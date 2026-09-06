# Infrastructure

Sized for **2,500 concurrent users between 07:00 and 15:00**. Every number below
is derived in [`../docs/capacity-model.md`](../docs/capacity-model.md); change it
there first.

```
                    ┌──────────────┐
   internet ───────▶│  nginx  x2   │  TLS, rate limiting, /assets cache
                    └──────┬───────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
  ┌───────────┐     ┌─────────────┐    ┌────────────┐
  │ web x6→10 │     │ socketio x2 │    │ workers x3 │  short / default / long
  │ 17 gunicorn│    │  sticky     │    │  deployments│
  └─────┬─────┘     └──────┬──────┘    └──────┬─────┘
        │                  │                  │      ┌───────────────┐
        └──────────────────┼──────────────────┼─────▶│ scheduler x1  │
                           │                  │      │  EXACTLY ONE  │
                           ▼                  ▼      └───────────────┘
              ┌────────────────────────────────────┐
              │ redis: cache / queue / socketio     │
              └────────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
      ┌────────────────┐        ┌──────────────────┐
      │ MariaDB primary│───────▶│ replicas x2      │  reports, dashboards
      │ 16 vCPU / 64 GB│        │ 8 vCPU / 32 GB   │
      └────────────────┘        └──────────────────┘
```

## Layout

| Path | What |
|---|---|
| `docker/` | Multi-stage image + production-shaped compose stack |
| `k8s/` | 22 resources: deployments, HPAs, PDB, NetworkPolicies, migration Job, backup CronJob |
| `nginx/` | Edge config: TLS, rate limiting, asset caching, websocket upgrade |
| `mariadb/` | Primary and replica tuning |
| `redis/` | Three instances, each with a different job and a different policy |
| `supervisor/` | The same topology for teams on VMs rather than Kubernetes |
| `observability/` | Prometheus scrape config and 16 alert rules, each with a runbook |

## Four decisions that carry the load

**KPI snapshots, not live aggregation.** Executive dashboards read one indexed
row rather than scanning `tabGL Entry`. ~15 ms instead of ~2 s, and at 07:00
dozens of people open dashboards inside the same few minutes (ADR 0004).

**A notification outbox.** Nothing is sent inline, so a slow SMS gateway can
never occupy a gunicorn worker during the attendance rush (ADR 0005).

**Assets served and cached at the edge.** Frappe's bundles are content-hashed,
so nginx serves them `immutable` for a year. Put a CDN in front and roughly 70%
of requests never reach Python at all.

**Row scoping in SQL.** Parent and teacher permissions are subqueries, not
Python id lists — a 2,500-element `IN` clause per list view would dominate every
query plan.

## Three configuration choices that are correctness, not preference

1. **`redis-queue` runs `maxmemory-policy noeviction`.** Under any `allkeys-*`
   policy Redis silently discards queued jobs when memory fills — an unsent fee
   reminder, a lost ZATCA clearance, an invoice never generated, with no error
   raised anywhere. `noeviction` turns that into a loud enqueue failure.

2. **The scheduler is a `StatefulSet` with `replicas: 1`.** A Deployment's
   rolling update briefly runs two pods; for a scheduler that means every job
   fires twice — two overdue-fee SMS to every parent, two late-fee invoices.
   There is a critical alert for this because "impossible" has a way of not
   being.

3. **`innodb_flush_log_at_trx_commit = 1` with `sync_binlog = 1`.** The durable
   pair. This is a school's cash ledger; the throughput cost is accepted
   deliberately so that no committed fee payment is lost on power failure.

## Building the image

```bash
sudo bash scripts/start-docker.sh     # WSL2 does not reliably run systemd
sudo bash scripts/build-image.sh      # writes a full log; reports the real exit status
sudo bash scripts/verify-image.sh     # proves the image is usable, not just built
```

`build-image.sh` exists because `docker build ... | tail` swallows the build's
exit code unless `pipefail` is set — a failed build then looks exactly like a
successful one. That is not hypothetical: the first attempt here appeared to
pass while `bench init` had aborted.

`verify-image.sh` exists because "the build succeeded" is a weak claim. It runs
inside the image and checks the things that can be quietly wrong: the Python
minor version, the Node major version, every app present *and importable*, the
AGS asset bundles actually built, `wkhtmltopdf` and the Noto fonts present, and
that the image does not run as root.

### Two base-image constraints that are not free choices

| | Required | What goes wrong otherwise |
|---|---|---|
| Python | **3.14** exactly | frappe 16 pins `>=3.14,<3.15`. A 3.12 base fails minutes into `bench init` with a uv resolver message that never names the base image. |
| Node | **≥ 24** | frappe's `engines` field. Older Node builds assets with warnings and then fails at runtime in socketio — much harder to diagnose than a build error. Needed in the runtime stage too, since socketio runs there. |
| Debian | bookworm | `wkhtmltopdf` renders every invoice and payslip and is absent from newer Debian. |

## Deploying

Migrations run as their own Job **before** the rollout — never as an
initContainer on a multi-replica Deployment, where six pods would race
`bench migrate` against one site.

```bash
kubectl -n ags-erp delete job ags-migrate --ignore-not-found
kubectl -n ags-erp apply -f k8s/40-migrate-job-netpol.yaml
kubectl -n ags-erp wait --for=condition=complete job/ags-migrate --timeout=30m
kubectl -n ags-erp set image deployment/ags-web frappe=ags/edusmart-erp:<tag>
kubectl -n ags-erp rollout status deployment/ags-web
```

The web tier rolls with `maxUnavailable: 0`: the peak window has no spare
capacity to absorb a missing node.

## Proving the capacity claim

```bash
k6 run -e BASE_URL=https://erp-staging.ags.edu.sa \
       -e PARENT_PASSWORD=... -e TEACHER_PASSWORD=... \
       ../load-tests/k6/school-day.js
```

The script replays the shape of a real day — the 07:40 attendance rush, the
mid-morning plateau, the month-start parent surge — and its thresholds are the
SLOs from the capacity model, so a run that breaches them fails. Run it before
every capacity change; a capacity claim nobody re-tests quietly rots.

The parent cohort uses a **constant arrival rate**, not constant VUs, on
purpose: parents arrive independently, so if the app slows they pile up rather
than politely waiting their turn. That is what exposes a capacity cliff instead
of hiding it behind closed-loop backpressure.

## When something is wrong

Every alert in `observability/alerts.yml` names a runbook in
[`../docs/runbooks/`](../docs/runbooks). Start there rather than in the logs —
the runbooks are ordered by what is actually most likely.
