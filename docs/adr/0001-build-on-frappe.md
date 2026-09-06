# ADR 0001 — Build the AGS layer on Frappe/ERPNext rather than greenfield

**Status:** Accepted · 2026-09-06

## Context

The handover (§1, §31, §39) is unambiguous: reuse native DocTypes and business
logic wherever mature functionality exists, and put AGS-specific logic in a
separate app. The alternative — a greenfield Next.js/Postgres ERP — was
available and would have been faster to demo.

## Decision

Build `ags_edusmart` as a Frappe app on Frappe 16.33 / ERPNext 16.34.1 /
HRMS 16.17.1 / Education 16.1.0.

## Why

The expensive, boring, correctness-critical parts of a school ERP already exist
and are battle-tested: double-entry GL, stock ledger, fixed-asset depreciation,
payroll, procurement cycle with three-way-matchable documents. Rewriting them
would consume the entire budget and produce a worse ledger.

What does *not* exist upstream is exactly what this app contains: campus-scoped
multi-entity structure, a payer account that consolidates siblings, a
component-eligible discount engine, commitment accounting, and Saudi/ZATCA
compliance.

## Consequences

- Upgrade compatibility is a standing constraint. No forking of core; extensions
  are custom fields, hooks and new DocTypes only.
- Upstream changes can break us in non-obvious ways. Two already have — see
  ADR 0007 and the Budget schema note in `ags_procurement/commitments.py`.
- The team needs Frappe fluency, which is a narrower skill pool than React.

## Alternatives rejected

**Greenfield.** Would have meant writing a general ledger. A school's cash
ledger is not the place to learn double-entry accounting.

**ERPNext without a custom app** (custom fields and server scripts only).
Rejected: the fee engine and approval matrix are real software with real tests,
and server scripts are not a place to put software you intend to maintain.
