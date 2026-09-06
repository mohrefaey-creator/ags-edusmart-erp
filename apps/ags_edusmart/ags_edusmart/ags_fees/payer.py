"""Payer account roll-up.

Every figure a parent sees on their statement is derived here from the AR ledger,
never accumulated incrementally - an incrementally maintained balance drifts the
moment an invoice is cancelled or a payment reconciled outside the portal.
"""

from __future__ import annotations

import frappe
from frappe.utils import flt, getdate, now, nowdate


def refresh_payer_account(payer_account: str) -> dict:
	customer = frappe.db.get_value("AGS Payer Account", payer_account, "customer")
	if not customer:
		return {}

	summary = compute_summary(customer)
	frappe.db.set_value(
		"AGS Payer Account",
		payer_account,
		{
			"total_billed": summary["total_billed"],
			"total_paid": summary["total_paid"],
			"outstanding": summary["outstanding"],
			"overdue": summary["overdue"],
			"credit_balance": summary["credit_balance"],
			"next_due_date": summary["next_due_date"],
			"summary_updated_on": now(),
		},
		update_modified=False,
	)
	return summary


def compute_summary(customer: str) -> dict:
	rows = frappe.get_all(
		"Sales Invoice",
		filters={"customer": customer, "docstatus": 1},
		fields=["name", "grand_total", "outstanding_amount", "due_date", "is_return"],
	)

	today = getdate(nowdate())
	total_billed = total_paid = outstanding = overdue = 0.0
	next_due = None

	for row in rows:
		grand = flt(row.grand_total)
		out = flt(row.outstanding_amount)
		total_billed += grand
		total_paid += grand - out
		outstanding += out
		if out > 0 and row.due_date:
			if getdate(row.due_date) < today:
				overdue += out
			elif next_due is None or getdate(row.due_date) < next_due:
				next_due = getdate(row.due_date)

	# Unallocated advances sit as a negative outstanding on the party ledger.
	advance = flt(
		frappe.db.sql(
			"""
			select sum(credit - debit)
			from `tabGL Entry`
			where party_type = 'Customer' and party = %s
			  and is_cancelled = 0 and against_voucher is null
			""",
			customer,
		)[0][0]
	)

	return {
		"total_billed": flt(total_billed, 2),
		"total_paid": flt(total_paid, 2),
		"outstanding": flt(outstanding, 2),
		"overdue": flt(overdue, 2),
		"credit_balance": flt(max(advance, 0), 2),
		"next_due_date": next_due,
	}


def refresh_all(limit: int = 2000) -> int:
	names = frappe.get_all(
		"AGS Payer Account", filters={"is_active": 1}, pluck="name", limit=limit
	)
	for name in names:
		try:
			refresh_payer_account(name)
		except Exception:
			frappe.log_error(
				title="AGS: payer summary refresh failed",
				message=f"{name}\n{frappe.get_traceback()}",
			)
	frappe.db.commit()
	return len(names)


@frappe.whitelist()
def get_statement(payer_account: str) -> dict:
	"""Consolidated statement across every child (SKILL sec. 18)."""
	from ags_edusmart.ags_core.permissions import payer_account_has_permission

	doc = frappe.get_doc("AGS Payer Account", payer_account)
	if not payer_account_has_permission(doc, "read"):
		frappe.throw(frappe._("Not permitted."), frappe.PermissionError)

	invoices = frappe.get_all(
		"Sales Invoice",
		filters={"customer": doc.customer, "docstatus": 1},
		fields=[
			"name", "posting_date", "due_date", "grand_total", "outstanding_amount",
			"status", "ags_student", "ags_installment_no",
		],
		order_by="posting_date asc, name asc",
	)

	student_names = {
		row.name: row.student_name
		for row in frappe.get_all(
			"Student",
			filters={"name": ("in", [i.ags_student for i in invoices if i.ags_student] or [""])},
			fields=["name", "student_name"],
		)
	}
	for inv in invoices:
		inv["student_name"] = student_names.get(inv.ags_student)
		inv["paid_amount"] = flt(inv.grand_total) - flt(inv.outstanding_amount)

	return {
		"payer": {
			"name": doc.name,
			"payer_name": doc.payer_name,
			"customer": doc.customer,
			"outstanding": doc.outstanding,
			"overdue": doc.overdue,
			"credit_balance": doc.credit_balance,
			"next_due_date": doc.next_due_date,
		},
		"children": [
			{"student": row.student, "student_name": row.student_name, "program": row.program}
			for row in doc.students if row.is_active
		],
		"invoices": invoices,
	}
