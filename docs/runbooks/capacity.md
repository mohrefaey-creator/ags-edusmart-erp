# Runbook — capacity pressure

Triggered by `AGSWebSaturated`, `AGSWebAtMaxReplicas`, `AGSBufferPoolThrashing`
or `AGSConnectionsNearLimit`.

## First: is this growth, or a regression?

Adding hardware to a regression buys a few days and hides the cause. Compare
against the model in `docs/capacity-model.md`:

```
expected req/s = concurrent_sessions / 10
```

If request rate is roughly in line with the number of people actually logged in,
this is growth — scale. If request rate has jumped without more users, something
started making more calls per interaction: go to `slow-response.md` §3.

## Scaling the web tier

The model provisions 6 pods and autoscales to 10 (~72% utilisation at the
625 req/s design peak).

```bash
kubectl -n ags-erp get hpa ags-web
kubectl -n ags-erp patch hpa ags-web --type=merge \
  -p '{"spec":{"maxReplicas":14}}'
```

Before going past ~14, check the database connection budget:

```
web_pods x 17 workers + 20 background + overhead  <  max_connections (500)
```

14 pods puts you at ~260 connections — still fine. Beyond 20 pods, raise
`max_connections` in `infra/mariadb/primary.cnf` *and* size the DB for the extra
per-connection memory before scaling.

## Scaling the database

This is the harder ceiling, and usually the real one.

1. **Buffer pool.** Working set must fit. Recompute it:
   ```sql
   SELECT table_name,
          ROUND((data_length + index_length)/1024/1024/1024, 1) AS gb
   FROM information_schema.tables
   WHERE table_schema = DATABASE()
   ORDER BY data_length + index_length DESC LIMIT 15;
   ```
   Then set `innodb_buffer_pool_size` to ~70% of node RAM, sized above that
   total. Requires a restart — do it outside 07:00-15:00.

2. **Move reads off the primary.** Reports and dashboards should already be on
   the replica. Confirm in `site_config.json`:
   ```json
   { "read_from_replica": 1, "replica_host": "mariadb-replica.ags-erp.svc.cluster.local" }
   ```
   Never route writes or read-after-write flows there — replication is async, so
   a parent who has just paid could still see an outstanding balance.

3. **Prune the audit trail.** `tabVersion` is often the largest table. It is the
   audit trail (SKILL sec. 24), so it is retained deliberately — archive it to
   cold storage rather than deleting, and only with finance's agreement.

## What to do at the peak, right now

If it is 07:45 and the tier is pinned, in order of preference:

1. Raise `maxReplicas` (seconds, safe).
2. Confirm the CDN is serving `/assets/` — an origin serving bundles is the
   cheapest thing to fix and often the largest share of requests.
3. Defer background load: pause the `long` queue workers for the peak hour.
   Reminders and KPI refresh can wait an hour; attendance cannot.
   ```bash
   kubectl -n ags-erp scale deployment ags-worker-long --replicas=1
   ```
   Restore it afterwards.
