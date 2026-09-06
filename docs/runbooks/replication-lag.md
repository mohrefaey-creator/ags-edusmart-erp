# Runbook — replica lag above 5 s

## Why the SLO is 5 s

Reports and dashboards read the replica. Beyond a few seconds they start
disagreeing with the desk — finance runs a receivables report, sees a balance
that the cashier's screen says is already paid, and trust in the numbers goes
first.

Writes and read-after-write flows never touch the replica, so lag is a
*consistency* problem for reporting, not a correctness problem for payments.

## Diagnose

```bash
kubectl exec -n ags-erp deploy/mariadb-replica -- \
  mysql -e "SHOW REPLICA STATUS\G" | grep -E "Seconds_Behind|Replica_(IO|SQL)_Running|Last_Error"
```

- `Replica_SQL_Running: No` → replication is broken, not lagging. Read
  `Last_Error` and go to the recovery section.
- `Seconds_Behind_Master` climbing steadily → apply cannot keep up.

## Usual causes

1. **The 07:40 attendance write burst.** Expected, and it should clear by 08:15.
   Parallel apply is already configured (`slave_parallel_threads = 8`,
   `slave_parallel_mode = optimistic` in `infra/mariadb/replica.cnf`). If it is
   not clearing, raise threads to 16 and restart the replica.

2. **A long single transaction on the primary.** Row-based replication applies
   it as one unit, so a bulk payroll submit or a large data import serialises.
   Find it on the primary:
   ```sql
   SELECT * FROM information_schema.innodb_trx ORDER BY trx_started LIMIT 5;
   ```
   Batch such imports rather than running them as one transaction.

3. **Replica under-provisioned or thrashing.** Check its buffer pool hit rate;
   the replica has a 22 GB pool against the primary's 44 GB, which is fine for
   reporting but not if someone points heavy ad-hoc analytics at it.

## While it is lagging

Point reporting back at the primary temporarily — slower for everyone, but
consistent:

```json
{ "read_from_replica": 0 }
```

in `sites/erp.ags.edu.sa/site_config.json`, then restart the web tier. Revert
once lag is inside SLO.

## If replication is broken

Do not repoint traffic and hope. Rebuild the replica from a fresh primary
backup — replicas hold no unique data, so this is always safe:

```bash
bench --site erp.ags.edu.sa backup --with-files
# restore onto the replica host, then re-establish replication from the
# recorded GTID position
```
