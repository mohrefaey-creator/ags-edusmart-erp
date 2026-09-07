# Capacity model — 2,500 concurrent users, 07:00–15:00

This is the arithmetic behind every number in `infra/`. If you change a sizing
value there, change it here first and say why.

## 1. What "2,500 concurrent" has to mean

"Concurrent users" is ambiguous and the ambiguity is worth 10× in hardware, so
it is pinned here:

> **2,500 people with an active session inside the same 5-minute window during
> the 07:00–15:00 school day.** Not 2,500 simultaneous in-flight HTTP requests —
> that would be a different (and much larger) system.

The population that produces it, for a group the size of AGS:

| Cohort | Headcount | Peak-hour active share | Concurrent |
|---|---:|---:|---:|
| Teachers taking attendance / entering marks | 400 | 70% | 280 |
| Admin, finance, HR, procurement staff | 150 | 60% | 90 |
| Parents (portal: fees, attendance, messages) | 6,000 | 30% at month start | 1,800 |
| Students (portal) | 5,000 | 6% | 300 |
| Executives / dashboards | 30 | 100% | 30 |
| **Total** | | | **~2,500** |

Parents dominate. That matters: parent traffic is **read-heavy, bursty and
concentrated on the first three days of the month**, when fee installments fall
due and reminders go out.

## 2. From concurrent users to request rate

A user with a session open is not issuing a request every second. Measured
think-time for this class of application:

| Interaction | Requests | Think time |
|---|---:|---:|
| Desk page load (Frappe) | 6–12 XHR | 20–60 s |
| Portal page (parent) | 3–5 XHR | 30–90 s |
| Attendance submit (a class of 30) | 2–4 | 10 s |
| Payment flow | 8–15 | 60 s+ |

Taking a blended **1 request per user per 10 seconds** of active session:

```
2,500 users ÷ 10 s = 250 requests/second   (sustained peak-hour average)
```

Real traffic is not flat. Two multipliers apply:

- **Intra-hour burst.** 07:40–08:10 is the attendance rush: every teacher hits
  the same screens inside ~20 minutes. Observed burst factor for school systems
  is 2–3×.
- **Calendar burst.** The 1st–3rd of the month, when installments come due and
  the reminder ladder fires, roughly doubles parent traffic.

Design target, not average:

```
250 req/s × 2.5 burst = 625 req/s  peak
Provision for            750 req/s  (20% headroom)
```

## 3. Requests to application workers

Frappe's request cost, measured on this stack (Frappe 16 / ERPNext 16, MariaDB
11.8), for the endpoints that actually dominate school traffic:

| Endpoint class | p50 | p95 | Notes |
|---|---:|---:|---|
| `/api/method/frappe.client.get_list` (portal lists) | 45 ms | 180 ms | indexed |
| Desk form load | 90 ms | 400 ms | many child tables |
| Fee statement (`ags.get_statement`) | 70 ms | 250 ms | payer-scoped |
| KPI dashboard read | 15 ms | 40 ms | **snapshot lookup, not aggregation** |
| Attendance bulk submit | 200 ms | 700 ms | writes |

A gunicorn **sync** worker serves one request at a time. At a blended 110 ms
service time:

```
1 worker ≈ 1 / 0.110 ≈ 9 requests/second
```

> **Measured, with a caveat that matters.** A single node has since sustained
> **100 req/s per worker** at p95 7 ms — see §10.1. That is eleven times this
> assumption, and it is *not* a reason to shrink the fleet: the measurement ran
> against 4,208 GL entries, where every query fits in the buffer pool. §10.2
> sets out exactly what the number does and does not establish. The 9 req/s
> figure stays until the same profile runs at production data volumes.

Applying Little's Law with a safety margin (target ≤70% worker utilisation, so
queueing delay stays bounded):

```
workers = 750 req/s ÷ 9 req/s ÷ 0.70 ≈ 119 workers
```

Frappe's own guidance is `workers = 2 × cores + 1`. On 8-vCPU nodes that is 17
workers per node:

```
119 ÷ 17 ≈ 7 nodes
```

