# Runbook — slow responses

**Check the clock first.** Between 07:00 and 15:00 this is urgent; at 22:00 it
is usually a background job and can wait for morning.

## Triage in order

Work down. Each step is cheap and rules out a whole class of cause.

### 1. Is it the database or the app tier?

```bash
kubectl -n ags-erp top pods -l tier=web
kubectl exec -n ags-erp deploy/mariadb-primary -- mysqladmin processlist | head -40
```

- Web CPU high, DB idle → app tier saturated. Go to `capacity.md`.
- DB busy, web waiting → a query problem. Continue.

### 2. Find the query

```sql
SELECT id, user, time, state, LEFT(info, 200)
FROM information_schema.processlist
WHERE command != 'Sleep' AND time > 2
ORDER BY time DESC;
```

Then the slow log (`long_query_time = 1`):

```bash
kubectl exec -n ags-erp deploy/mariadb-primary -- \
  mysqldumpslow -s t -t 20 /var/log/mysql/slow.log
```

### 3. The three regressions this system is prone to

These are ranked by how often they are the answer.

**a. A dashboard doing live aggregation.** KPI reads are supposed to be a single
indexed lookup on `tabAGS KPI Snapshot.scope_key`. If you see a scan of
`tabGL Entry` behind a dashboard request, a KPI has been switched from `Method`
to a live `SQL` source, or snapshots have gone stale and something is falling
back. Check:

```sql
SELECT code, MAX(computed_on) FROM `tabAGS KPI Snapshot` GROUP BY code
ORDER BY 2 ASC LIMIT 10;
```

Stale snapshots mean the scheduler is not running → `scheduler-down.md`.

**b. A permission query gone Python-side.** Parent and teacher row scoping is a
SQL subquery on purpose (`ags_core/permissions.py`). If someone replaces it with
a Python list of ids, every portal list view carries a few thousand-element `IN`
clause. Symptom: portal p95 climbs while desk p95 is fine.

**c. Buffer pool thrashing.** If
`innodb_buffer_pool_reads / innodb_buffer_pool_read_requests > 2%`, the working
set has outgrown the 44 GB pool. **Do not add web pods** — more concurrency
against a thrashing database makes it worse. See `capacity.md`.

### 4. Confirm the fix

```bash
k6 run -e BASE_URL=https://erp-staging.ags.edu.sa load-tests/k6/school-day.js
```

The thresholds in that script are the SLOs. A pass is the evidence.
