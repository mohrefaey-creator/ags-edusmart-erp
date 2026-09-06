# Runbook — 5xx spike

## Establish blast radius first

```bash
kubectl -n ags-erp logs -l tier=web --tail=200 | grep -iE "traceback|error" | head -40
kubectl -n ags-erp get pods -l tier=web
```

Is it every pod, or one? One pod failing while others are healthy is usually a
bad node or a wedged worker — delete the pod, then investigate at leisure.

## Read the actual exception

Frappe records these in the site, so they survive a pod restart:

```sql
SELECT method, LEFT(error, 400) AS err, COUNT(*) c
FROM `tabError Log`
WHERE creation > NOW() - INTERVAL 1 HOUR
GROUP BY method, err
ORDER BY c DESC LIMIT 10;
```

## Causes seen on this stack, in likelihood order

1. **Database connections exhausted** — `Too many connections`. Compare
   `threads_connected` with `max_connections` (500). Usually follows a scale-up
   past the connection budget; see `capacity.md`.

2. **A missing accounting-dimension column.** The signature is
   `Unknown column 'campus' in 'SELECT'`, raised from ERPNext's *own* budget
   validation whenever a GL entry posts. ERPNext hands dimension field creation
   to a background worker (`enqueue_after_commit`), so on a cluster where no
   worker was running when the dimension was created, the Accounting Dimension
   row exists and its columns do not. Fix:
   ```bash
   bench --site erp.ags.edu.sa execute ags_edusmart.setup.dimensions.execute
   bench --site erp.ags.edu.sa migrate
   ```
   `setup/dimensions.py` calls the field maker synchronously for exactly this
   reason; this alert means something created a dimension outside that path.

3. **A half-applied migration.** Check the migration Job's output from the last
   deploy. Migrations run as their own Job before the rollout precisely so this
   is visible rather than racing six web pods.

4. **Redis unreachable.** Cache loss degrades; queue loss breaks any write that
   enqueues. Check NetworkPolicy first if this appeared right after a cluster
   change.

## Roll back

If the spike began with a deploy, roll back first and diagnose after — unless
the release included a schema migration, in which case check what the migration
changed before reverting the image.

```bash
kubectl -n ags-erp rollout undo deployment/ags-web
kubectl -n ags-erp rollout status deployment/ags-web
```
