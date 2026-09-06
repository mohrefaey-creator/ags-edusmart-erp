import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class AGSFeeWaiver(Document):
	def validate(self):
		invoice = frappe.db.get_value(
			"Sales Invoice", self.sales_invoice,
			["customer", "company", "outstanding_amount", "docstatus", "ags_payer_account"],
			as_dict=True,
		)
		if not invoice:
			frappe.throw(_("Invoice {0} not found.").format(self.sales_invoice))
		if invoice.docstatus != 1:
			frappe.throw(_("Invoice {0} is not submitted.").format(self.sales_invoice))

		payer_customer = frappe.db.get_value("AGS Payer Account", self.payer_account, "customer")
		if payer_customer != invoice.customer:
			frappe.throw(
				_("Invoice {0} is billed to {1}, not to this payer account.").format(
					self.sales_invoice, invoice.customer
				)
			)
		if flt(self.waiver_amount) > flt(invoice.outstanding_amount):
			frappe.throw(
				_("Waiver of {0} exceeds the {1} outstanding.").format(
					self.waiver_amount, invoice.outstanding_amount
				)
			)
		self.company = invoice.company

	def before_submit(self):
		self.approval_status = "Pending"

	def on_cancel(self):
		if self.credit_note:
			frappe.throw(
				_("Cancel credit note {0} first.").format(self.credit_note)
			)
