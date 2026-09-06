"""Accounting dimensions so campus / division / grade flow into the GL.

SKILL sec. 4.2 is explicit that dimensions must reach Sales Invoice, Purchase
Invoice, Payment Entry and Journal Entry, and equally explicit that they must not
all be mandatory everywhere - mandatory rules are per transaction type, set by
finance in the Accounting Dimension itself.
"""

from __future__ import annotations

import frappe

# (dimension DocType, label). Department, Project and Cost Center already ship as
# ERPNext dimensions, so only the AGS-specific ones are created here.
AGS_DIMENSIONS: list[tuple[str, str]] = [
	("AGS Campus", "Campus"),
	("AGS School Division", "School Division"),
	("Academic Year", "Academic Year"),
	("Program", "Grade"),
]


def create_accounting_dimensions() -> None:
	for doctype, label in AGS_DIMENSIONS:
		if not frappe.db.exists("DocType", doctype):
			# Academic Year / Program come from Frappe Education; if the app is
			# absent we simply skip rather than fail the install.
			continue

		name = frappe.db.get_value("Accounting Dimension", {"document_type": doctype}, "name")
		if not name:
			try:
				dimension = frappe.get_doc({
					"doctype": "Accounting Dimension",
					"document_type": doctype,
					"label": label,
					"disabled": 0,
				})
				dimension.insert(ignore_permissions=True)
				name = dimension.name
			except frappe.DuplicateEntryError:
				name = frappe.db.get_value(
					"Accounting Dimension", {"document_type": doctype}, "name"
				)
			except Exception:
				# A dimension failing to build must not abort the whole install.
				frappe.log_error(
					title="AGS: accounting dimension failed",
					message=f"{doctype}\n{frappe.get_traceback()}",
				)
				continue

		if name:
			materialise_dimension_fields(name)


def materialise_dimension_fields(dimension_name: str) -> bool:
	"""Create the dimension's custom fields on the accounting doctypes, now.

	ERPNext's ``AccountingDimension.on_update`` hands this to a background worker
	(``frappe.enqueue(..., enqueue_after_commit=True)``). On a bench with no
	running worker - a fresh install, a CI box, a container that starts web
	before workers - the job never executes, so the dimension row exists while
	its columns do not. The first symptom is an opaque
	``Unknown column 'campus' in 'SELECT'`` raised from ERPNext's own budget
	validation when any GL entry is posted, because the budget query selects
	every dimension fieldname.

	Calling the maker synchronously makes install deterministic. It is safe to
	repeat: ``create_custom_field`` skips a field that already exists.
	"""
	from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
		make_dimension_in_accounting_doctypes,
	)

	doc = frappe.get_doc("Accounting Dimension", dimension_name)
	if doc.disabled:
		return False
	try:
		make_dimension_in_accounting_doctypes(doc=doc)
	except Exception:
		frappe.log_error(
			title="AGS: dimension field creation failed",
			message=f"{dimension_name}\n{frappe.get_traceback()}",
		)
		return False
	return True


def execute() -> None:
	create_accounting_dimensions()
	frappe.db.commit()
