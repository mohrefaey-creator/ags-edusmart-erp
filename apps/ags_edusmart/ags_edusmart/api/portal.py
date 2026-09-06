"""Parent and employee portal API (SKILL sec. 21, 22, 33).

Every endpoint here is reachable by a low-privilege portal user, so each one
resolves the caller's own scope server-side and ignores any identifying argument
the client supplies. A parent cannot ask for another payer's statement by
changing a parameter, because no endpoint takes a payer id from the request.

The vocabulary is school-facing: "Request Supplies" rather than Material
Request, "Pay School Fees" rather than Sales Invoice (SKILL sec. 33). The ERP
terms stay in the backend where finance and procurement expect them.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from ags_edusmart.ags_core.permissions import payer_accounts_for_user


# --------------------------------------------------------------------- helpers
def _require_login() -> str:
	if frappe.session.user == "Guest":
		frappe.throw(_("Please sign in."), frappe.PermissionError)
	return frappe.session.user


def _my_payer_account() -> str:
	"""The caller's own payer account. Never taken from the request."""
	user = _require_login()
	accounts = payer_accounts_for_user(user)
	if not accounts:
		frappe.throw(
			_("No payer account is linked to your login. Contact the school office."),
			frappe.PermissionError,
		)
	return accounts[0]


def _my_students() -> list[str]:
	payer = _my_payer_account()
	return frappe.get_all(
		"AGS Payer Student",
		filters={"parent": payer, "parenttype": "AGS Payer Account", "is_active": 1},
		pluck="student",
	)


def _assert_my_student(student: str) -> str:
	if student not in _my_students():
		frappe.throw(_("Not permitted for this student."), frappe.PermissionError)
	return student


def _my_employee() -> str:
	user = _require_login()
	employee = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")
	if not employee:
		frappe.throw(_("No active employee record is linked to your login."),
		             frappe.PermissionError)
	return employee


# ------------------------------------------------------------- parent portal
@frappe.whitelist()
def my_children() -> list[dict]:
	"""The caller's children, with the headline figures for each."""
	payer = _my_payer_account()
	rows = frappe.get_all(
		"AGS Payer Student",
		filters={"parent": payer, "parenttype": "AGS Payer Account", "is_active": 1},
		fields=["student", "student_name", "program", "academic_year", "sibling_index"],
		order_by="sibling_index asc",
	)

	for row in rows:
		student = frappe.db.get_value(
			"Student", row.student,
			["ags_campus", "ags_school_division", "image"], as_dict=True,
		) or {}
		row["campus"] = student.get("ags_campus")
		row["division"] = student.get("ags_school_division")
		row["image"] = student.get("image")

		plan = frappe.db.get_value(
			"AGS Fee Plan",
			{"student": row.student, "docstatus": 1, "status": ("!=", "Cancelled")},
			["name", "net_total", "paid_total", "outstanding_total"],
			as_dict=True,
		)
		row["fee_plan"] = plan.name if plan else None
		row["fees_total"] = flt(plan.net_total) if plan else 0.0
		row["fees_paid"] = flt(plan.paid_total) if plan else 0.0
		row["fees_outstanding"] = flt(plan.outstanding_total) if plan else 0.0

	return rows


@frappe.whitelist()
def my_statement() -> dict:
	"""Consolidated statement across every child (SKILL sec. 18)."""
	from ags_edusmart.ags_fees.payer import get_statement

	return get_statement(_my_payer_account())


@frappe.whitelist()
def my_outstanding() -> dict:
	"""What is payable now — the "Pay School Fees" basket."""
	from ags_edusmart.ags_fees.payments import outstanding_for_payer

	payer = _my_payer_account()
	invoices = outstanding_for_payer(payer)

	names = {i["ags_student"] for i in invoices if i.get("ags_student")}
	student_names = {
		r.name: r.student_name
		for r in frappe.get_all(
			"Student", filters={"name": ("in", list(names) or [""])},
			fields=["name", "student_name"],
		)
	}

	today = getdate(nowdate())
	total = overdue = 0.0
	for row in invoices:
		row["student_name"] = student_names.get(row.get("ags_student"))
		row["is_overdue"] = bool(row.get("due_date") and getdate(row["due_date"]) < today)
		total += flt(row["outstanding_amount"])
		if row["is_overdue"]:
			overdue += flt(row["outstanding_amount"])

	summary = frappe.db.get_value(
		"AGS Payer Account", payer, ["payer_name", "credit_balance"], as_dict=True
	)
	return {
		"payer_name": summary.payer_name if summary else None,
		"credit_balance": flt(summary.credit_balance) if summary else 0.0,
		"total_outstanding": flt(total, 2),
		"total_overdue": flt(overdue, 2),
		"invoices": invoices,
	}


@frappe.whitelist()
def my_installments(student: str | None = None) -> list[dict]:
	"""Upcoming installments, so a parent can see what falls due when."""
	students = [_assert_my_student(student)] if student else _my_students()
	if not students:
		return []

	return frappe.db.sql(
		"""
		select p.student, p.student_name, i.installment_no, i.label, i.due_date,
		       i.amount, i.paid_amount, i.outstanding_amount, i.status,
		       i.sales_invoice
		from `tabAGS Fee Plan Installment` i
		inner join `tabAGS Fee Plan` p on p.name = i.parent
		where p.docstatus = 1 and p.student in %(students)s
		  and i.status != 'Cancelled'
		order by i.due_date asc
		""",
		{"students": students},
		as_dict=True,
	)


