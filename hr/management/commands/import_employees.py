"""Import employee profiles from a CSV file.

Covers both the legacy-data migration path and bulk onboarding.
Columns (header required, extra columns ignored):

    user_id,email,first_name,last_name,user_role,department_code,
    job_title,manager_user_id,hire_date

Idempotent: rows are matched by user_id and updated in place.
Managers are wired in a second pass so row order doesn't matter.

    python manage.py import_employees employees.csv [--dry-run]
"""

import csv

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from hr.models import Department, EmployeeProfile


class Command(BaseCommand):
    help = "Import/update employee profiles from a CSV file (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            fh = open(options["csv_path"], newline="", encoding="utf-8-sig")
        except OSError as exc:
            raise CommandError(str(exc)) from exc

        with fh:
            rows = list(csv.DictReader(fh))
        if not rows:
            raise CommandError("CSV contains no data rows.")

        created = updated = 0
        manager_links: list[tuple[int, int]] = []

        for line, row in enumerate(rows, start=2):
            try:
                user_id = int(row["user_id"])
            except (KeyError, TypeError, ValueError) as exc:
                raise CommandError(f"line {line}: bad user_id") from exc

            department = None
            code = (row.get("department_code") or "").strip()
            if code:
                department, _ = Department.objects.get_or_create(
                    code=code, defaults={"name": code.title()}
                )

            defaults = {
                "email": (row.get("email") or "").strip(),
                "first_name": (row.get("first_name") or "").strip(),
                "last_name": (row.get("last_name") or "").strip(),
                "user_role": (row.get("user_role") or "EMPLOYEE").strip()
                or "EMPLOYEE",
                "department": department,
                "job_title": (row.get("job_title") or "").strip(),
                "hire_date": (row.get("hire_date") or "").strip() or None,
            }
            _, was_created = EmployeeProfile.objects.update_or_create(
                user_id=user_id, defaults=defaults
            )
            created += int(was_created)
            updated += int(not was_created)

            manager_raw = (row.get("manager_user_id") or "").strip()
            if manager_raw:
                manager_links.append((user_id, int(manager_raw)))

        linked = 0
        for user_id, manager_user_id in manager_links:
            manager = EmployeeProfile.objects.filter(
                user_id=manager_user_id
            ).first()
            if manager is None:
                self.stderr.write(
                    f"warning: manager user_id={manager_user_id} not found "
                    f"for employee user_id={user_id}"
                )
                continue
            EmployeeProfile.objects.filter(user_id=user_id).update(
                manager=manager
            )
            linked += 1

        summary = (f"created={created} updated={updated} "
                   f"manager_links={linked}")
        if options["dry_run"]:
            transaction.set_rollback(True)
            self.stdout.write(self.style.WARNING(f"DRY RUN — {summary}"))
        else:
            self.stdout.write(self.style.SUCCESS(summary))
