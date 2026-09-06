# Version lock

The exact upstream commits this deployment was built and tested against.
Regenerate with `bash scripts/capture-versions.sh` and commit the diff.

## Why pin to a commit, not a branch

`version-16` moves. An ERP that reprices fees differently after an unattended
`bench update` is worse than one that is a month behind, and the failure would
surface as a parent disputing an invoice rather than as a red build. The
deployment repo therefore records what it was built against; upgrades are a
deliberate commit to this file, reviewed like any other change.

## Locked as of 2026-09-06

| App | Version | Commit | Branch |
|---|---|---|---|
| frappe | 16.33.0 | `33bf510b17afcaaa857ed38b921d8e9e50dcd232` | version-16 |
| erpnext | 16.34.1 | `0b50853985312bc64977f9324c55b5d8c1ab2e59` | version-16 |
| hrms | 16.17.1 | `e1481b5cd038657d82357d91a2d81cc84c707016` | version-16 |
| education | 16.0.1 | `93bc7075753369457919720690f80c6d2207b5f2` | version-16 |
| payments | 0.0.1 | `cca07d9f9392e2ea0e521c5975151db9e4b6c321` | version-16 |
| **ags_edusmart** | 1.0.0 | *(this repo's sibling — see `apps.json`)* | main |

## Runtime

These are constraints, not preferences. Both were found by a build failing.

| | Version | Why exactly this |
|---|---|---|
| **Python** | **3.14** | `frappe/pyproject.toml` pins `requires-python = ">=3.14,<3.15"` — an unusually tight range. A 3.12 base fails minutes into `bench init` with a uv resolver message that never names the base image as the cause. Ubuntu 26.04 ships 3.14.4, so the WSL bench works by luck; the container image had to be corrected. |
| **Node** | **≥ 24** | `frappe/package.json` declares `engines: {node: ">=24"}`. Older Node builds assets with warnings and then fails at runtime in socketio — much more expensive to diagnose than a build error. Needed in the runtime image too, not just the builder, because socketio runs there. |
| Debian | bookworm | `wkhtmltopdf` renders every fee invoice and payslip and is not packaged in newer Debian releases. |
| MariaDB | 11.8.6 | utf8mb4 required — see `infra/mariadb/primary.cnf` |
| Redis | 7 | three instances; see `infra/redis/` |

## Licensing note

`education`, `erpnext`, `hrms` and `frappe` are GPL/AGPL-family. `ags_edusmart`
is MIT and does not modify or redistribute their source — it is a separate app
installed alongside them, which is the arrangement the Frappe app model is
designed for. **Frappe CRM is deliberately excluded** from this stack on AGPL-3.0
grounds; nothing here depends on it.

## Upgrade procedure

1. Update a single app's commit in `apps.json` and this file.
2. `bash scripts/bootstrap.sh --site staging.localhost` on a clean box.
3. `bench --site staging.localhost run-tests --app ags_edusmart` — all 56 must pass.
4. `bash scripts/smoke-portal.sh` against the staging URL.
5. `k6 run load-tests/k6/school-day.js` — the SLOs in `docs/capacity-model.md`
   are the gate.
6. Only then promote. Never upgrade more than one upstream app at a time: when
   something breaks you want to know which one did it.
