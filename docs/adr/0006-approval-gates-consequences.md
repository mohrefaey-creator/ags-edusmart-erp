# ADR 0006 — Approval gates the consequence, not the submission

**Status:** Accepted · 2026-09-06

## Context

Handover §23 asks for one reusable approval engine across purchase requests,
orders, discounts, refunds, expense claims, leave and journal adjustments, with
amount thresholds (§8.3, §17.7). §39.4 says to use Frappe Workflow where
possible.

The instinct is to block submission until approved.

## Decision

Submitting a document *raises* an `AGS Approval Request` and stamps the document
as pending. What the engine gates is the **downstream consequence**:

- a Purchase Order cannot be raised from an unapproved Material Request;
- an above-threshold discount does not reduce a fee plan until its tier signs
  off;
- a fee waiver posts no credit note until approved.

Level semantics are cumulative: a level applies when
`amount >= from_amount` and (`to_amount` is 0 or `amount <= to_amount`). So
SAR 30,000 requires department head **and** finance **and** principal — not
principal alone.

## Why

A submitted-but-awaiting-approval document is exactly the state §8.5 describes
("Draft / Awaiting Approval / Approved / …"). Blocking submission instead would
leave the request as a mutable draft, which means the thing being approved can
change between request and decision — the audit trail then records an approval
of something that no longer exists.

Gating the consequence keeps the approved artefact immutable.

## Why not pure Frappe Workflow

Frappe Workflow is per-DocType state machines configured in the UI. It cannot
express "the approver set depends on an amount read from a configurable field",
which is the entire requirement. The matrix generates the routing; Workflow
remains available for teams that want per-doctype states on top.

## Consequences

- Native doctypes need an `ags_approval_status` field with `allow_on_submit`.
- `assert_approved()` must be called at each consequence point; missing one is a
  silent hole, so the guard is tested (`test_purchase_order_is_blocked_by_an_unapproved_request`).
- An approved discount edits a *submitted* fee plan in place rather than
  re-running validation, because `components` is deliberately not
  `allow_on_submit` — the priced structure a parent already holds an invoice
  against must stay immutable.
