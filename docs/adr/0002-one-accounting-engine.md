# ADR 0002 — One accounting engine; commitments are a side ledger

**Status:** Accepted · 2026-09-06

## Context

Handover §29 requires a single general ledger: fees, payroll, procurement and
assets must all post through one engine. Separately, §7.1 requires commitment
accounting — budget consumed by *approved requests and open orders*, before any
invoice exists.

These pull in opposite directions. Commitments look like accounting entries and
the obvious implementation is to post them to the GL.

## Decision

Nothing in `ags_edusmart` posts its own GL entries.

- A fee invoice is a `Sales Invoice`.
- A fee waiver is a return `Sales Invoice` (credit note), proportioned across the
  original lines so each revenue account is reversed by its own share.
- A department issue is a `Stock Entry` of type Material Issue.
- An asset handover is an `Asset Movement`.

`AGS Budget Commitment` is a **side ledger**. It never touches the GL. It is
reconciled nightly against the documents it mirrors, so a crash between "PO
submitted" and "commitment converted" self-heals rather than leaving budget
reserved forever.

## Why

A commitment is not an accounting event — no money has moved and no obligation
has crystallised. Posting one would put unrealised amounts into the trial
balance, and the school's auditors would be right to object.

Keeping it separate also means a bug in the commitment logic can waste budget
headroom but can never corrupt the ledger.

## Consequences

- "Available budget" is computed, not stored:
  `budget − actual(GL) − open commitments`.
- The commitment ledger can drift from reality; the nightly reconciliation is
  therefore load-bearing, not optional.
- Anyone reading the GL sees only real transactions, which is the point.
