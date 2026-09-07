# Load tests

Two profiles. They answer different questions and the distinction matters.

| Profile | Question | Gates? |
|---|---|---|
| `k6/calibrate.js` | What does **one node** actually deliver per worker? | No — meant to be pushed past the SLO |
| `k6/school-day.js` | Does the **deployed topology** hold a real school day? | Yes — thresholds are the SLOs |

## Why calibration exists

[`docs/capacity-model.md`](../docs/capacity-model.md) §3 rests on a single
assumption:

> a gunicorn worker serves ~9 req/s at a ~110 ms blended service time

Every node count downstream comes from that one number. If it is wrong by 2×,
the whole model is wrong by 2×. `calibrate.js` measures it on one node and
prints the verdict, so the model becomes extrapolation from a measurement
rather than arithmetic from a guess.

```bash
sudo bash scripts/install-k6.sh
bash scripts/load-test.sh calibrate
```

Output ends with:

```
  Model check (docs/capacity-model.md §3)
    assumed  9.00 req/s per worker
    measured X.XX req/s per worker
    verdict  ...
```

## Why this never runs against `bench serve`

`bench serve` is Werkzeug: single process, single thread, no preload. Measuring
it tells you about Werkzeug, not about the system. `scripts/load-test.sh`
starts **gunicorn with the same flags the container image uses**, so the numbers
transfer to the deployed topology.

Worker count defaults to what the machine can hold rather than the model's 17 —
a Frappe worker resides around 200–250 MB, so 17 need roughly 4 GB for the app
tier alone. That is exactly why calibration reports *per worker*: a small run
scales up honestly, a whole-box run does not.

## The school-day profile

Replays the shape of a real day rather than a flat rate, because the risk in
this system is the shape:

```
06:30  quiet
07:40  attendance rush      — every teacher, same screens, ~20 minutes
09:00  mid-morning plateau  — admin, finance, procurement
12:00  parent surge         — month-start installments and the reminder ladder
15:00  wind-down
```

Compressed by default: one simulated minute per real second, so a full day runs
in about nine minutes. `-e COMPRESSION=1` for real time.

The parent cohort uses a **constant arrival rate**, not constant VUs. Parents
arrive independently; if the app slows they pile up rather than politely waiting
their turn. A closed-loop VU model throttles itself when the server slows, which
hides a capacity cliff instead of finding it.

```bash
k6 run -e BASE_URL=https://erp-staging.ags.edu.sa \
       -e PARENT_PASSWORD=... -e TEACHER_PASSWORD=... \
       k6/school-day.js
```

Its thresholds are the SLOs from the capacity model §11, so a breach fails the
run. Run it before every capacity change — a capacity claim nobody re-tests
quietly rots.

## Reading a failure

A breach is information, not just a red mark:

| Symptom | Likely cause |
|---|---|
| `ags_desk_latency` p95 climbs, `ags_portal_latency` fine | a desk form got heavier — check child-table loads |
| Both climb together, CPU flat | database — see `docs/runbooks/slow-response.md` §3 |
| `ags_read_latency` fine until a step, then a cliff | worker saturation; the knee is your real capacity |
| KPI read p95 in seconds | a dashboard reverted to live aggregation (ADR 0004) |

## Results

`results-calibrate-400rps.txt` and `results-school-day-unscaled.txt` are the raw
output of the last run. Summary and, more importantly, the limits of what they
prove: [`../docs/capacity-model.md`](../docs/capacity-model.md) §10.

## Diagnosing a failed run

k6 reports a failure *rate* and nothing about the cause, and in this system four
completely different faults all present as "most requests failed" with
implausibly good latency, because an error response is fast. Every one of these
was hit while getting the profile to pass:

| Symptom | Cause | Tool |
|---|---|---|
| "gunicorn did not come up" while it is plainly up | Request Host resolves to `default_site`, a different database | `scripts/probe-endpoints.sh` |
| 84% fail, "Insufficient Permission" | Role has no DocType-level access, so row scoping never runs | `scripts/probe-endpoints.sh` |
| ~50% of logins 500 | Concurrent logins for one account race in Frappe's session bookkeeping | `scripts/probe-login-concurrency.sh` |
| 93% fail, "Login to access" | k6 empties the cookie jar between iterations | `scripts/probe-session.sh` |
| 19% fail on exactly one endpoint | A recycled VU kept the previous scenario's session | the `FAIL` samples below |

Run the probes before re-running an eight-minute profile — each answers its
question in under a minute. `school-day.js` also prints the first few non-200
responses with status and body (`-e FAILURE_SAMPLES=25`), which is usually
enough on its own: "93% failed" and "93% timed out" look identical in the k6
summary and mean entirely different things.
