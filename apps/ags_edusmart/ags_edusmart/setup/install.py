"""Install / migrate orchestration.

Every step here is idempotent and independently safe to re-run, because
``after_migrate`` fires on every deploy. Failures in optional seed data are
logged rather than raised: a missing default must not leave a site half-migrated.
"""

from __future__ import annotations

import frappe

from ags_edusmart.setup import custom_fields, dimensions, roles, seed


def before_install() -> None:
	"""Roles must exist before DocType permissions are imported."""
	roles.create_roles()


def after_install() -> None:
	roles.create_roles()
	dimensions.create_accounting_dimensions()
	custom_fields.create_ags_custom_fields()
	seed.seed_all()
	frappe.db.commit()


def after_migrate() -> None:
	roles.create_roles()
	_safe(dimensions.create_accounting_dimensions, "accounting dimensions")
	_safe(custom_fields.create_ags_custom_fields, "custom fields")
	_safe(seed.seed_all, "seed data")
	frappe.db.commit()


def before_uninstall() -> None:
	"""Remove only what this app owns. Native records are left untouched."""
	for doctype, filters in (
		("Custom Field", {"module": "AGS Core"}),
		("Property Setter", {"module": "AGS Core"}),
	):
		for name in frappe.get_all(doctype, filters=filters, pluck="name"):
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
	frappe.db.commit()


def _safe(fn, label: str) -> None:
	try:
		fn()
	except Exception:
		frappe.log_error(
			title=f"AGS migrate: {label} failed",
			message=frappe.get_traceback(),
		)
