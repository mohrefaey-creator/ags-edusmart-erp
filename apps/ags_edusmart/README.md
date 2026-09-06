# AGS EduSmart ERP — `ags_edusmart`

The AGS-specific layer of the AGS EduSmart ERP. It runs **on top of** Frappe,
ERPNext, Frappe HR and Frappe Education and does not replace any of them.

## What lives here, and what deliberately does not

The governing rule (handover §31, §39.1) is: reuse the native DocType wherever
mature functionality already exists. So this app contains no chart of accounts,
no stock ledger, no payroll calculation and no attendance engine. It contains the
things the Frappe ecosystem does *not* provide for a Saudi multi-campus school
group:

| Module | What it adds |
|---|---|
| `ags_core` | Campus and School Division masters, campus row-scoping, AGS Settings |
| `ags_fees` | Payer accounts, student fee plans, the discount engine, installment invoicing, waivers |
| `ags_collections` | Collection cases, AR ageing buckets, the reminder ladder |
| `ags_procurement` | Commitment accounting, quotation comparison, three-way match exceptions |
| `ags_inventory` | Department Issue (school-facing wrapper over Stock Entry) |
| `ags_assets` | Asset handover with digital acknowledgement, custody enforcement |
| `ags_hr` | Saudi identifiers, document-expiry tracking, GOSI components |
| `ags_approvals` | One configurable approval matrix for every module |
| `ags_dashboards` | KPI definitions, snapshot engine, role-scoped dashboard reads |
| `ags_notifications` | Durable outbox across In-App / Email / SMS / WhatsApp |
| `ags_localization` | ZATCA hash chain, TLV QR, UBL generation, clearance archive |
| `ags_ai` | 21 permission-scoped analyzers, bilingual question routing, driver decomposition |

## Architectural commitments

**One accounting engine.** Nothing here posts its own GL entries. A fee invoice
is a `Sales Invoice`, a waiver is a return invoice, a department issue is a
`Stock Entry`, a handover is an `Asset Movement`. Budget commitments are a *side*
ledger and are explicitly excluded from the GL.

**One stock ledger.** Department Issue posts Material Issue and reads
availability from `Bin`; it never maintains its own quantities.

**Student identity is separate from payer identity.** `AGS Payer Account` owns
the receivable and carries one `Customer`, which is what lets three siblings
consolidate onto one statement.

**Discounts are per component, ordered, and threshold-gated.** See
`ags_fees/discounts.py` — eligibility is by fee category, rules run by priority
each seeing the net left by the last, and anything above its tier lands as
*Pending Approval* rather than silently reducing the payable.

**Dashboards read snapshots, not live aggregates.** At the 07:00–15:00 peak a
live KPI would be a full scan of `GL Entry` per viewer. One background pass
computes each scope; readers do one indexed lookup.

## Regenerating DocTypes

Schema is generated from specs so ~40 DocTypes stay consistent:

```bash
python tools/generate.py
```

Edit `tools/specs_*.py`, re-run, commit the JSON diff. Controllers on disk are
never overwritten.

## Development

The repository is the source of truth; the bench holds a working copy:

```bash
bash scripts/sync-app.sh
```

Then, inside the bench:

```bash
bench --site ags.localhost migrate
bench --site ags.localhost run-tests --app ags_edusmart
```

## The AI layer

21 analyzers answering the questions named in handover §28, each computing its
numbers from the ledger. A language model is optional, off by default, and may
only rephrase a finished result — see [ADR 0008](../../docs/adr/0008-ai-computes-nothing.md).

```bash
bench --site ags.localhost execute ags_edusmart.ags_ai.api.briefing
```

Routing is deterministic and bilingual. Below a confidence floor it returns the
questions it *can* answer rather than guessing:

```
0.85  overdue_by_campus      <- which campus has the highest overdue balance
0.81  margin_drivers         <- why did operating margin decrease
0.85  long_overdue_payers    <- which parents are more than 90 days overdue
0.53  expiring_documents     <- متى تنتهي الإقامة
0.00  NO MATCH               <- how do I bake a cake
```

Every question, including refusals, lands in `AGS AI Query Log`.

## Arabic

`translations/ar.csv` is generated, not hand-edited:

```bash
python tools/build_translations.py          # rebuild + validate
python tools/build_translations.py --check  # CI gate
```

Coverage is 100% of 961 strings and is enforced by `tests/test_translations.py`,
which fails if a new DocType label has no entry. Terminology decisions are
recorded in [ADR 0009](../../docs/adr/0009-arabic-terminology.md).

To see the portal in Arabic, set a user's language:

```bash
bench --site ags.localhost execute frappe.client.set_value   --kwargs "{'doctype':'User','name':'mohamed.ahmed@example.com','fieldname':'language','value':'ar'}"
```

## Bilingual / RTL note

Identifier-shaped values are wrapped in `.code`, which sets both `direction: ltr`
and `unicode-bidi: isolate`. Isolation alone is not enough — without an explicit
direction the run still inherits RTL and `1-A` still renders as `A-1`. The class
must not be applied to a slot that can hold prose, nor to formatted currency.
