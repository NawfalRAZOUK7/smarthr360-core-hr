"""Ingest an ERP personnel export into SmartHR360.

    python manage.py sync_erp <file> --source {odoo|sap} [--dry-run]

Examples::

    python manage.py sync_erp integration/samples/odoo_employees.json --source odoo
    python manage.py sync_erp integration/samples/sap_employees.xml --source sap --dry-run

Idempotent: rerunning the same file updates existing profiles in place
(matched on source_system + external_employee_id) and never creates duplicates.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from integration.adapters import AdapterError, available_sources, get_adapter
from integration.services import ERPSyncService


class Command(BaseCommand):
    help = "Import/update employee profiles from an ERP export (Odoo JSON, SAP XML)."

    def add_arguments(self, parser):
        parser.add_argument("file", help="Path to the ERP export file.")
        parser.add_argument(
            "--source",
            required=True,
            choices=available_sources(),
            help="ERP source format.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse, validate and simulate the upsert without committing.",
        )
        parser.add_argument(
            "--user-id",
            type=int,
            default=None,
            help="Auth user id triggering the sync (audit).",
        )

    def handle(self, *args, **opts):
        path = opts["file"]
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
        except OSError as exc:
            raise CommandError(f"cannot read '{path}': {exc}") from exc

        try:
            adapter = get_adapter(opts["source"])
        except AdapterError as exc:
            raise CommandError(str(exc)) from exc

        service = ERPSyncService(adapter, triggered_by_user_id=opts.get("user_id"))
        try:
            result = service.run(
                raw, dry_run=opts["dry_run"], file_name=path
            )
        except AdapterError as exc:
            raise CommandError(f"parse failed: {exc}") from exc

        self.stdout.write(self.style.MIGRATE_HEADING(result.as_summary()))
        if result.run_id:
            self.stdout.write(f"  audit: ERPSyncRun#{result.run_id}")
        for err in result.errors[:20]:
            self.stdout.write(
                self.style.WARNING(
                    f"  - [{err['external_id'] or err['index']}] "
                    f"{err['field']}: {err['error']}"
                )
            )
        if len(result.errors) > 20:
            self.stdout.write(f"  ... {len(result.errors) - 20} more errors")

        if result.status == "FAILED":
            raise CommandError("sync failed: no record could be imported.")
