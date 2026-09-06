# Runbook — queue backlog

Triggered by `AGSQueueBacklog`, `AGSShortQueueBacklog`,
`AGSRedisQueueNearCapacity`, `AGSNotificationOutboxStalled` or
`AGSInvoiceGenerationStalled`.

## Which queue, and does it hurt now?

| Queue | Carries | Felt by users |
|---|---|---|
| `short` | notification queueing, cache invalidation | immediately |
| `default` | document hooks, integrations | within minutes |
| `long` | reminder ladder, KPI refresh, ZATCA, invoicing | next day |

A `short` backlog during the school day is an incident. A `long` backlog at
02:00 usually is not.

```bash
bench --site erp.ags.edu.sa doctor
kubectl -n ags-erp exec deploy/redis-queue -- redis-cli -p 11000 info keyspace
```

## The dangerous one: redis-queue near capacity

`redis-queue` runs `maxmemory-policy noeviction` deliberately
(`infra/redis/redis-queue.conf`). Under any `allkeys-*` policy Redis would
**silently discard queued jobs** — an unsent reminder, a lost ZATCA clearance,
an invoice never generated, with no error anywhere. `noeviction` converts that
into loud enqueue failures instead.

So at >80% memory you are close to enqueues failing:

```bash
kubectl -n ags-erp exec deploy/redis-queue -- redis-cli -p 11000 info memory | head
```

Drain first, resize second:

```bash
kubectl -n ags-erp scale deployment ags-worker-long --replicas=16
```

## Why it is backed up

1. **Workers are dead or crash-looping.**
   ```bash
   kubectl -n ags-erp get pods -l tier=worker
   kubectl -n ags-erp logs -l queue=long --tail=200 | grep -i traceback
   ```
2. **A poison job** retrying forever. Look in `Error Log` for a repeating title.
3. **A slow external gateway.** SMS/WhatsApp delivery is HTTP with a 15 s
   timeout; a dead gateway makes every send take 15 s. The outbox is designed so
   this cannot block a transaction, but it will stall the drain.
   ```sql
   SELECT channel, status, COUNT(*) FROM `tabAGS Notification Outbox`
   WHERE creation > NOW() - INTERVAL 1 DAY GROUP BY 1,2;
   ```
   If one channel is failing, disable it in AGS Settings and let the rest drain.

## Draining safely

Everything on these queues is idempotent — outbox rows and reminder logs carry
unique dedupe keys, and installment invoicing refuses to double-bill. It is
therefore safe to add workers and safe to re-run a failed pass.

```bash
kubectl -n ags-erp scale deployment ags-worker-short --replicas=16
# and afterwards, back to the model's numbers
kubectl -n ags-erp scale deployment ags-worker-short --replicas=8
```

Failed outbox rows park at `status = Failed` after 5 attempts. Re-queue them
once the gateway is healthy:

```sql
UPDATE `tabAGS Notification Outbox`
SET status = 'Queued', attempts = 0, scheduled_for = NOW()
WHERE status = 'Failed' AND creation > NOW() - INTERVAL 2 DAY;
```

## Installments due but not invoiced

```bash
bench --site erp.ags.edu.sa execute ags_edusmart.ags_fees.invoicing.create_due_invoices
```

Safe to re-run: it skips any installment that already carries an invoice, and
commits per plan so one bad plan cannot roll back the batch. Check the returned
`failed` list and the Error Log for those.
