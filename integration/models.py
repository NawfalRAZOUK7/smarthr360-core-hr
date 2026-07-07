"""Persistence for the ERP integration layer.

Only ingestion *bookkeeping* lives here — the employee records themselves are
written into ``hr.EmployeeProfile``. ``ERPSyncRun`` is the audit trail of every
synchronization and is also the source of the Prometheus metrics exposed in
Étape 5.
"""

from django.db import models


class ERPSyncRun(models.Model):
    """One execution of the ERP ingestion pipeline."""

    class Status(models.TextChoices):
        RUNNING = "RUNNING", "Running"
        SUCCESS = "SUCCESS", "Success"
        PARTIAL = "PARTIAL", "Partial (some records rejected)"
        FAILED = "FAILED", "Failed"

    source_system = models.CharField(max_length=32)
    file_name = models.CharField(max_length=255, blank=True)
    dry_run = models.BooleanField(default=False)

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.RUNNING
    )

    total_records = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)

    # Structured per-record errors: [{"index": int, "external_id": str,
    # "field": str, "error": str}, ...]
    errors = models.JSONField(default=list, blank=True)

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    triggered_by_user_id = models.PositiveBigIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(
                fields=["source_system", "-started_at"],
                name="integration_src_started_idx",
            ),
            models.Index(fields=["status"], name="integration_status_idx"),
        ]

    def __str__(self):
        return (
            f"ERPSyncRun#{self.pk} {self.source_system} {self.status} "
            f"(+{self.created_count}/~{self.updated_count}/x{self.error_count})"
        )
