"""Seed the SCD2 history for employees that have none yet.

Opens an initial (version 1) history row for every EmployeeProfile without an
open row. Idempotent: employees that already have history are skipped.

    python manage.py backfill_history [--reason "initial load"] [--dry-run]
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from hr.models import EmployeeProfile, EmployeeProfileHistory
from hr.services.history_service import snapshot_employee_history


class Command(BaseCommand):
    help = "Create initial SCD2 history rows for employees that have none."

    def add_arguments(self, parser):
        parser.add_argument("--reason", default="initial backfill")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        dry_run = opts["dry_run"]
        reason = opts["reason"]

        already = set(
            EmployeeProfileHistory.objects.filter(date_fin__isnull=True)
            .values_list("employee_id", flat=True)
        )
        todo = EmployeeProfile.objects.exclude(pk__in=already)
        total = todo.count()

        created = 0
        with transaction.atomic():
            sid = transaction.savepoint()
            for emp in todo.iterator():
                row = snapshot_employee_history(
                    emp, reason=reason, source_system=emp.source_system or "MANUAL"
                )
                created += int(row is not None)
            if dry_run:
                transaction.savepoint_rollback(sid)
            else:
                transaction.savepoint_commit(sid)

        mode = "DRY-RUN" if dry_run else "COMMIT"
        self.stdout.write(
            self.style.SUCCESS(
                f"[{mode}] {total} employees without history, {created} rows opened."
            )
        )
