"""Where the campus lives on a document, and why it is not one name.

Two mechanisms put a campus on a document, and they choose different fieldnames:

* **Accounting Dimensions.** Registering "AGS Campus" as a dimension makes
  ERPNext create a field on every accounting doctype (Sales Invoice, Payment
  Entry, Journal Entry, Purchase Order, Budget, ...). Its fieldname comes from
  the dimension *label*, so it is ``campus`` - and ``grade`` for the Program
  dimension. This is ERPNext's field; it is what the budget and dimension
  reports query, and it must not be renamed.

* **AGS custom fields.** Student, Employee, Asset and Guardian are not
  accounting doctypes, so no dimension reaches them. They carry ``ags_campus``,
  namespaced to make clear the app owns it.

Rather than remembering which is which at every call site, resolve through here.
"""

from __future__ import annotations

import frappe

# Order matters: the dimension field wins where both somehow exist.
CAMPUS_FIELDS = ("campus", "ags_campus")
DIVISION_FIELDS = ("school_division", "ags_school_division")
ACADEMIC_YEAR_FIELDS = ("academic_year", "ags_academic_year")
GRADE_FIELDS = ("grade", "program", "ags_program")


def resolve_field(doctype: str, candidates: tuple[str, ...]) -> str | None:
	meta = frappe.get_meta(doctype)
	for name in candidates:
		if meta.has_field(name):
			return name
	return None


def campus_field(doctype: str) -> str | None:
	return resolve_field(doctype, CAMPUS_FIELDS)


def campus_of(doc) -> str | None:
	for name in CAMPUS_FIELDS:
		value = doc.get(name)
		if value:
			return value
	return None


def set_dimensions(doc, *, campus=None, school_division=None, academic_year=None,
                   grade=None) -> None:
	"""Write whichever dimension fields this doctype actually has."""
	for candidates, value in (
		(CAMPUS_FIELDS, campus),
		(DIVISION_FIELDS, school_division),
		(ACADEMIC_YEAR_FIELDS, academic_year),
		(GRADE_FIELDS, grade),
	):
		if not value:
			continue
		field = resolve_field(doc.doctype, candidates)
		if field:
			doc.set(field, value)
