# Runbook — more than one scheduler running

**Severity: critical. Act immediately; the damage is outbound and irreversible.**

## Why this matters

Every scheduled job fires once per scheduler. Two schedulers means:

- two overdue-fee SMS/WhatsApp messages to every overdue parent,
- two late-fee invoices against the same overdue invoice,
- two KPI refresh passes (harmless, just wasteful),
- two invoicing runs (mostly caught, see below).

The application defends itself in depth — `AGS Notification Outbox.dedupe_key`
and `AGS Reminder Log.dedupe_key` are unique, and installment invoicing refuses
to bill an installment that already carries a submitted invoice — so most
duplicates collapse. **Do not rely on that.** The guards are a safety net for a
race, not a licence to run two schedulers.

## Confirm

```bash
kubectl -n ags-erp get pods -l tier=scheduler
kubectl -n ags-erp get statefulset ags-scheduler -o jsonpath='{.spec.replicas}{"\n"}'
```

Anything other than exactly one running pod is the incident.

## Fix

```bash
kubectl -n ags-erp scale statefulset ags-scheduler --replicas=1
```

If a second scheduler is running outside Kubernetes (a leftover supervisor
process on a VM, common during a migration):

```bash
sudo supervisorctl stop ags-scheduler
sudo supervisorctl remove ags-scheduler   # and delete the file from that node
```

## Assess the damage

```bash
bench --site erp.ags.edu.sa mariadb
```

```sql
-- Duplicate outbound messages in the overlap window
SELECT reference_doctype, reference_name, channel, COUNT(*) c
FROM `tabAGS Notification Outbox`
WHERE creation > NOW() - INTERVAL 6 HOUR
GROUP BY 1,2,3 HAVING c > 1;

-- Duplicate late fees against the same invoice
SELECT ags_late_fee_against, COUNT(*) c
FROM `tabSales Invoice`
WHERE docstatus = 1 AND ags_late_fee_against IS NOT NULL
GROUP BY 1 HAVING c > 1;
```

Cancel duplicate late-fee invoices; they are ordinary Sales Invoices and cancel
cleanly. If duplicate messages were already delivered, tell the collections team
before parents call them.

## Prevent

The scheduler is a `StatefulSet` with `replicas: 1` and `OrderedReady`
(`infra/k8s/20-workers-scheduler.yaml`) specifically because a Deployment's
rolling update briefly runs two pods. Never convert it to a Deployment.
