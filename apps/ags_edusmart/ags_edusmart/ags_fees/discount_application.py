"""Applying an approved discount back onto its fee plan (SKILL sec. 17.7).

The application is deliberately the only route by which an above-threshold
discount reaches a fee plan, and it records the full before/after pair so the
audit answers "who reduced this, from what, to what, and why".
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, now


def compute_amounts(doc) -> None:
	"""Fill current_net / discount_amount / proposed_net / discount_percent."""
	plan = frappe.db.get_value(
		"AGS Fee Plan", doc.fee_plan, ["net_total", "gross_total"], as_dict=True
	)
	if not plan:
		return

	current = flt(plan.net_total)
	if doc.calculation == "Percent":
		amount = flt(current * flt(doc.value) / 100.0, 2)
	else:
		amount = min(flt(doc.value), current)

	doc.current_net = current
	doc.discount_amount = flt(amount, 2)
	doc.proposed_net = flt(current - amount, 2)
	# The tier is decided on the effective percentage of the plan, so a flat
	# 20,000 SAR exception routes the same way a 25% one would.
	doc.discount_percent = flt(amount / current * 100, 2) if current else 0.0


def apply_to_fee_plan(doc) -> None:
	"""Called by the approval engine once every level has signed off.

	The plan is submitted, so this edits it in place rather than re-running
	``validate``: a full recalculation would try to rewrite ``components``, which
	is deliberately *not* allow_on_submit - the priced structure a parent already
	holds an invoice against must stay immutable. Only the discount trail, the
	totals and the still-uninvoiced installments move.
	"""
	if doc.applied:
		return

	plan = frappe.get_doc("AGS Fee Plan", doc.fee_plan)
	if plan.docstatus != 1:
		frappe.throw(_("Fee plan {0} is not submitted.").format(doc.fee_plan))

	amount = flt(doc.discount_amount, 2)
	if amount <= 0:
		frappe.throw(_("Discount amount must be greater than zero."))

	open_rows = [
		row for row in plan.installments
		if not row.sales_invoice and row.status in ("Pending", "Cancelled")
	]
	reducible = flt(sum(flt(r.amount) for r in open_rows), 2)
	if amount > reducible:
		frappe.throw(
			_("Discount of {0} exceeds the {1} still uninvoiced on this plan. "
			  "Raise a credit note against the issued invoices instead.")
			.format(amount, reducible),
			title=_("Cannot Apply Discount"),
		)

	before = flt(plan.net_total)

	child = frappe.get_doc({
		"doctype": "AGS Fee Plan Discount",
		"parent": plan.name,
		"parenttype": "AGS Fee Plan",
		"parentfield": "discounts",
		"idx": len(plan.discounts) + 1,
		"discount_rule": doc.discount_rule,
		"discount_type": doc.discount_type,
		"calculation": doc.calculation,
		"value": doc.value,
		"discount_amount": amount,
		"status": "Applied",
		"approval_reference": doc.name,
		"notes": f"Approved discount application {doc.name}",
	})
	child.flags.ignore_permissions = True
	child.insert()

	_reduce_installments(open_rows, amount, reducible)

	after = flt(before - amount, 2)
	plan.db_set("discount_total", flt(plan.discount_total) + amount, update_modified=False)
	plan.db_set("net_total", after, update_modified=False)
	plan.db_set(
		"outstanding_total", flt(after - flt(plan.paid_total), 2), update_modified=False
	)

	doc.db_set("applied", 1, update_modified=False)
	doc.db_set("approved_by", frappe.session.user, update_modified=False)
	doc.db_set("approved_on", now(), update_modified=False)
	doc.db_set("current_net", before, update_modified=False)
	doc.db_set("proposed_net", after, update_modified=False)

	plan.add_comment(
		"Info",
		_("Discount application {0} approved. Net payable {1} -> {2}.").format(
			doc.name, before, after
		),
	)

	from ags_edusmart.ags_fees.payer import refresh_payer_account

	refresh_payer_account(plan.payer_account)


def _reduce_installments(rows: list, amount: float, reducible: float) -> None:
	"""Spread the reduction pro-rata over uninvoiced installments.

	The last row absorbs the rounding remainder so the installments still sum
	exactly to the new net payable.
	"""
	remaining = amount
	for index, row in enumerate(rows):
		if index == len(rows) - 1:
			share = remaining
		else:
			share = flt(amount * (flt(row.amount) / reducible), 2)
			remaining = flt(remaining - share, 2)
		new_amount = flt(flt(row.amount) - share, 2)
		row.db_set("amount", new_amount, update_modified=False)
		row.db_set("outstanding_amount", new_amount, update_modified=False)
