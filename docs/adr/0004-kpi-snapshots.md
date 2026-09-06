# ADR 0004 — Dashboards read snapshots, never live aggregates

**Status:** Accepted · 2026-09-06

## Context

Handover §26–27 asks for executive dashboards with drilldown by company, campus,
division, grade, department and academic year. The obvious implementation
computes each KPI on read.

The load profile makes that untenable. At 07:00 dozens of people open dashboards
within a few minutes of each other, inside the same window as the attendance
rush. "Revenue per student" over a multi-year `tabGL Entry` is a full scan.

## Decision

`AGS KPI Snapshot` holds one row per (KPI × scope), keyed by a hashed
`scope_key` and upserted by a background refresh. Dashboard reads are a single
indexed lookup.

`AGS KPI Definition` carries a `refresh_interval_minutes`, so a cheap KPI can be
fresh and an expensive one can be hourly, without changing any read path.

## Why

Measured difference on this stack: ~15 ms for a snapshot read against ~2 s for
the live aggregation. At thirty concurrent dashboard users during the peak, that
is the difference between a rounding error and saturating the web tier.

Staleness is acceptable here in a way it is not for a fee balance: an executive
looking at "collection % by campus" is making a monthly decision, not a
transactional one. The read path returns `computed_on` and a `stale` flag so the
UI can say how old the number is rather than implying it is live.

## Consequences

- The scheduler becomes load-bearing for dashboards. If it stops, dashboards
  serve stale numbers *confidently* — hence `AGSSchedulerDown` is a critical
  alert and `docs/runbooks/scheduler-down.md` lists dashboards explicitly.
- Scope explosion is bounded on purpose: only company × campus × academic year
  are pre-materialised. Finer drilldowns compute on demand.
- A regression that reintroduces live aggregation is caught by the `dashboards`
  scenario in the k6 profile, which asserts the p95.
