# Hooks on native Payment Entry. Parents "Pay School Fees"; the backend posts a
# standard Payment Entry and the AR ledger stays the only source of truth
# (SKILL sec. 19/29).
import frappe
from frappe import _
from frappe.utils import flt

from ags_edusmart.utils.dimensions import campus_field as campus_field_for


def validate_payment(doc, method=None):
	if doc.party_type != "Customer" or not doc.party:
		return

	payer = frappe.db.get_value(
		"AGS Payer Account", {"customer": doc.party}, ["name", "campus"], as_dict=True
	)
	if not payer:
		return

	# Carry the campus dimension so cash lands in the right P&L slice.
	campus_field = campus_field_for(doc.doctype)
	if campus_field and not doc.get(campus_field) and payer.campus:
		doc.set(campus_field, payer.campus)

	for ref in doc.references:
		if ref.reference_doctype != "Sales Invoice":
			continue
		invoice_customer = frappe.db.get_value("Sales Invoice", ref.reference_name, "customer")
		if invoice_customer and invoice_customer != doc.party:
			frappe.throw(
				_("Invoice {0} belongs to {1}, not {2}.").format(
					ref.reference_name, invoice_customer, doc.party
				)
			)


def on_payment_submit(doc, method=None):
	_resync(doc)


def on_payment_cancel(doc, method=None):
	_resync(doc)


def _resync(doc):
	from ags_edusmart.ags_collections.ageing import refresh_case_for_payer
	from ags_edusmart.ags_fees.payer import refresh_payer_account

	if doc.party_type != "Customer" or not doc.party:
		return

	plans = set()
	for ref in doc.references:
		if ref.reference_doctype != "Sales Invoice":
			continue
		plan = frappe.db.get_value("Sales Invoice", ref.reference_name, "ags_fee_plan")
		if plan:
			plans.add(plan)

	for plan in plans:
		try:
			frappe.get_doc("AGS Fee Plan", plan).refresh_totals()
		except frappe.DoesNotExistError:
			continue

	payer = frappe.db.get_value("AGS Payer Account", {"customer": doc.party}, "name")
	if payer:
		refresh_payer_account(payer)
		refresh_case_for_payer(payer)


@frappe.whitelist()
def outstanding_for_payer(payer_account):
	# Used by the parent portal to build a "pay now" basket.
	customer = frappe.db.get_value("AGS Payer Account", payer_account, "customer")
	if not customer:
		return []
	rows = frappe.get_all(
		"Sales Invoice",
		filters={"customer": customer, "docstatus": 1, "outstanding_amount": (">", 0)},
		fields=["name", "posting_date", "due_date", "grand_total", "outstanding_amount",
		        "ags_student", "ags_installment_no"],
		order_by="due_date asc",
	)
	for row in rows:
		row["outstanding_amount"] = flt(row["outstanding_amount"], 2)
	return rows
