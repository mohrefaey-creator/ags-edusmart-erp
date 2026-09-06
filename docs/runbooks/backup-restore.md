# Runbook — backup and restore

## What is backed up

The nightly CronJob (`infra/k8s/40-migrate-job-netpol.yaml`, 01:15 Riyadh) runs
Frappe's own backup with `--with-files`, so the artefact restores with
`bench restore` rather than a bespoke script. It covers the database plus public
and private files: admission documents, supplier quotations, expense receipts,
generated invoice PDFs.

`site_config.json` holds the **encryption key**. Without it, encrypted fields
(ZATCA certificates and secrets, integration passwords) cannot be decrypted from
a restored database. Store it in the secret manager, separately from the backup.
A database backup alone is not a complete recovery.

## Verify a backup is real

An untested backup is a hypothesis. Monthly:

```bash
bench new-site restore-test.localhost --db-root-password "$DB_ROOT_PASSWORD"
bench --site restore-test.localhost restore /path/to/backup.sql.gz \
  --with-public-files /path/to/files.tar \
  --with-private-files /path/to/private-files.tar
bench --site restore-test.localhost migrate
bench --site restore-test.localhost run-tests --app ags_edusmart
bench drop-site restore-test.localhost --db-root-password "$DB_ROOT_PASSWORD"
```

Running the app's own suite against the restored site is the check that matters:
it re-derives the fee arithmetic from real data rather than just confirming the
tables exist.

## Restore into production

1. **Stop writes.** A restore under live traffic produces a database matching
   neither the backup nor production.
   ```bash
   kubectl -n ags-erp scale deployment ags-web ags-worker-short \
     ags-worker-default ags-worker-long --replicas=0
   kubectl -n ags-erp scale statefulset ags-scheduler --replicas=0
   ```
2. Restore, then `bench migrate`.
3. **Reconcile before reopening.** The ledger must balance before cashiers are
   let back in:
   ```sql
   SELECT SUM(debit) - SUM(credit) FROM `tabGL Entry` WHERE is_cancelled = 0;
   ```
   It must be zero.
4. Verify the ZATCA chain (`zatca-failures.md`) — invoices cleared after the
   backup point will be missing from the archive.
5. Scale back up. Scheduler **last**, and to exactly one.

## Recovery objectives

| | Target |
|---|---|
| RPO | 24 h from the nightly backup; < 5 min with binlog replay |
| RTO | 2 h |

Binary logging is on with `sync_binlog = 1`, so point-in-time recovery between
nightly backups is possible. That is the difference between losing a day of fee
payments and losing minutes.
