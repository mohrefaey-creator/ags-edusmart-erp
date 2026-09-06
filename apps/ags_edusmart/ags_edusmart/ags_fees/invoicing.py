"""Student invoice generation and the hooks on native Sales Invoice.

One installment produces one Sales Invoice raised on the *payer's* customer, not
the student's, so siblings consolidate onto a single statement (SKILL sec. 18).
The student stays on the invoice as a dimension for reporting.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from ags_edusmart.ags_fees.deferred_revenue import is_enabled as deferred_enabled
from ags_edusmart.ags_fees.deferred_revenue import service_period
from ags_edusmart.utils.dimensions import set_dimensions


@frappe.whitelist()
def create_invoice_for_installment(fee_plan: str, installment_no: int) -> str:
	plan = frappe.get_doc("AGS Fee Plan", fee_plan)
	if plan.docstatus != 1:
		frappe.throw(_("Submit the fee plan before invoicing."))

	row = next(
		(r for r in plan.installments if int(r.installment_no) == int(installment_no)), None
	)
	if not row:
		frappe.throw(_("Installment {0} not found on {1}.").format(installment_no, fee_plan))

	if row.sales_invoice:
		existing = frappe.db.get_value("Sales Invoice", row.sales_invoice, "docstatus")
		if existing in (0, 1):
			frappe.throw(
				_("Installment {0} is already invoiced as {1}.").format(
					installment_no, row.sales_invoice
				)
			)

	allocation = plan.component_allocation(len(plan.installments))
	lines = allocation[int(installment_no) - 1]
	if not lines:
		frappe.throw(_("Installment {0} has no billable lines.").format(installment_no))

	customer = frappe.db.get_value("AGS Payer Account", plan.payer_account, "customer")
	if not customer:
		frappe.throw(_("Payer account {0} has no customer.").format(plan.payer_account))

	posting_date, due_date = _posting_and_due(plan.company, row.due_date)

	invoice = frappe.new_doc("Sales Invoice")
	invoice.customer = customer
	invoice.company = plan.company
	invoice.posting_date = posting_date
	invoice.set_posting_time = 1
	invoice.due_date = due_date
	invoice.currency = plan.currency
	invoice.ags_student = plan.student
	invoice.ags_fee_plan = plan.name
	invoice.ags_payer_account = plan.payer_account
	invoice.ags_installment_no = row.installment_no
	if plan.receivable_account:
		invoice.debit_to = plan.receivable_account
	if plan.cost_center:
		invoice.cost_center = plan.cost_center

	# Fee rates come from the plan, not from a price list, but Sales Invoice still
	# requires one - and it must be in the invoice currency or the exchange-rate
	# fields cannot resolve.
	price_list = _selling_price_list(invoice.currency)
	if price_list:
		invoice.selling_price_list = price_list

	set_dimensions(
		invoice,
		campus=plan.campus,
		school_division=plan.school_division,
		academic_year=plan.academic_year,
		grade=plan.program,
	)

	# Deferred tuition is handled by ERPNext's own amortisation engine; all this
	# has to supply is the service window (SKILL sec. 5.4).
	service_start = service_end = None
	if deferred_enabled():
		service_start, service_end = service_period(plan.academic_year)

	for line in lines:
		item_code = line["item"]
		if not item_code:
			frappe.throw(
				_("Fee category {0} has no linked Item, so it cannot post to a revenue account.")
				.format(line["fees_category"])
			)
		item_row = {
			"item_code": item_code,
			"item_name": line["fees_category"],
			"description": line["description"] or line["fees_category"],
			"qty": 1,
			"rate": flt(line["amount"], 2),
			"income_account": line["income_account"],
			"cost_center": plan.cost_center,
		}
		if service_start and service_end and frappe.db.get_value(
			"Item", item_code, "enable_deferred_revenue"
		):
			item_row["enable_deferred_revenue"] = 1
			item_row["service_start_date"] = service_start
			item_row["service_end_date"] = service_end
		invoice.append("items", item_row)

	invoice.flags.ignore_permissions = True
	invoice.insert()
	invoice.submit()

	row.db_set("sales_invoice", invoice.name, update_modified=False)
	row.db_set("status", "Invoiced", update_modified=False)
	row.db_set("outstanding_amount", flt(invoice.outstanding_amount, 2), update_modified=False)
	plan.refresh_totals()
	return invoice.name


@frappe.whitelist()
def create_due_invoices(as_of: str | None = None, limit: int = 500) -> dict:
	"""Invoice every pending installment falling due on or before ``as_of``.

	Batched and committed per plan so a single bad plan cannot roll back the run.
	"""
	as_of = as_of or nowdate()
	rows = frappe.db.sql(
		"""
		select i.parent as fee_plan, i.installment_no
		from `tabAGS Fee Plan Installment` i
		inner join `tabAGS Fee Plan` p on p.name = i.parent
		where p.docstatus = 1 and p.status = 'Active'
		  and i.status = 'Pending' and (i.sales_invoice is null or i.sales_invoice = '')
		  and i.due_date <= %(as_of)s
		order by i.due_date asc
		limit %(limit)s
		""",
		{"as_of": as_of, "limit": int(limit)},
		as_dict=True,
	)

	created, failed = [], []
	for row in rows:
		try:
			created.append(create_invoice_for_installment(row.fee_plan, row.installment_no))
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			failed.append(row.fee_plan)
			frappe.log_error(
				title="AGS: installment invoicing failed",
				message=f"{row.fee_plan} #{row.installment_no}\n{frappe.get_traceback()}",
			)
	return {"created": created, "failed": failed}


def _selling_price_list(currency: str) -> str | None:
	"""A selling price list in the given currency, preferring the configured default."""
	default = frappe.db.get_single_value("Selling Settings", "selling_price_list")
	if default and frappe.db.get_value("Price List", default, "currency") == currency:
		return default
	return frappe.db.get_value(
		"Price List",
		{"selling": 1, "enabled": 1, "currency": currency},
		"name",
	)


def _posting_and_due(company: str, scheduled_due) -> tuple:
	"""Resolve posting and due dates for an installment invoice.

	ERPNext refuses a due date earlier than the posting date, which bites on
	*backfill* - generating an invoice for an installment whose due date has
	already passed. Forcing the due date forward to today would silently reset
	the debt's age and understate the ageing report, so instead the invoice is
	dated at its own due date whenever that period is still open. Only when the
	period is closed does it fall back to today, and then the due date moves with
	it rather than the other way round.
	"""
	today = getdate(nowdate())
	due = getdate(scheduled_due)

	if due >= today:
		return today, due

	if _period_open(company, due):
		return due, due

	return today, today


def _period_open(company: str, date) -> bool:
	from erpnext.accounts.utils import get_fiscal_year

	try:
		get_fiscal_year(date, company=company, as_dict=True)
	except Exception:
		return False
	return True


# --------------------------------------------------------------- doc events
def validate_school_invoice(doc, method=None):
	"""Keep the school dimensions coherent on any fee invoice."""
	if not doc.get("ags_fee_plan"):
		return

	plan = frappe.db.get_value(
		"AGS Fee Plan", doc.ags_fee_plan,
		["student", "payer_account", "campus", "company", "docstatus"],
		as_dict=True,
	)
	if not plan:
		return
	if plan.docstatus == 2:
		frappe.throw(_("Fee plan {0} is cancelled.").format(doc.ags_fee_plan))
	if plan.company != doc.company:
		frappe.throw(
			_("Invoice company {0} does not match the fee plan company {1}.").format(
				doc.company, plan.company
			)
		)
	doc.ags_student = doc.ags_student or plan.student
	doc.ags_payer_account = doc.ags_payer_account or plan.payer_account


def on_invoice_submit(doc, method=None):
	_sync_plan_and_payer(doc)


def on_invoice_cancel(doc, method=None):
	if doc.get("ags_fee_plan"):
		frappe.db.sql(
			"""
			update `tabAGS Fee Plan Installment`
			set sales_invoice = null, status = 'Pending', paid_amount = 0,
			    outstanding_amount = amount
			where parent = %(plan)s and sales_invoice = %(invoice)s
			""",
			{"plan": doc.ags_fee_plan, "invoice": doc.name},
		)
	_sync_plan_and_payer(doc)


def _sync_plan_and_payer(doc) -> None:
	from ags_edusmart.ags_fees.payer import refresh_payer_account

	if doc.get("ags_fee_plan"):
		try:
			frappe.get_doc("AGS Fee Plan", doc.ags_fee_plan).refresh_totals()
		except frappe.DoesNotExistError:
			pass
	if doc.get("ags_payer_account"):
		refresh_payer_account(doc.ags_payer_account)


def mark_overdue_installments(as_of: str | None = None) -> int:
	as_of = getdate(as_of or nowdate())
	return frappe.db.sql(
		"""
		update `tabAGS Fee Plan Installment`
		set status = 'Overdue'
		where status in ('Invoiced', 'Partially Paid')
		  and due_date < %(as_of)s
		""",
		{"as_of": as_of},
	)
