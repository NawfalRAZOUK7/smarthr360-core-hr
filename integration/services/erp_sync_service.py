"""ERP ingestion orchestration.

Pipeline (EAI ingestion side)::

    raw bytes
       │  adapter.parse()          -> CanonicalEmployee stream   (format layer)
       ▼
    ERPEmployeeStagingSerializer   -> validated dicts            (data-quality gate)
       ▼
    upsert EmployeeProfile         -> idempotent, keyed on       (persistence layer)
                                      (source_system, external_employee_id)
       ▼
    second pass: link managers by external id
       ▼
    ERPSyncRun                     -> audit + metrics source

The whole run is wrapped in a single transaction (unless ``dry_run``): either
every valid record lands or none does, so a crashed sync never leaves the HR
database half-updated.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable

from django.db import transaction
from django.utils import timezone

from hr.models import Department, EmployeeProfile
from hr.services.history_service import (
    history_signal_suppressed,
    snapshot_employee_history,
)

from config.metrics import record_erp_sync

from ..adapters import AdapterRecordError, ERPAdapter
from ..adapters.base import CanonicalEmployee
from ..models import ERPSyncRun
from ..serializers import ERPEmployeeStagingSerializer

logger = logging.getLogger("integration.erp_sync")


@dataclass
class ERPSyncResult:
    source_system: str
    dry_run: bool
    total: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list = field(default_factory=list)
    run_id: int | None = None

    @property
    def status(self) -> str:
        if self.errors and (self.created or self.updated):
            return ERPSyncRun.Status.PARTIAL
        if self.errors and not (self.created or self.updated):
            return ERPSyncRun.Status.FAILED
        return ERPSyncRun.Status.SUCCESS

    def as_summary(self) -> str:
        mode = "DRY-RUN" if self.dry_run else "COMMIT"
        return (
            f"[{mode}] {self.source_system}: {self.total} read, "
            f"{self.created} created, {self.updated} updated, "
            f"{self.skipped} skipped, {len(self.errors)} errors "
            f"-> {self.status}"
        )


class ERPSyncService:
    """Runs one ERP import end-to-end."""

    def __init__(self, adapter: ERPAdapter, *, triggered_by_user_id: int | None = None):
        self.adapter = adapter
        self.triggered_by_user_id = triggered_by_user_id

    # ------------------------------------------------------------------
    def run(
        self,
        raw: bytes,
        *,
        dry_run: bool = False,
        file_name: str = "",
        record_run: bool = True,
    ) -> ERPSyncResult:
        result = ERPSyncResult(
            source_system=self.adapter.source_system, dry_run=dry_run
        )

        # 1. parse + validate into a staging list (no DB writes yet)
        staged, manager_links = self._stage(raw, result)

        # 2. open the audit run early so its id can be stamped on each history
        #    row for full run -> change lineage (Option B).
        run = None
        if record_run and not dry_run:
            run = ERPSyncRun.objects.create(
                source_system=self.adapter.source_system,
                file_name=file_name,
                dry_run=False,
                status=ERPSyncRun.Status.RUNNING,
                triggered_by_user_id=self.triggered_by_user_id,
            )
            result.run_id = run.pk

        # 3. persist (atomic). dry_run rolls the savepoint back at the end.
        #    We take over historization explicitly, so the post_save signal is
        #    muted for this block (single write path, correct provenance, and
        #    the manager set via .update() is captured by the final pass).
        with history_signal_suppressed(), transaction.atomic():
            sid = transaction.savepoint()
            affected = self._upsert(staged, result)
            self._link_managers(manager_links, result)
            self._snapshot_history(affected, result.run_id)
            if dry_run:
                transaction.savepoint_rollback(sid)
            else:
                transaction.savepoint_commit(sid)

        # 4. finalize the audit run + emit Prometheus metrics (real runs only)
        if run is not None:
            self._finalize_run(run, result)
            record_erp_sync(result)

        logger.info(result.as_summary())
        return result

    # -- stage ----------------------------------------------------------
    def _stage(self, raw: bytes, result: ERPSyncResult):
        staged: list[dict] = []
        manager_links: list[tuple[str, str]] = []

        records: Iterable[CanonicalEmployee]
        # Adapter-level (document) errors propagate to the caller.
        records = self.adapter.parse(raw)

        index = 0
        while True:
            try:
                canonical = next(records)
            except StopIteration:
                break
            except AdapterRecordError as exc:
                result.total += 1
                result.skipped += 1
                result.errors.append(
                    {
                        "index": exc.index if exc.index is not None else index,
                        "external_id": "",
                        "field": "record",
                        "error": str(exc),
                    }
                )
                index += 1
                continue

            result.total += 1
            serializer = ERPEmployeeStagingSerializer(data=canonical.as_dict())
            if not serializer.is_valid():
                result.skipped += 1
                for field_name, msgs in serializer.errors.items():
                    result.errors.append(
                        {
                            "index": index,
                            "external_id": canonical.external_employee_id,
                            "field": field_name,
                            "error": "; ".join(str(m) for m in msgs),
                        }
                    )
                index += 1
                continue

            data = serializer.validated_data
            staged.append(data)
            if data.get("manager_external_id"):
                manager_links.append(
                    (data["external_employee_id"], data["manager_external_id"])
                )
            index += 1

        return staged, manager_links

    # -- upsert ---------------------------------------------------------
    def _upsert(self, staged: list[dict], result: ERPSyncResult) -> list[int]:
        """Upsert employees; return the pks touched by this run."""
        affected: list[int] = []
        for data in staged:
            department = self._resolve_department(
                data.get("department_code"), data.get("department_name")
            )
            defaults = {
                "email": data.get("email", ""),
                "first_name": data.get("first_name", ""),
                "last_name": data.get("last_name", ""),
                "user_role": data.get("user_role", "EMPLOYEE"),
                "job_title": data.get("job_title", ""),
                "employment_type": data.get("employment_type", "FULL_TIME"),
                "hire_date": data.get("hire_date"),
                "phone_number": data.get("phone_number", ""),
                "is_active": data.get("is_active", True),
                "department": department,
            }
            # Only overwrite user_id when the ERP actually provides one, so we
            # never wipe an already-linked auth account on resync.
            if data.get("user_id"):
                defaults["user_id"] = data["user_id"]

            obj, created = EmployeeProfile.objects.update_or_create(
                source_system=data["source_system"],
                external_employee_id=data["external_employee_id"],
                defaults=defaults,
            )
            affected.append(obj.pk)
            if created:
                result.created += 1
            else:
                result.updated += 1
        return affected

    def _snapshot_history(self, affected_pks: list[int], run_id: int | None):
        """Open one SCD2 version per changed employee, with run provenance.

        Runs after manager linking so the final manager is captured. Reloads
        the rows so ``.update()``-set managers are reflected. Idempotent: an
        employee whose facts did not actually change yields no new version.
        """
        source = self.adapter.source_system
        reason = (
            f"ERP sync #{run_id} ({source})" if run_id else f"ERP dry-run ({source})"
        )
        for emp in EmployeeProfile.objects.filter(pk__in=affected_pks):
            snapshot_employee_history(
                emp,
                reason=reason,
                changed_by_user_id=self.triggered_by_user_id,
                source_system=source,
            )

    def _link_managers(self, links: list[tuple[str, str]], result: ERPSyncResult):
        source = self.adapter.source_system
        for emp_ext_id, mgr_ext_id in links:
            manager = EmployeeProfile.objects.filter(
                source_system=source, external_employee_id=mgr_ext_id
            ).first()
            if manager is None:
                result.errors.append(
                    {
                        "index": -1,
                        "external_id": emp_ext_id,
                        "field": "manager_external_id",
                        "error": f"manager '{mgr_ext_id}' not found in batch",
                    }
                )
                continue
            EmployeeProfile.objects.filter(
                source_system=source, external_employee_id=emp_ext_id
            ).exclude(pk=manager.pk).update(manager=manager)

    @staticmethod
    def _resolve_department(code: str, name: str):
        code = (code or "").strip()
        name = (name or "").strip()
        if not code and not name:
            return None
        if code:
            dept, _ = Department.objects.get_or_create(
                code=code, defaults={"name": name or code.title()}
            )
            return dept
        # No code: match/create by name using a slugged code.
        dept, _ = Department.objects.get_or_create(
            name=name, defaults={"code": name.upper()[:20]}
        )
        return dept

    # -- audit ----------------------------------------------------------
    def _finalize_run(self, run: ERPSyncRun, result: ERPSyncResult) -> None:
        run.status = result.status
        run.total_records = result.total
        run.created_count = result.created
        run.updated_count = result.updated
        run.skipped_count = result.skipped
        run.error_count = len(result.errors)
        run.errors = result.errors[:500]  # cap payload
        run.finished_at = timezone.now()
        run.save()
