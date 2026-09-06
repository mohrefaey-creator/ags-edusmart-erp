# ADR 0007 — Two campus fieldnames, deliberately

**Status:** Accepted · 2026-09-06

## Context

Campus must reach both accounting documents (for dimension reporting, budget
validation and P&L by campus, §4.2) and school masters like Student, Employee
and Asset.

ERPNext's Accounting Dimension mechanism creates its own custom field on every
accounting doctype, and derives the fieldname from the dimension **label**. Our
"Campus" dimension therefore produces `campus`, and "Grade" produces `grade`.

Student, Employee, Asset and Guardian are not accounting doctypes, so no
dimension reaches them.

## Decision

- Accounting doctypes: `campus`, `school_division`, `academic_year`, `grade` —
  **ERPNext's fields, not ours.** Never renamed.
- Non-accounting masters: `ags_campus`, `ags_school_division` — ours, namespaced.
- All access goes through `ags_edusmart/utils/dimensions.py`
  (`campus_of`, `campus_field`, `set_dimensions`), which resolves whichever
  exists.

## Why not one name everywhere

Renaming ERPNext's dimension field breaks budget validation, which selects every
dimension fieldname by name from `tabBudget`. Adding a parallel `ags_campus` to
accounting doctypes instead gives two columns holding the same fact, one of which
ERPNext ignores — a reporting trap that would surface as "P&L by campus is
missing half the entries".

## The failure this cost us

ERPNext hands dimension field creation to a background worker
(`frappe.enqueue(..., enqueue_after_commit=True)`). On a bench with no running
worker — a fresh install, CI, or a container that starts web before workers —
the job never runs. The Accounting Dimension row exists and its columns do not.

The symptom is not a helpful error. It is
`Unknown column 'campus' in 'SELECT'` raised from ERPNext's own budget
validation, on any GL posting, with nothing in the traceback pointing at
dimensions.

`setup/dimensions.py::materialise_dimension_fields` therefore calls the field
maker **synchronously**, and the whole story is written down at that call site
and in `docs/runbooks/error-spike.md`.

## Consequences

- One indirection when reading a campus off a document. Cheap, and it is a
  single well-named helper.
- New AGS doctypes should use plain `campus`, matching the dimension convention.
