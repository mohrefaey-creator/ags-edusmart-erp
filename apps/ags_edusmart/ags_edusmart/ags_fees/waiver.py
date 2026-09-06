# Fee waiver -> credit note.
#
# A waiver is written off through a native return Sales Invoice rather than by
# editing the original, so the AR ledger, the VAT return and the parent
# statement all stay consistent (SKILL sec. 29).
import frappe
from frappe import _
from frappe.utils import flt

from ags_edusmart.utils.dimensions import set_dimensions


def post_credit_note(doc):
	if doc.credit_note:
		return doc.credit_note

	invoice = frappe.get_doc("Sales Invoice", doc.sales_invoice)
	if invoice.docstatus != 1:
		frappe.throw(_("Invoice {0} is not submitted.").format(doc.sales_invoice))

	amount = flt(doc.waiver_amount, 2)
	if amount <= 0:
		frappe.throw(_("Waiver amount must be greater than zero."))
	if amount > flt(invoice.outstanding_amount):
		frappe.throw(
			_("Waiver of {0} exceeds the {1} outstanding on invoice {2}.").format(
				amount, invoice.outstanding_amount, invoice.name
			)
		)

	credit = frappe.new_doc("Sales Invoice")
	credit.customer = invoice.customer
	credit.company = invoice.company
	credit.is_return = 1
	credit.return_against = invoice.name
	credit.posting_date = doc.posting_date
	credit.set_posting_time = 1
	credit.due_date = doc.posting_date
	credit.debit_to = invoice.debit_to
	credit.ags_payer_account = doc.payer_account
	credit.ags_student = doc.student
	set_dimensions(credit, campus=doc.campus)

	# Proportional across the original lines keeps each revenue account reversed
	# by its own share instead of dumping the whole waiver on one account.
	total = flt(invoice.net_total) or flt(invoice.grand_total)
	remaining = amount
	rows = [row for row in invoice.items if flt(row.amount) > 0]
	for index, row in enumerate(rows):
		share = remaining if index == len(rows) - 1 else flt(amount * flt(row.amount) / total, 2)
		if index != len(rows) - 1:
			remaining = flt(remaining - share, 2)
		if share <= 0:
			continue
		credit.append("items", {
			"item_code": row.item_code,
			"description": f"Fee waiver against {invoice.name}",
			"qty": -1,
			"rate": share,
			"income_account": row.income_account,
			"cost_center": row.cost_center,
		})

	if not credit.items:
		frappe.throw(_("Nothing to waive on invoice {0}.").format(invoice.name))

	credit.flags.ignore_permissions = True
	credit.insert()
	credit.submit()

	doc.db_set("credit_note", credit.name, update_modified=False)

	from ags_edusmart.ags_fees.payer import refresh_payer_account

	refresh_payer_account(doc.payer_account)
	return credit.name
