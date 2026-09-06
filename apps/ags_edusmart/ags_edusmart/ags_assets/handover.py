"""Asset custody (SKILL sec. 10.4).

Two rules the school actually enforces:

* custody moves through a native Asset Movement, so the Asset's own custodian and
  location stay authoritative;
* an employee cannot be separated while assets are still signed out to them.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now, nowdate


def sync_custodian(doc, method=None):
	"""After an Asset Movement submits, mirror custody onto the AGS record."""
	handover = frappe.db.get_value(
		"AGS Asset Handover", {"asset_movement": doc.name}, "name"
	)
	if not handover:
		return
	frappe.db.set_value(
		"AGS Asset Handover", handover, "status",
		"Returned" if doc.purpose == "Receipt" else "Active",
		update_modified=False,
	)


def open_handovers_for_employee(employee: str) -> list[str]:
	return frappe.get_all(
		"AGS Asset Handover",
		filters={
			"to_employee": employee,
			"docstatus": 1,
			"status": ("in", ("Pending Acknowledgement", "Active")),
		},
		pluck="name",
	)


def block_separation_with_open_assets(doc, method=None):
	"""Employee Separation validate hook (SKILL sec. 10.4)."""
	if not doc.get("employee"):
		return
	open_items = open_handovers_for_employee(doc.employee)
	if not open_items:
		return
	frappe.throw(
		_("{0} still holds assets under handover(s) {1}. Return or reassign them "
		  "before completing separation.").format(
			doc.get("employee_name") or doc.employee, ", ".join(open_items)
		),
		title=_("Assets Not Returned"),
	)


@frappe.whitelist()
def acknowledge(handover: str) -> str:
	"""Digital acknowledgement by the receiving employee."""
	doc = frappe.get_doc("AGS Asset Handover", handover)
	if doc.docstatus != 1:
		frappe.throw(_("Handover {0} is not submitted.").format(handover))
	if doc.acknowledged:
		return doc.name

	employee_user = frappe.db.get_value("Employee", doc.to_employee, "user_id")
	if frappe.session.user != employee_user and "System Manager" not in frappe.get_roles():
		frappe.throw(
			_("Only {0} can acknowledge this handover.").format(employee_user or "-"),
			frappe.PermissionError,
		)

	doc.db_set("acknowledged", 1, update_modified=False)
	doc.db_set("acknowledged_by", frappe.session.user, update_modified=False)
	doc.db_set("acknowledged_on", now(), update_modified=False)
	doc.db_set("status", "Active", update_modified=False)
	doc.add_comment("Info", _("Acknowledged by {0}.").format(frappe.session.user))
	return doc.name


@frappe.whitelist()
def my_assets(user: str | None = None) -> list[dict]:
	"""Employee self-service: what am I holding? (SKILL sec. 22)"""
	user = user or frappe.session.user
	employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
	if not employee:
		return []

	return frappe.db.sql(
		"""
		select ho.name as handover, ho.handover_date, ho.status, ho.acknowledged,
		       ho.return_due_date, i.asset, i.asset_name, i.serial_no, i.condition
		from `tabAGS Asset Handover` ho
		inner join `tabAGS Asset Handover Item` i on i.parent = ho.name
		where ho.docstatus = 1 and ho.to_employee = %(employee)s
		  and ho.status in ('Pending Acknowledgement', 'Active')
		order by ho.handover_date desc
		""",
		{"employee": employee},
		as_dict=True,
	)


def notify_overdue_returns() -> int:
	"""Assets past their return date, surfaced to the asset manager."""
	from ags_edusmart.ags_notifications.dispatcher import queue_message

	rows = frappe.get_all(
		"AGS Asset Handover",
		filters={
			"docstatus": 1,
			"status": "Active",
			"return_due_date": ("<", nowdate()),
		},
		fields=["name", "to_employee", "to_employee_name", "return_due_date", "campus"],
		limit=500,
	)
	sent = 0
	for row in rows:
		managers = frappe.get_all(
			"Has Role",
			filters={"role": "AGS Asset Manager", "parenttype": "User"},
			pluck="parent",
		)
		for user in managers:
			if queue_message(
				channel="In-App",
				recipient=user,
				recipient_user=user,
				subject=_("Asset return overdue: {0}").format(row.name),
				message=_("{0} was due to return assets on {1}.").format(
					row.to_employee_name or row.to_employee, row.return_due_date
				),
				dedupe_key=f"asset-overdue|{row.name}|{user}|{nowdate()}",
				reference_doctype="AGS Asset Handover",
				reference_name=row.name,
				priority="High",
			):
				sent += 1
	return sent
