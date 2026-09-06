# Runbook — ZATCA clearance failing

## What is and is not at risk

Invoices still post. The GL is correct. What has stopped is *clearance* with the
tax authority.

The hash chain is the thing to protect. Each `AGS ZATCA Invoice Log` row carries
the previous invoice's hash (PIH) and a monotonic counter (ICV). That chain is
what makes tampering detectable, and it is built at submit time — before any
network call. So a gateway outage does not corrupt it; it only delays clearance.

`block_on_failure` is off by default deliberately: a ZATCA outage must not stop
a cashier taking a parent's payment.

## Diagnose

```sql
SELECT status, COUNT(*), MAX(creation)
FROM `tabAGS ZATCA Invoice Log`
WHERE creation > NOW() - INTERVAL 2 DAY
GROUP BY status;

SELECT sales_invoice, attempts, LEFT(error, 300)
FROM `tabAGS ZATCA Invoice Log`
WHERE status = 'Failed' ORDER BY creation DESC LIMIT 20;
```

Read the actual `error` text before doing anything. The common ones:

| Error | Meaning | Action |
|---|---|---|
| 401 / 403 | certificate or secret wrong/expired | rotate credentials in AGS ZATCA Settings |
| 400 with validation detail | the UBL does not satisfy the current spec | see below |
| timeout / 5xx | ZATCA side | wait; the queue retries with backoff |

## Certificate expiry

Compliance and production certificates expire. Rotate in **AGS ZATCA Settings**
(`production_certificate` / `production_secret` are Password fields, so they are
encrypted at rest and never appear in a backup as plaintext).

## Validation failures after a ZATCA spec change

`ags_localization/zatca.py` deliberately keeps the endpoint and credentials in
configuration rather than code, because SKILL sec. 25.1 requires following the
requirements current at development time rather than stale hardcoded rules. A
schema change is therefore a code change to `build_ubl`, not a config change.

Re-generating is safe: the archive row is keyed uniquely on `sales_invoice`, and
`generate_archive_row` returns the existing row rather than re-chaining.

## Verify the chain before and after any repair

```bash
bench --site erp.ags.edu.sa execute \
  ags_edusmart.ags_localization.zatca.verify_chain \
  --kwargs "{'company': 'AGS Education Group'}"
```

`{"ok": true}` means every row's `previous_hash` matches its predecessor's
`invoice_hash`. If it reports a break, **stop and escalate to finance** — do not
rewrite hashes to make it pass. A broken chain is a reportable fact, not a bug
to be patched away.

## Drain the backlog

```bash
bench --site erp.ags.edu.sa execute ags_edusmart.ags_localization.zatca.submit_queued
```

Rows that exhausted `max_retries` sit at `Failed`; reset them to `Queued` once
the cause is fixed.