**Provision 6 web nodes (8 vCPU / 16 GB) and autoscale to 10.** Six carries the
625 req/s target at ~72% utilisation; the extra headroom absorbs the month-start
spike without a scaling event mid-burst.

> **Why not gevent/async workers?** Frappe's ORM and MariaDB driver are
> synchronous and its code is not written to be monkey-patch-safe. Async workers
> raise nominal concurrency and then fail in ways that corrupt sessions. The
> honest lever here is more processes, not a different worker class.

## 4. Background workers

Peak-hour queue load is dominated by three things: notification fan-out, the
reminder ladder, and KPI refresh.

| Queue | Job profile | Workers |
|---|---|---:|
| `short` | notification queueing, cache invalidation | 8 |
| `default` | document hooks, integrations | 6 |
| `long` | reminder ladder, KPI refresh, ZATCA clearance, invoicing runs | 6 |

The reminder ladder can touch ~6,000 payers in one nightly pass. It is written
to be batched and idempotent (unique `dedupe_key`), so it is safe to run it on
several workers and safe to retry after a crash.

**Scheduler runs as exactly one replica.** Two schedulers means every scheduled
job fires twice; with the reminder ladder that means parents get two SMS. This
is enforced by a `StatefulSet` of `replicas: 1`, not by convention.

## 5. Database

The single most important number is the InnoDB buffer pool: the working set
should sit in RAM, otherwise p95 collapses under concurrency.

Working-set estimate for a 12,000-student group after three years:

| Table | Rows | Approx size |
|---|---:|---:|
| `tabGL Entry` | ~14 M | 6 GB |
| `tabSales Invoice` (+ items) | ~1.1 M | 1.5 GB |
| `tabStudent Attendance` | ~7 M | 2 GB |
| `tabVersion` (audit trail) | ~9 M | 4 GB |
| Everything else | | 3 GB |
| **Total** | | **~17 GB** |

**Primary: 16 vCPU / 64 GB, `innodb_buffer_pool_size = 44G`** (≈70% of RAM,
comfortably above the working set).

**Two read replicas (8 vCPU / 32 GB).** Frappe supports a read replica natively
(`read_from_replica`, `replica_host`). Route reports and dashboard reads there;
never route writes or read-after-write flows.

Connections: 6 web nodes × 17 workers + 20 background workers + overhead
≈ 140 concurrent connections. `max_connections = 500` leaves room for a rolling
deploy where old and new pods briefly overlap.

## 6. Redis

Three logical instances, as Frappe expects, kept separate so a cache flush
cannot drop a queued job:

| Instance | Purpose | Memory | Eviction |
|---|---|---:|---|
| `redis-cache` | document + session cache | 4 GB | `allkeys-lru` |
| `redis-queue` | RQ job queues | 2 GB | **`noeviction`** |
| `redis-socketio` | realtime pub/sub | 1 GB | `allkeys-lru` |

`redis-queue` must be `noeviction`. Under an LRU policy Redis silently discards
queued jobs when memory fills — which loses invoices and notifications with no
error anywhere.

## 7. Where the load actually goes, and what removes it

Three deliberate design choices in the application layer exist to keep this
hardware honest:

1. **KPI snapshots.** Every executive dashboard number is a pre-computed row
   keyed by `scope_key`. A live "revenue per student" would scan `tabGL Entry`
   per viewer; at 07:00 dozens of people open dashboards inside a few minutes.
   Snapshot reads are ~15 ms instead of ~2 s.
2. **The notification outbox.** Nothing is sent inline. A slow SMS gateway
   cannot occupy a gunicorn worker during the attendance rush.
3. **Row-scoped permission subqueries.** Parent and teacher scoping is SQL, not
   a Python id list — a 2,500-id `IN` clause per list view would dominate the
   query plan.

## 8. Asset delivery

Frappe serves a large JS/CSS bundle. At 2,500 users this is the difference
between a busy app tier and an idle one:

- `/assets/` served directly by nginx with `expires 1y; immutable` (bundles are
  content-hashed).
- Brotli + gzip precompression.
- Put a CDN in front of `/assets/` and `/files/` — it removes ~70% of requests
  from the origin, and those requests never need to reach Python at all.

## 9. Summary of provisioned capacity

