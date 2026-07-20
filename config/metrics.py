"""Custom Prometheus metrics for smarthr360-core-hr (Étape 5).

These live on the default prometheus_client registry, which ``django-prometheus``
already exposes at ``/metrics`` — so every metric defined here is scraped by the
platform Prometheus without any extra endpoint.

Naming follows Prometheus conventions: ``smarthr360_<subsystem>_<unit>`` with
``_total`` for counters and ``_seconds`` for timestamps. Helper functions keep
the instrumentation out of the business services.
"""

from __future__ import annotations

import time

from prometheus_client import Counter, Gauge

# ---------------------------------------------------------------------------
# ERP ingestion (EAI) — Étape 1
# ---------------------------------------------------------------------------
ERP_SYNC_RUNS = Counter(
    "smarthr360_erp_sync_runs_total",
    "Number of ERP synchronization runs, by source system and final status.",
    ["source_system", "status"],
)

ERP_SYNC_RECORDS = Counter(
    "smarthr360_erp_sync_records_total",
    "Employee records processed by the ERP connector, by source and outcome.",
    ["source_system", "outcome"],  # created | updated | skipped | error
)

ERP_SYNC_LAST_SUCCESS = Gauge(
    "smarthr360_erp_sync_last_success_timestamp_seconds",
    "Unix time of the last successful (SUCCESS/PARTIAL) ERP sync, by source.",
    ["source_system"],
    multiprocess_mode="max",  # timestamp: latest across workers
)

# ---------------------------------------------------------------------------
# Skill-gap predictions — Étape 4
# ---------------------------------------------------------------------------
SKILL_GAP_FORECASTS = Gauge(
    "smarthr360_skill_gap_forecasts",
    "Latest skill-gap forecast count, by department and severity.",
    ["department", "severity"],
    multiprocess_mode="livesum",  # current count: sum across live workers
)

SKILL_GAP_HIGH = Gauge(
    "smarthr360_skill_gap_high_count",
    "Latest number of HIGH-severity skill gaps, by department.",
    ["department"],
    multiprocess_mode="livesum",
)

SKILL_GAP_LAST_RUN = Gauge(
    "smarthr360_skill_gap_last_run_timestamp_seconds",
    "Unix time of the last skill-gap prediction run.",
    multiprocess_mode="max",  # timestamp: latest across workers
)


# ---------------------------------------------------------------------------
# Instrumentation helpers
# ---------------------------------------------------------------------------
def record_erp_sync(result) -> None:
    """Update ERP metrics from an ERPSyncResult. Never raises."""
    try:
        source = result.source_system or "UNKNOWN"
        status = str(result.status)
        ERP_SYNC_RUNS.labels(source_system=source, status=status).inc()
        ERP_SYNC_RECORDS.labels(source_system=source, outcome="created").inc(result.created)
        ERP_SYNC_RECORDS.labels(source_system=source, outcome="updated").inc(result.updated)
        ERP_SYNC_RECORDS.labels(source_system=source, outcome="skipped").inc(result.skipped)
        ERP_SYNC_RECORDS.labels(source_system=source, outcome="error").inc(len(result.errors))
        if status in {"SUCCESS", "PARTIAL"}:
            ERP_SYNC_LAST_SUCCESS.labels(source_system=source).set(time.time())
    except Exception:  # pragma: no cover - metrics must never break business logic
        pass


def record_skill_gap_run(forecasts) -> None:
    """Set skill-gap gauges from a list of forecast dicts. Never raises."""
    try:
        by_dept_sev: dict[tuple[str, str], int] = {}
        high_by_dept: dict[str, int] = {}
        for f in forecasts:
            dept = f["department_code"]
            sev = f["severity"]
            by_dept_sev[(dept, sev)] = by_dept_sev.get((dept, sev), 0) + 1
            if sev == "HIGH":
                high_by_dept[dept] = high_by_dept.get(dept, 0) + 1

        # Reset known series so a department that dropped to zero reports zero.
        SKILL_GAP_HIGH.clear()
        SKILL_GAP_FORECASTS.clear()
        for dept, count in high_by_dept.items():
            SKILL_GAP_HIGH.labels(department=dept).set(count)
        for (dept, sev), count in by_dept_sev.items():
            SKILL_GAP_FORECASTS.labels(department=dept, severity=sev).set(count)

        SKILL_GAP_LAST_RUN.set(time.time())
    except Exception:  # pragma: no cover
        pass
