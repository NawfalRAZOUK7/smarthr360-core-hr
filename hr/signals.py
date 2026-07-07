"""Signals that keep the SCD2 history in sync with EmployeeProfile.

Wiring a ``post_save`` receiver means *every* write path — Django admin, DRF
API, the ERP sync service, data migrations — automatically produces history,
with no risk of a caller forgetting to snapshot.

The snapshot service is idempotent, so callers that already snapshot with rich
context (e.g. the ERP sync passing a change reason) are not double-counted:
the signal simply finds no diff and does nothing.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from hr.models import EmployeeProfile
from hr.services.history_service import signal_suppressed, snapshot_employee_history

logger = logging.getLogger("hr.history")


@receiver(post_save, sender=EmployeeProfile, dispatch_uid="hr_employee_scd2_history")
def record_employee_history(sender, instance, created, **kwargs):
    """Open a new SCD2 version when a tracked fact changed.

    Deferred with ``on_commit`` so the history row is written only once the
    employee row is durably committed (avoids orphan history on rollback).

    Skipped when a caller (ERP sync) has taken over historization explicitly.
    """
    if signal_suppressed():
        return

    reason = "created" if created else ""

    def _snapshot():
        try:
            snapshot_employee_history(instance, reason=reason)
        except Exception:  # never let history break the main write
            logger.exception("SCD2 history snapshot failed for employee=%s", instance.pk)

    transaction.on_commit(_snapshot)
