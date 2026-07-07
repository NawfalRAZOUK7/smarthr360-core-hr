"""SCD Type 2 historization service for EmployeeProfile.

Single entry point :func:`snapshot_employee_history`. It is **idempotent**: if
the tracked facts are unchanged since the current open row, it does nothing —
so it is safe to call it from a ``post_save`` signal, from the ERP sync service
and from the backfill command without ever creating duplicate versions.

Transition rule (SCD2):
    on a detected change at instant T:
        current_row.date_fin = T; current_row.is_current = False
        new_row.date_debut  = T; new_row.version = current.version + 1
"""

from __future__ import annotations

import contextlib
import logging
import threading
from typing import Optional

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger("hr.history")

# Thread-local switch letting a caller (e.g. the ERP sync service) take over
# historization explicitly and mute the post_save signal for the duration, so
# there is a single write path and no redundant snapshot attempts.
_state = threading.local()


def signal_suppressed() -> bool:
    return getattr(_state, "suppress", False)


@contextlib.contextmanager
def history_signal_suppressed():
    """Within this block the post_save history signal is a no-op."""
    previous = getattr(_state, "suppress", False)
    _state.suppress = True
    try:
        yield
    finally:
        _state.suppress = previous

# Fields on EmployeeProfile whose change opens a new SCD2 version.
TRACKED_FIELDS = (
    "department_id",
    "manager_id_snapshot",
    "job_title",
    "employment_type",
    "user_role",
    "salary",
    "is_employment_active",
)


def build_snapshot_from_employee(employee) -> dict:
    """Extract the tracked snapshot dict from a live EmployeeProfile."""
    return {
        "department_id": employee.department_id,
        "manager_id_snapshot": employee.manager_id,
        "job_title": employee.job_title or "",
        "employment_type": employee.employment_type or "",
        "user_role": employee.user_role or "",
        "salary": employee.salary,
        "is_employment_active": bool(employee.is_active),
    }


def _differs(new: dict, current) -> bool:
    if current is None:
        return True
    cur = current.tracked_snapshot
    return any(new.get(f) != cur.get(f) for f in TRACKED_FIELDS)


@transaction.atomic
def snapshot_employee_history(
    employee,
    *,
    reason: str = "",
    changed_by_user_id: Optional[int] = None,
    source_system: str = "",
    at=None,
):
    """Open a new SCD2 version for ``employee`` iff a tracked fact changed.

    Returns the newly created ``EmployeeProfileHistory`` row, or ``None`` when
    nothing changed.
    """
    # Local import avoids app-registry issues at import time (signals/apps).
    from hr.models import EmployeeProfileHistory

    now = at or timezone.now()
    new_snapshot = build_snapshot_from_employee(employee)

    # Lock the open row to serialise concurrent updates on the same employee.
    current = (
        EmployeeProfileHistory.objects.select_for_update()
        .filter(employee=employee, date_fin__isnull=True)
        .order_by("-version")
        .first()
    )

    if not _differs(new_snapshot, current):
        return None

    if current is not None:
        current.date_fin = now
        current.is_current = False
        current.save(update_fields=["date_fin", "is_current"])
        next_version = current.version + 1
        # First real change inherits provenance context; if the caller gave no
        # reason, describe what moved.
        reason = reason or _describe_change(current.tracked_snapshot, new_snapshot)
    else:
        next_version = 1
        reason = reason or "initial"

    row = EmployeeProfileHistory.objects.create(
        employee=employee,
        department_id=new_snapshot["department_id"],
        manager_id_snapshot=new_snapshot["manager_id_snapshot"],
        job_title=new_snapshot["job_title"],
        employment_type=new_snapshot["employment_type"],
        user_role=new_snapshot["user_role"],
        salary=new_snapshot["salary"],
        is_employment_active=new_snapshot["is_employment_active"],
        version=next_version,
        date_debut=now,
        date_fin=None,
        is_current=True,
        change_reason=reason[:255],
        changed_by_user_id=changed_by_user_id,
        source_system=source_system or getattr(employee, "source_system", "") or "",
    )
    logger.info(
        "SCD2 snapshot employee=%s v%s reason=%s", employee.pk, next_version, reason
    )
    return row


def _describe_change(old: dict, new: dict) -> str:
    changed = [f for f in TRACKED_FIELDS if old.get(f) != new.get(f)]
    label = {
        "department_id": "department",
        "manager_id_snapshot": "manager",
        "job_title": "job_title",
        "employment_type": "employment_type",
        "user_role": "role",
        "salary": "salary",
        "is_employment_active": "employment_status",
    }
    return "changed: " + ", ".join(label.get(f, f) for f in changed)
