# ADR 0005 — Notifications go through a durable outbox

**Status:** Accepted · 2026-09-06

## Context

Handover §35 requires In-App, Email, SMS and WhatsApp delivery across a dozen
event types, including the fee reminder ladder that can touch ~6,000 payers in a
single nightly pass.

## Decision

Nothing is sent inline. Every message is written to `AGS Notification Outbox`
and drained by a background worker with retry and backoff.

Each row carries a **unique `dedupe_key`** (rule + document + channel + target
day). The unique index, not application logic, is what makes the pipeline
idempotent.

## Why

Two independent reasons.

**Latency.** Sending inline puts a third-party SMS gateway on the critical path
of a fee payment. A gateway that takes 15 seconds to time out would occupy a
gunicorn worker for 15 seconds — during the 07:00 peak, a few hundred of those
take the tier down. The outbox means the worst case is a delayed message.

**Correctness.** Reminder runs must be safely repeatable: a scheduler restart, a
retry after a crash, or two workers racing must not send a parent two copies of
the same overdue notice. Enforcing that with a unique constraint means it holds
even when the application logic is wrong.

## Consequences

- `redis-queue` must run `maxmemory-policy noeviction`. Under an LRU policy
  Redis silently discards queued jobs — an unsent reminder with no error
  anywhere. This is documented in `infra/redis/redis-queue.conf` and alerted on.
- Failed rows park at `status = Failed` after five attempts, visible and
  re-queueable, rather than disappearing.
- Delivery is at-least-once in principle; the dedupe key reduces it to
  effectively-once per rule per day.
