# Runbook — scheduler not running

**Severity: critical, but quiet.** Nothing errors. Everything just stops
happening, and the system keeps serving confidently stale numbers.

## What stops

| Job | Consequence of a day's outage |
|---|---|
| `run_reminder_rules` | No fee reminders. Collections silently slips. |
| `refresh_collection_cases` | Ageing buckets freeze; the collections dashboard lies. |
| `create_due_invoices` | Installments fall due but are never billed. |
| `apply_late_fees` | Late fees not charged (recoverable — it is date-driven). |
| `refresh_due_kpis` | Executive dashboards serve yesterday's numbers **without saying so**. |
| `flush_outbox` | Queued notifications never send. |
| `submit_queued` (ZATCA) | Invoices post but do not clear. Compliance exposure grows. |
| `notify_document_expiry` | Iqama/contract expiry warnings missed. |

## Confirm

```bash
kubectl -n ags-erp get pods -l tier=scheduler
kubectl -n ags-erp logs -l tier=scheduler --tail=100
bench --site erp.ags.edu.sa doctor
```

`bench doctor` reports scheduler status and queue depth in one shot.

## Common causes

1. **Scheduler disabled in the site**, not a pod problem:
   ```bash
   bench --site erp.ags.edu.sa enable-scheduler
   ```
   `bench new-site` leaves it disabled — this bites on every fresh environment.
2. **Cannot reach `redis-queue`.** Check the NetworkPolicy and the service.
3. **Crash loop** from a bad scheduled method. The traceback is in `Error Log`.

## Recover

Restart, then catch up the jobs that are safe to re-run. All of these are
idempotent by design:

```bash
kubectl -n ags-erp rollout restart statefulset ags-scheduler

bench --site erp.ags.edu.sa execute ags_edusmart.ags_collections.ageing.refresh_collection_cases
bench --site erp.ags.edu.sa execute ags_edusmart.ags_fees.payer.refresh_all
bench --site erp.ags.edu.sa execute ags_edusmart.ags_dashboards.kpi_engine.refresh_due_kpis
bench --site erp.ags.edu.sa execute ags_edusmart.ags_notifications.dispatcher.flush_outbox
```

**Think before catching up the reminder ladder.** `run_reminder_rules` fires
against invoices due *relative to today*. Running it after a multi-day outage
sends only today's ladder step, which is usually what you want — but if parents
missed three days of warnings, coordinate with collections rather than silently
skipping to "30 days overdue".
