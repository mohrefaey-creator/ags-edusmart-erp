# AGS EduSmart ERP

A school-focused ERP for the AGS Education Group, built as an application layer
over Frappe 16, ERPNext 16, Frappe HR and Frappe Education — the architecture the
handover (`AGS_EduSmart_ERP_SKILL.md`) specifies.

It is a running system, not a scaffold. The fee engine prices the handover's own
worked example to the riyal, invoices post to a real general ledger, and the
parent portal serves a real consolidated statement.

```
School ERP/
├── apps/ags_edusmart/     the AGS application (40 DocTypes, 12 modules)
├── infra/                 production topology for 2,500 concurrent users
├── load-tests/            k6 profile that replays a school day
├── docs/                  capacity model, ADRs, runbooks
├── tools/                 DocType generator and spec files
└── scripts/               bench sync, portal smoke check
```

## What it does

The rule throughout is **reuse the native DocType**. There is no chart of
accounts here, no stock ledger, no payroll calculation — ERPNext and Frappe HR
already do those, and do them better than a rewrite would. What this app adds is
what a Saudi multi-campus school group needs and the upstream apps do not have:

| Module | Adds |
|---|---|
| `ags_core` | Campus and School Division masters, campus row-scoping, settings |
| `ags_fees` | Payer accounts, student fee plans, the discount engine, installment invoicing, waivers |
| `ags_collections` | Collection cases, AR ageing buckets, the reminder ladder |
| `ags_procurement` | Commitment accounting, quotation comparison, three-way match exceptions |
| `ags_inventory` | Department Issue — school language over `Stock Entry` |
| `ags_assets` | Asset handover with digital acknowledgement, custody enforcement at separation |
| `ags_hr` | Saudi identifiers, document-expiry tracking, GOSI components |
| `ags_approvals` | One configurable approval matrix for every module |
| `ags_dashboards` | KPI definitions, snapshot engine, role-scoped reads |
| `ags_notifications` | Durable outbox across In-App / Email / SMS / WhatsApp |
| `ags_localization` | ZATCA hash chain, TLV QR, UBL generation, clearance archive |

## The parts worth reading first

**The fee engine** (`ags_fees/discounts.py`, `ags_fees/doctype/ags_fee_plan/`).
Discounts are eligible **per fee component**, so "second child: 10% tuition only"
leaves books, registration and transport untouched. Rules run in priority order,
each seeing the net the previous one left, so two stacked 10% rules take 19% and
not 20%. Anything above its approval threshold lands as *Pending Approval* and
does not reduce the payable until a human signs it off.

Verified against the handover's own numbers (§17.3, §17.6):

```
Grade 5, 2026/27      gross 24,500
second child          − 2,000   (10% of tuition 20,000, nothing else)
                        ───────
net payable             22,500   →  3 term installments of 7,500
```

**Commitment accounting** (`ags_procurement/commitments.py`). ERPNext's budget
check only sees actuals, so a department can approve five requests against the
same remaining SAR 50,000 and find out when the invoices land. This keeps a side
ledger of what is *promised* — and deliberately never posts it to the GL, because
a commitment is not an accounting event (ADR 0002).

**The approval matrix** (`ags_approvals/engine.py`). One engine, cumulative
thresholds. SAR 30,000 needs department head **and** finance **and** principal,
matching §8.3 exactly. What it gates is the consequence, not the submission —
see ADR 0006 for why that distinction matters to the audit trail.

## Running it

The bench lives in WSL; this repository is the source of truth and syncs into it.

```bash
bash scripts/sync-app.sh
```

```bash
wsl -d Ubuntu-26.04 -u frappe -- bash -lc \
  'cd ~/frappe-bench && bench --site ags.localhost migrate'
```

Build the reference dataset — the AGS Jeddah/Riyadh group, the Grade 5 fee
structure, one payer with three children, and the sibling discount tiers:

```bash
wsl -d Ubuntu-26.04 -u frappe -- bash -lc \
  'cd ~/frappe-bench && bench --site ags.localhost execute ags_edusmart.setup.demo.build'
```

Then serve it:

```bash
wsl -d Ubuntu-26.04 -u frappe -- bash -lc \
  'cd ~/frappe-bench && bench --site ags.localhost serve --port 8000'
```

- Desk: `http://localhost:8000/app` — `Administrator`
- Parent portal: `http://localhost:8000/parent`

`bench --site ags.localhost execute ags_edusmart.setup.demo.create_portal_users`
creates the demo parent login. It refuses to run outside a development site, so
it cannot create a weak account in production by accident.

## Verifying it

```bash
# 30 tests: fee arithmetic, installment reconciliation, ledger posting,
# commitment accounting, approval ladders, ZATCA encoding, grade parsing
wsl -d Ubuntu-26.04 -u frappe -- bash -lc \
  'cd ~/frappe-bench && bench --site ags.localhost run-tests --app ags_edusmart'

# portal reachability, scope isolation, page rendering
bash scripts/smoke-portal.sh
```

The smoke check includes the two negative cases that matter: an anonymous caller
is refused, and a signed-in parent asking about a child who is not theirs is
refused.

## Infrastructure

Sized for **2,500 concurrent users, 07:00–15:00**, with the arithmetic written
down in [`docs/capacity-model.md`](docs/capacity-model.md) rather than asserted.
Summary: 6 web nodes autoscaling to 10, split background workers, exactly one
scheduler, a 16 vCPU MariaDB primary with two read replicas, and three Redis
instances. See [`infra/README.md`](infra/README.md).

The capacity claim is falsifiable: `load-tests/k6/school-day.js` replays the
shape of a real day — the 07:40 attendance rush, the mid-morning plateau, the
month-start parent surge — and fails the run if the SLOs are breached.

## Documentation

- [`docs/capacity-model.md`](docs/capacity-model.md) — the sizing arithmetic
- [`docs/adr/`](docs/adr) — why the design is what it is (7 decisions)
- [`docs/runbooks/`](docs/runbooks) — 9 runbooks, one per alert
- [`apps/ags_edusmart/README.md`](apps/ags_edusmart/README.md) — the app itself

## Two upstream behaviours worth knowing

Both cost real debugging time and are documented at the call site:

1. **ERPNext enqueues accounting-dimension field creation to a background
   worker.** On a bench with no running worker the Accounting Dimension row
   exists and its columns do not; the symptom is
   `Unknown column 'campus' in 'SELECT'` raised from ERPNext's own budget
   validation on any GL posting. `setup/dimensions.py` therefore calls the field
   maker synchronously. See ADR 0007.

2. **ERPNext v16 restructured `Budget`.** `account` and `budget_amount` moved
   onto the Budget itself, the `Budget Account` child table is gone, and the
   single `fiscal_year` field became a from/to range. `commitments.py` handles
   both shapes, because a silently-zero budget would disable the budget check
   entirely rather than erroring.
