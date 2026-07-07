# Custom metrics — smarthr360-core-hr

All metrics are exposed on the existing `/metrics` endpoint (django-prometheus,
default registry). No extra endpoint is needed — the platform Prometheus job
that already scrapes `core-hr:8000/metrics` picks them up automatically.

## ERP ingestion (Étape 1)

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `smarthr360_erp_sync_runs_total` | counter | `source_system`, `status` | ERP sync runs, by source (`ODOO`/`SAP`) and final status (`SUCCESS`/`PARTIAL`/`FAILED`) |
| `smarthr360_erp_sync_records_total` | counter | `source_system`, `outcome` | Records processed (`created`/`updated`/`skipped`/`error`) |
| `smarthr360_erp_sync_last_success_timestamp_seconds` | gauge | `source_system` | Unix time of last successful sync |

## Skill-gap predictions (Étape 4)

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `smarthr360_skill_gap_forecasts` | gauge | `department`, `severity` | Latest forecast count per department/severity |
| `smarthr360_skill_gap_high_count` | gauge | `department` | Latest number of HIGH-severity gaps per department |
| `smarthr360_skill_gap_last_run_timestamp_seconds` | gauge | — | Unix time of last prediction run |

## Example PromQL

```promql
# ERP sync failure rate over 1h, by source
sum by (source_system) (rate(smarthr360_erp_sync_runs_total{status="FAILED"}[1h]))
  / sum by (source_system) (rate(smarthr360_erp_sync_runs_total[1h]))

# Alert if no successful sync in the last 24h
time() - max by (source_system) (smarthr360_erp_sync_last_success_timestamp_seconds) > 86400

# Total HIGH-severity skill gaps across the org
sum(smarthr360_skill_gap_high_count)
```
