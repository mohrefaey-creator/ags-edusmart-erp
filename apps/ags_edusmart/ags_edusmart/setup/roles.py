"""AGS role families (SKILL sec. 34).

These must exist *before* DocType JSON is synced: every permission row carries a
Link to Role, and Frappe rejects the import if the target is missing. That is why
this runs from ``before_install`` and again from a ``pre_model_sync`` patch - the
first covers a fresh install, the second covers an upgrade that adds a role.
"""

from __future__ import annotations

import frappe

# desk_access=0 gives a portal-only role: parents and students never reach the
# ERP desk, they only ever see the portal pages (SKILL sec. 21/33).
AGS_ROLES: list[tuple[str, bool]] = [
	("AGS Group Executive", True),
	("AGS Finance Manager", True),
	("AGS Accountant", True),
	("AGS Cashier", True),
	("AGS Department Head", True),
	("AGS Procurement Manager", True),
	("AGS Procurement Officer", True),
	("AGS Storekeeper", True),
	("AGS Asset Manager", True),
	("AGS HR Manager", True),
	("AGS HR Officer", True),
	("AGS Payroll Officer", True),
	("AGS Principal", True),
	("AGS Vice Principal", True),
	("AGS Academic Coordinator", True),
	("AGS Teacher", True),
	("AGS Counselor", True),
	("AGS Nurse", True),
	("AGS IT", True),
	("AGS Maintenance", True),
	("AGS Collections Officer", True),
	("AGS Auditor", True),
	("AGS Parent", False),
	("AGS Student", False),
]


def create_roles() -> None:
	existing = set(
		frappe.get_all("Role", filters={"name": ("in", [r[0] for r in AGS_ROLES])}, pluck="name")
	)
	for role_name, desk_access in AGS_ROLES:
		if role_name in existing:
			continue
		frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": role_name,
				"desk_access": int(desk_access),
				"is_custom": 1,
			}
		).insert(ignore_permissions=True)


def execute() -> None:
	"""Patch entry point."""
	create_roles()
	frappe.db.commit()