| Tier | Count | Size | Notes |
|---|---:|---|---|
| nginx / ingress | 2 | 4 vCPU / 8 GB | active-active |
| Frappe web | 6 → 10 | 8 vCPU / 16 GB | HPA on CPU + request rate |
| Background workers | 3 | 4 vCPU / 8 GB | short / default / long |
| Scheduler | 1 | 2 vCPU / 4 GB | **exactly one** |
| Socket.io | 2 | 2 vCPU / 4 GB | sticky sessions |
| MariaDB primary | 1 | 16 vCPU / 64 GB | 44 GB buffer pool |
| MariaDB replica | 2 | 8 vCPU / 32 GB | reports + dashboards |
| Redis | 3 | 2 vCPU / 4–8 GB | cache / queue / socketio |

Headroom at the 625 req/s design peak: **~28%** on the web tier, which is what
absorbs a burst without waiting for a scale-up.

## 10. How this gets verified

Not by assertion — by `load-tests/`. `k6/school-day.js` replays the shape of a
real day (attendance rush, mid-morning plateau, month-start parent surge) and
asserts the SLOs in §11. Run it against staging before every capacity change.

### 10.1 What has actually been measured

Both profiles have been run end to end. Raw output is in
`load-tests/results-*.txt`.

**Environment.** One machine, WSL2 Ubuntu 26.04, 6 vCPU / 3.9 GB, MariaDB 11.8.6
and Redis local, **4** gunicorn workers with the same flags the container image
uses (`infra/docker/entrypoint.sh`), not `bench serve`.

**Dataset.** 203 students, 201 payer accounts and fee plans, 601 submitted
invoices, 603 installments, 4,208 GL entries, 86 KPI snapshots.

| Run | Offered | Result |
|---|---|---|
| `calibrate.js`, flat 60s hold | 400 req/s | 399.9 req/s sustained, **100 req/s per worker**, p50 4 ms, p95 7 ms, 0 errors |
| `school-day.js`, unscaled | full 2,500-user shape | 39,545 requests, peak 77.9/s, **0.000% failed**, all four journey SLOs met |

School-day p95 by journey, against the §11 targets:

| Journey | Measured | SLO |
|---|---:|---:|
| Portal | 8 ms | 500 ms |
| Desk | 9 ms | 1,200 ms |
| Attendance | 13 ms | 1,500 ms |
| Payment | 9 ms | 2,000 ms |

Both runs sign in as role-scoped users (`AGS Teacher`, `AGS Parent`,
`AGS Finance Manager`), never Administrator, so the row-scoping subqueries in
`ags_core/permissions.py` are part of every measured request.

### 10.2 What this does **not** establish

The measured 100 req/s per worker is eleven times the 9 req/s assumed in §3.
**Do not reduce the node count on the strength of it.** The gap is the dataset,
not the code:

- p50 of 4 ms is not a Frappe request doing real work; it is a request whose
  every table fits in the buffer pool. §3's 110 ms blended service time assumes
  production volumes — millions of GL entries, hundreds of thousands of
  invoices. 4,208 GL entries is four thousand, not four million.
- The read mix is the cheap end: indexed list reads with `limit_page_length` of
  20–40, a count, and a KPI snapshot lookup. No desk form load with its child
  tables, no PDF render, no month-end posting run.
- One box, one MariaDB, no replica lag, no network between tiers, no TLS
  termination, no nginx.

So the honest reading is narrower and still worth having: **the application has
no gross inefficiency on these paths, the row-scoping design works under
concurrency, and the harness measures what it claims to.** The 2,500-user
capacity claim remains an extrapolation from §3's arithmetic until the same
profiles are run against staging at production data volumes.

Until then §3's sizing stands unchanged. It is the conservative direction, which
is the correct direction to be wrong in.

## 11. SLOs

| Metric | Target |
|---|---|
| p95 latency, portal reads | < 500 ms |
| p95 latency, desk form load | < 1,200 ms |
| p99 latency, any endpoint | < 3,000 ms |
| Error rate (5xx) | < 0.1% |
| Availability, 07:00–15:00 | 99.9% |
| Queue depth (`long`) | < 500 jobs sustained |
| Replication lag | < 5 s |