@frappe.whitelist()
def my_child_attendance(student: str, limit: int = 30) -> list[dict]:
	_assert_my_student(student)
	return frappe.get_all(
		"Student Attendance",
		filters={"student": student, "docstatus": 1},
		fields=["date", "status", "leave_application"],
		order_by="date desc",
		limit=min(int(limit), 200),
	)


@frappe.whitelist()
def my_child_results(student: str) -> list[dict]:
	_assert_my_student(student)
	return frappe.get_all(
		"Assessment Result",
		filters={"student": student, "docstatus": 1},
		fields=["assessment_plan", "course", "grade", "total_score", "maximum_score"],
		order_by="creation desc",
		limit=100,
	)


# ------------------------------------------------- employee self-service
@frappe.whitelist()
def my_profile() -> dict:
	"""Employee self-service landing data (SKILL sec. 22)."""
	employee = _my_employee()
	row = frappe.db.get_value(
		"Employee", employee,
		["employee_name", "designation", "department", "ags_campus",
		 "date_of_joining", "ags_iqama_expiry", "ags_passport_expiry"],
		as_dict=True,
	)
	row["employee"] = employee
	row["leave_balance"] = _leave_balance(employee)
	row["open_assets"] = frappe.db.count("AGS Asset Handover", {
		"to_employee": employee, "docstatus": 1,
		"status": ("in", ("Pending Acknowledgement", "Active")),
	})
	return row


def _leave_balance(employee: str) -> list[dict]:
	from hrms.hr.doctype.leave_application.leave_application import get_leave_balance_on

	balances = []
	for leave_type in frappe.get_all("Leave Type", pluck="name"):
		try:
			balance = get_leave_balance_on(employee, leave_type, nowdate())
		except Exception:
			# A leave type with no allocation raises rather than returning zero;
			# an employee simply has no balance for it.
			continue
		if balance:
			balances.append({"leave_type": leave_type, "balance": flt(balance)})
	return balances


@frappe.whitelist()
def my_assets() -> list[dict]:
	from ags_edusmart.ags_assets.handover import my_assets as assets

	return assets()


@frappe.whitelist()
def acknowledge_asset_handover(handover: str) -> str:
	from ags_edusmart.ags_assets.handover import acknowledge

	return acknowledge(handover)


@frappe.whitelist()
def request_supplies(purpose: str, items: str, required_date: str | None = None,
                     justification: str | None = None) -> str:
	"""Teacher-facing "Request Supplies". Creates a Material Request (SKILL sec. 33).

	``items`` is a JSON list of ``{"item_code": ..., "qty": ...}``.
	"""
	import json

	employee = _my_employee()
	rows = json.loads(items) if isinstance(items, str) else items
	if not rows:
		frappe.throw(_("Add at least one item."))

	profile = frappe.db.get_value(
		"Employee", employee, ["company", "ags_campus", "department"], as_dict=True
	)
	warehouse = frappe.db.get_value(
		"AGS Campus", profile.ags_campus, "default_warehouse"
	) if profile.ags_campus else None
	if not warehouse:
		warehouse = frappe.db.get_value(
			"Warehouse", {"company": profile.company, "is_group": 0}, "name"
		)

	request = frappe.new_doc("Material Request")
	request.material_request_type = "Purchase"
	request.company = profile.company
	request.transaction_date = nowdate()
	request.schedule_date = required_date or nowdate()
	request.ags_campus = profile.ags_campus
	request.ags_purpose = purpose
	request.ags_justification = justification

	for row in rows:
		request.append("items", {
			"item_code": row["item_code"],
			"qty": flt(row["qty"]),
			"schedule_date": required_date or nowdate(),
			"warehouse": warehouse,
		})

	# Submitted on the requester's behalf, which is what opens the approval
	# request; the teacher never sees an approval matrix.
	request.flags.ignore_permissions = True
	request.insert()
	request.submit()
	return request.name


@frappe.whitelist()
def my_requests(limit: int = 20) -> list[dict]:
	"""Requests raised by this employee, in school language."""
	employee = _my_employee()
	user = frappe.db.get_value("Employee", employee, "user_id")

	requests = frappe.get_all(
		"Material Request",
		filters={"owner": user, "docstatus": ("<", 2)},
		fields=["name", "transaction_date", "ags_purpose", "ags_estimated_total",
		        "ags_approval_status", "status"],
		order_by="creation desc",
		limit=int(limit),
	)
	for row in requests:
		row["approval"] = _approval_state(row.name)
	return requests


def _approval_state(material_request: str) -> dict | None:
	row = frappe.db.get_value(
		"AGS Approval Request",
		{"reference_doctype": "Material Request", "reference_name": material_request},
		["status", "current_level", "current_role", "due_by"],
		as_dict=True,
	)
	return row
