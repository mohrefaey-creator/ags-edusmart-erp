# ADR 0003 — The payer is a separate entity from the student

**Status:** Accepted · 2026-09-06

## Context

Handover §13.4 and §18: student identity must be separate from financial payer
identity, and one payer must be able to carry several children on a single
statement.

Frappe Education puts a `customer` field directly on `Student`, which makes each
child their own receivable.

## Decision

`AGS Payer Account` owns the `Customer`. Invoices are raised on the *payer's*
customer, with the student carried as a dimension (`ags_student`).

`AGS Payer Student` rows link children to the payer and carry a computed
`sibling_index`.

## Why

Billing per student makes the common case wrong. A parent with three children
gets three statements, three balances, and a payment that has to be split by
hand across three ledgers. Consolidating on the payer means one statement, one
balance, and ERPNext's own payment allocation does the work.

It is also what makes the sibling discount computable: the tier depends on how
many children *this payer* has enrolled, which is only knowable if the payer is
a first-class record.

`sibling_index` is ordered by **date of birth**, not registration order, so
enrolling a younger child first does not silently move an older sibling into a
different discount tier.

## Consequences

- One customer per payer is enforced (unique constraint, validated with a clear
  message rather than a database error).
- Parent portal permissions resolve through Guardian → payer account, so a
  parent can only ever read their own account.
- `Student.customer` is left alone. It is unused by this app but not removed,
  since removing an upstream field breaks upgrade compatibility (ADR 0001).
