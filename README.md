# AGS EduSmart ERP — deployment

This is the **deployment repository**: it defines the stack, pins its versions,
builds it from nothing, and runs it. It contains no application code.

The system is two repositories, which is how the Frappe app model expects a
custom app to live (handover §3):

| Repo | Contains | Where |
|---|---|---|
| **This one** | Stack definition, infrastructure, capacity model, runbooks, load tests, bootstrap | `School ERP/` |
| **[`ags_edusmart`](apps/ags_edusmart)** | The AGS application — 42 DocTypes, 12 modules, 56 tests | `School ERP/apps/ags_edusmart/` |

They are independent git repositories. This one deliberately does **not** track
`apps/`: `apps.json` records which apps the stack is built from and at which
commit, and `scripts/bootstrap.sh` fetches them. The AGS app sits here as a
working checkout so bootstrap can install it without a network round-trip.

```
School ERP/
├── apps.json                stack definition — every app, pinned to a commit
├── apps/ags_edusmart/       the app repo (separate git history)
├── infra/                   nginx, MariaDB, Redis, Docker, k8s, observability
├── docs/                    capacity model, 9 ADRs, 9 runbooks, version lock
├── load-tests/              k6 profile replaying a school day
└── scripts/                 bootstrap, dev bring-up, verify, smoke check
```

## The stack

Nothing upstream is modified. Frappe, ERPNext, HRMS and Education run as
shipped; the AGS layer is a separate app installed alongside them.

| App | Version | Role |
|---|---|---|
| frappe | 16.33.0 | platform |
| erpnext | 16.34.1 | GL, procurement, stock, assets |
| hrms | 16.17.1 | employee, attendance, leave, payroll |
| education | 16.0.1 | student, guardian, enrollment, fee structure |
| payments | 0.0.1 | payment gateway plumbing |
| **ags_edusmart** | 1.0.0 | the AGS layer |

Exact commits are in [`docs/versions.lock.md`](docs/versions.lock.md). They are
pinned to a **commit, not a branch**: an ERP that reprices fees differently after
an unattended `bench update` is worse than one that is a month behind.

## Build it from nothing

```bash
sudo bash scripts/bootstrap.sh
```

Installs system dependencies, tunes MariaDB for utf8mb4, initialises a bench,
fetches every app at its pinned commit, creates the site, installs the AGS layer
and migrates. Idempotent — a re-run after a failure picks up where it stopped.

Then serve it:

```bash
bash scripts/start-dev.sh
```

- Desk: `http://localhost:8000/app` — `Administrator` / `dev-admin-not-real`
- Parent portal: `http://localhost:8000/parent`

Reference dataset — AGS Jeddah/Riyadh, the Grade 5 fee structure, one payer with
three children, the sibling discount tiers, and a part-paid invoice:

```bash
bench --site ags.localhost execute ags_edusmart.setup.demo.build
bench --site ags.localhost execute ags_edusmart.setup.demo.run_finance_journey
```

## Verify it

```bash
bash scripts/verify.sh
```

Runs everything that can fail: generated schema still matches its specs,
translation coverage and placeholder integrity, the full test suite against a
live site, and the portal end to end including its two negative cases
(anonymous refused, foreign student refused).

## Development loop

The app repo is the source of truth; the bench holds a working copy.

```bash
bash scripts/sync-app.sh                              # repo -> bench
bench --site ags.localhost migrate
bench --site ags.localhost run-tests --app ags_edusmart
```

## What the app does

The rule throughout is **reuse the native DocType**. There is no chart of
accounts here, no stock ledger, no payroll calculation. What the AGS layer adds
is what a Saudi multi-campus school group needs and the upstream apps do not
have — the fee engine, payer accounts, commitment accounting, one approval
matrix, ZATCA, and a permission-scoped analysis layer. See
[`apps/ags_edusmart/README.md`](apps/ags_edusmart/README.md).

The fee engine reproduces the handover's own worked example (§17.3, §17.6):

```
Grade 5, 2026/27      gross 24,500
second child          − 2,000   (10% of tuition 20,000, nothing else)
                        ───────
net payable             22,500   →  3 term installments of 7,500
```

## Infrastructure

Sized for **2,500 concurrent users, 07:00–15:00**, with the arithmetic written
down in [`docs/capacity-model.md`](docs/capacity-model.md) rather than asserted:
6 web nodes autoscaling to 10, background workers split by queue, exactly one
scheduler, a 16 vCPU MariaDB primary with two read replicas, three Redis
instances. See [`infra/README.md`](infra/README.md).

The capacity claim is falsifiable — `load-tests/k6/school-day.js` replays the
attendance rush, the mid-morning plateau and the month-start parent surge, and
fails the run if the SLOs are breached.

**Not yet exercised:** the container image has not been built, the Kubernetes
manifests have not been applied to a cluster, and the k6 profile has not been
run. They are written and syntax-validated; treat the capacity numbers as a
model until that changes.

## Documentation

- [`docs/capacity-model.md`](docs/capacity-model.md) — the sizing arithmetic
- [`docs/versions.lock.md`](docs/versions.lock.md) — pinned commits, upgrade procedure
- [`docs/adr/`](docs/adr) — 9 decisions and why
- [`docs/runbooks/`](docs/runbooks) — 9 runbooks, one per alert
- [`apps/ags_edusmart/README.md`](apps/ags_edusmart/README.md) — the application

## Three upstream behaviours worth knowing

Each cost real debugging time and is documented at the call site:

1. **ERPNext enqueues accounting-dimension field creation to a background
   worker.** On a bench with no running worker the Accounting Dimension row
   exists and its columns do not; the symptom is
   `Unknown column 'campus' in 'SELECT'` raised from ERPNext's own budget
   validation on any GL posting. `setup/dimensions.py` calls the field maker
   synchronously. See ADR 0007.

2. **ERPNext v16 restructured `Budget`.** `account` and `budget_amount` moved
   onto the Budget itself, the `Budget Account` child table is gone, and the
   single `fiscal_year` field became a from/to range. `commitments.py` handles
   both shapes, because a silently-zero budget would disable the budget check
   entirely rather than erroring.

3. **Frappe 16 pins Python to `>=3.14,<3.15` and Node to `>=24`.** Neither is a
   preference. A `python:3.12` base image fails minutes into `bench init` with a
   uv resolver message that never names the base image as the cause, and older
   Node builds assets with warnings then fails at runtime in socketio. Both are
   recorded in [`docs/versions.lock.md`](docs/versions.lock.md) and enforced at
   the top of the Dockerfile.
