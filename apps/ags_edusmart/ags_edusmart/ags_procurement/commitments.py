"""Commitment accounting (SKILL sec. 7.1).

    Original Budget - Actual Spend - Open PO - Approved PR = Available Budget

ERPNext's native budget check only sees *actuals*, so a department can approve
five purchase requests against the same remaining SAR 50,000 and only discover
the overspend when the invoices land. This module keeps a side ledger of what has
been promised.

It deliberately never posts to the GL: a commitment is not an accounting event,
and SKILL sec. 29 allows exactly one accounting engine. The ledger is reconciled
nightly against the documents it mirrors, so a crash mid-transition self-heals.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from ags_edusmart.utils.dimensions import campus_of


def settings():
	return frappe.get_cached_doc("AGS Settings")


def enabled() -> bool:
	return bool(settings().enable_commitment_accounting)


def fiscal_year_for(date=None) -> str | None:
	from erpnext.accounts.utils import get_fiscal_year

	try:
		return get_fiscal_year(getdate(date or nowdate()), as_dict=True).name
	except Exception:
		return None


# ------------------------------------------------------------------ budget
def budget_amount(company: str, account: str, cost_center: str, fiscal_year: str) -> float:
	"""Budgeted amount for one account/cost-center in a fiscal year.

	ERPNext restructured Budget in v16: ``account`` and ``budget_amount`` moved up
	to the Budget itself and the ``Budget Account`` child table disappeared, along
	with the single ``fiscal_year`` field (now a from/to range materialised as
	``budget_start_date`` / ``budget_end_date``). Both shapes are handled so this
	does not silently return zero - and a silent zero here is dangerous, because
	``has_budget`` false means *skip the budget check entirely*.
	"""
	if not (account and cost_center and fiscal_year):
		return 0.0

	dates = frappe.db.get_value(
		"Fiscal Year", fiscal_year, ["year_start_date", "year_end_date"], as_dict=True
	)
	if not dates:
		return 0.0

	params = {
		"company": company,
		"cost_center": cost_center,
		"account": account,
		"start": dates.year_start_date,
		"end": dates.year_end_date,
	}

	if frappe.get_meta("Budget").has_field("accounts"):
		# ERPNext <= v15
		value = frappe.db.sql(
			"""
			select sum(ba.budget_amount)
			from `tabBudget Account` ba
			inner join `tabBudget` b on b.name = ba.parent
			where b.docstatus = 1 and b.company = %(company)s
			  and b.cost_center = %(cost_center)s and ba.account = %(account)s
			  and b.fiscal_year = %(fiscal_year)s
			""",
			{**params, "fiscal_year": fiscal_year},
		)
	else:
		# ERPNext v16: one row per account, dated by the fiscal-year range.
		value = frappe.db.sql(
			"""
			select sum(b.budget_amount)
			from `tabBudget` b
			where b.docstatus = 1 and b.company = %(company)s
			  and b.cost_center = %(cost_center)s and b.account = %(account)s
			  and b.budget_start_date <= %(end)s and b.budget_end_date >= %(start)s
			""",
			params,
		)

	return flt(value[0][0]) if value else 0.0


def actual_spend(company: str, account: str, cost_center: str, fiscal_year: str) -> float:
	dates = frappe.db.get_value(
		"Fiscal Year", fiscal_year, ["year_start_date", "year_end_date"], as_dict=True
	)
	if not dates:
		return 0.0
	value = frappe.db.sql(
		"""
		select sum(debit - credit) from `tabGL Entry`
		where company = %(company)s and account = %(account)s
		  and cost_center = %(cost_center)s and is_cancelled = 0
		  and posting_date between %(start)s and %(end)s
		""",
		{
			"company": company,
			"account": account,
			"cost_center": cost_center,
			"start": dates.year_start_date,
			"end": dates.year_end_date,
		},
	)
	return flt(value[0][0]) if value else 0.0


def open_commitments(company: str, account: str, cost_center: str, fiscal_year: str,
                     exclude: tuple[str, str] | None = None) -> float:
	filters = {
		"company": company,
		"account": account,
		"cost_center": cost_center,
		"fiscal_year": fiscal_year,
		"status": ("in", ("Open", "Converted")),
	}
	rows = frappe.get_all(
		"AGS Budget Commitment",
		filters=filters,
		fields=["source_doctype", "source_name", "amount", "consumed_amount"],
	)
	total = 0.0
	for row in rows:
		if exclude and row.source_doctype == exclude[0] and row.source_name == exclude[1]:
			continue
		total += flt(row.amount) - flt(row.consumed_amount)
	return flt(total, 2)


def available_budget(company: str, account: str, cost_center: str,
                     fiscal_year: str | None = None,
                     exclude: tuple[str, str] | None = None) -> dict:
	fiscal_year = fiscal_year or fiscal_year_for()
	budget = budget_amount(company, account, cost_center, fiscal_year)
	actual = actual_spend(company, account, cost_center, fiscal_year)
	committed = open_commitments(company, account, cost_center, fiscal_year, exclude)
	return {
		"fiscal_year": fiscal_year,
		"budget": flt(budget, 2),
		"actual": flt(actual, 2),
		"committed": flt(committed, 2),
		"available": flt(budget - actual - committed, 2),
		"has_budget": bool(budget),
	}


# ---------------------------------------------------------- material request
def _mr_total(doc) -> float:
	total = 0.0
	for row in doc.items:
		rate = flt(row.get("rate")) or flt(
			frappe.db.get_value("Item", row.item_code, "valuation_rate")
		)
		total += flt(row.qty) * rate
	return flt(total, 2)


def _mr_cost_center(doc) -> str | None:
	for row in doc.items:
		if row.get("cost_center"):
			return row.cost_center
	campus = campus_of(doc)
	if campus:
		return frappe.db.get_value("AGS Campus", campus, "cost_center")
	return frappe.get_cached_value("Company", doc.company, "cost_center")


def validate_material_request(doc, method=None):
	if not doc.meta.has_field("ags_estimated_total"):
		return

	doc.ags_estimated_total = _mr_total(doc)

	if not enabled() or not doc.get("ags_budget_account"):
		return

	cost_center = _mr_cost_center(doc)
	status = available_budget(
		doc.company, doc.ags_budget_account, cost_center,
		exclude=("Material Request", doc.name),
	)
	doc.ags_budget_available = status["available"]

	if not status["has_budget"]:
		return

	if flt(doc.ags_estimated_total) <= status["available"]:
		return

	action = settings().commitment_action or "Warn"
	message = _(
		"Budget exceeded for {0} / {1}. Available {2} (budget {3} less actual {4} "
		"and committed {5}), requested {6}."
	).format(
		doc.ags_budget_account, cost_center, status["available"], status["budget"],
		status["actual"], status["committed"], doc.ags_estimated_total,
	)

	if action == "Stop":
		frappe.throw(message, title=_("Budget Exceeded"))
	elif action == "Require Override Approval":
		# The approval matrix carries a level flagged can_override_budget; the
		# request still submits, but it cannot become a PO without that sign-off.
		doc.ags_approval_status = "Pending"
		frappe.msgprint(message, indicator="orange", title=_("Override Approval Required"))
	else:
		frappe.msgprint(message, indicator="orange", title=_("Budget Warning"))


def reserve_commitment(doc, method=None):
	"""On MR submit: reserve the estimated amount against the budget line."""
	if not enabled() or not doc.get("ags_budget_account"):
		return
	_upsert_commitment(
		source_doctype="Material Request",
		source_name=doc.name,
		company=doc.company,
		account=doc.ags_budget_account,
		cost_center=_mr_cost_center(doc),
		campus=campus_of(doc),
		amount=flt(doc.ags_estimated_total),
		posting_date=doc.transaction_date,
	)


# ------------------------------------------------------------ purchase order
def validate_purchase_order(doc, method=None):
	"""A PO may not be raised from a request that has not cleared approval."""
	from ags_edusmart.ags_approvals.engine import assert_approved

	seen = set()
	for row in doc.items:
		mr = row.get("material_request")
		if not mr or mr in seen:
			continue
		seen.add(mr)
		assert_approved("Material Request", mr)

	if not enabled():
		return

	account = _po_expense_account(doc)
	if not account:
		return
	cost_center = _po_cost_center(doc)
	status = available_budget(
		doc.company, account, cost_center, exclude=("Purchase Order", doc.name)
	)
	if not status["has_budget"]:
		return
	if flt(doc.grand_total) <= status["available"] + _released_by_source(seen):
		return

	action = settings().commitment_action or "Warn"
	message = _("Budget exceeded for {0} / {1}. Available {2}, order {3}.").format(
		account, cost_center, status["available"], doc.grand_total
	)
	if action == "Stop":
		frappe.throw(message, title=_("Budget Exceeded"))
	frappe.msgprint(message, indicator="orange", title=_("Budget Warning"))


def _released_by_source(material_requests: set) -> float:
	"""Amounts already committed by the source requests, which this order replaces."""
	if not material_requests:
		return 0.0
	rows = frappe.get_all(
		"AGS Budget Commitment",
		filters={
			"source_doctype": "Material Request",
			"source_name": ("in", list(material_requests)),
			"status": ("in", ("Open", "Converted")),
		},
		fields=["amount", "consumed_amount"],
	)
	return flt(sum(flt(r.amount) - flt(r.consumed_amount) for r in rows), 2)


def _po_expense_account(doc) -> str | None:
	for row in doc.items:
		if row.get("expense_account"):
			return row.expense_account
	return None


def _po_cost_center(doc) -> str | None:
	for row in doc.items:
		if row.get("cost_center"):
			return row.cost_center
	return frappe.get_cached_value("Company", doc.company, "cost_center")


def convert_commitment(doc, method=None):
	"""On PO submit: release the request's commitment, open the order's own."""
	if not enabled():
		return

	for mr in {row.material_request for row in doc.items if row.get("material_request")}:
		frappe.db.set_value(
			"AGS Budget Commitment",
			{"source_doctype": "Material Request", "source_name": mr, "status": "Open"},
			"status", "Converted", update_modified=False,
		)

	account = _po_expense_account(doc)
	if not account:
		return
	_upsert_commitment(
		source_doctype="Purchase Order",
		source_name=doc.name,
		company=doc.company,
		account=account,
		cost_center=_po_cost_center(doc),
		campus=campus_of(doc),
		amount=flt(doc.grand_total),
		posting_date=doc.transaction_date,
	)


def settle_commitment(doc, method=None):
	"""On Purchase Invoice submit: the spend is now an actual, so retire the
	matching commitment by the invoiced amount."""
	if not enabled():
		return
	orders = {row.purchase_order for row in doc.items if row.get("purchase_order")}
	for order in orders:
		row = frappe.db.get_value(
			"AGS Budget Commitment",
			{"source_doctype": "Purchase Order", "source_name": order,
			 "status": ("in", ("Open", "Converted"))},
			["name", "amount", "consumed_amount"],
			as_dict=True,
		)
		if not row:
			continue
		invoiced = flt(
			sum(flt(i.amount) for i in doc.items if i.get("purchase_order") == order)
		)
		consumed = flt(flt(row.consumed_amount) + invoiced, 2)
		status = "Settled" if consumed >= flt(row.amount) - 0.01 else row.get("status", "Open")
		frappe.db.set_value(
			"AGS Budget Commitment", row.name,
			{
				"consumed_amount": consumed,
				"open_amount": max(flt(row.amount) - consumed, 0),
				"status": status,
			},
			update_modified=False,
		)


def release_commitment(doc, method=None):
	"""On cancel: free the reservation."""
	frappe.db.set_value(
		"AGS Budget Commitment",
		{"source_doctype": doc.doctype, "source_name": doc.name,
		 "status": ("in", ("Open", "Converted"))},
		{"status": "Released", "open_amount": 0},
		update_modified=False,
	)


def _upsert_commitment(source_doctype, source_name, company, account, cost_center,
                       campus, amount, posting_date):
	if not (account and cost_center) or flt(amount) <= 0:
		return

	existing = frappe.db.get_value(
		"AGS Budget Commitment",
		{"source_doctype": source_doctype, "source_name": source_name},
		"name",
	)
	values = {
		"company": company,
		"account": account,
		"cost_center": cost_center,
		"campus": campus,
		"amount": flt(amount, 2),
		"open_amount": flt(amount, 2),
		"posting_date": posting_date or nowdate(),
		"fiscal_year": fiscal_year_for(posting_date),
		"status": "Open",
	}
	if existing:
		frappe.db.set_value("AGS Budget Commitment", existing, values, update_modified=False)
		return existing

	doc = frappe.get_doc({
		"doctype": "AGS Budget Commitment",
		"source_doctype": source_doctype,
		"source_name": source_name,
		**values,
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


# -------------------------------------------------------------- reconciliation
def reconcile_commitments(limit: int = 5000) -> dict:
	"""Nightly self-heal.

	Closes commitments whose source document is cancelled, closed or fully
	billed. Without this a crash between "PO submitted" and "commitment
	converted" would leave budget reserved forever.
	"""
	rows = frappe.get_all(
		"AGS Budget Commitment",
		filters={"status": ("in", ("Open", "Converted"))},
		fields=["name", "source_doctype", "source_name", "amount", "consumed_amount"],
		limit=limit,
	)

	released = settled = 0
	for row in rows:
		source = frappe.db.get_value(
			row.source_doctype, row.source_name,
			["docstatus", "status"], as_dict=True,
		)
		if not source or source.docstatus == 2:
			frappe.db.set_value(
				"AGS Budget Commitment", row.name,
				{"status": "Released", "open_amount": 0}, update_modified=False,
			)
			released += 1
			continue

		if source.status in ("Closed", "Stopped", "Completed"):
			frappe.db.set_value(
				"AGS Budget Commitment", row.name,
				{"status": "Settled", "open_amount": 0}, update_modified=False,
			)
			settled += 1

	frappe.db.commit()
	return {"released": released, "settled": settled}


@frappe.whitelist()
def budget_status(company: str, account: str, cost_center: str,
                  fiscal_year: str | None = None) -> dict:
	"""Whitelisted for the purchase-request form's budget indicator."""
	return available_budget(company, account, cost_center, fiscal_year)
