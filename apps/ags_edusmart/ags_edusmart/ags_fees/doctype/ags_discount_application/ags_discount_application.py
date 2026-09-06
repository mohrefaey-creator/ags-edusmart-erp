import frappe
from frappe import _
from frappe.model.document import Document

from ags_edusmart.ags_fees.discount_application import compute_amounts


class AGSDiscountApplication(Document):
	def validate(self):
		compute_amounts(self)
		self.set_required_role()

	def before_submit(self):
		# Submitting is the act of *requesting*; the approval engine picks it up
		# from on_change and drives it from there.
		self.approval_status = "Pending"

	def on_cancel(self):
		if self.applied:
			frappe.throw(
				_("This discount has already been applied to {0}. "
				  "Raise a new application to reverse it.").format(self.fee_plan)
			)
		self.db_set("approval_status", "Draft")

	def set_required_role(self):
		from ags_edusmart.ags_approvals.engine import pick_matrix, required_levels

		matrix = pick_matrix(self)
		if not matrix:
			self.required_role = None
			return
		levels = required_levels(matrix["name"], self.discount_percent or 0)
		self.required_role = levels[-1].approver_role if levels else None
