import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now


class AGSCollectionCase(Document):
	def validate(self):
		self.stamp_actions()
		self.validate_resolution()

	def stamp_actions(self):
		for row in self.actions:
			if not row.action_by:
				row.action_by = frappe.session.user
			if not row.action_date:
				row.action_date = now()

	def validate_resolution(self):
		# Closing a case with money still on it hides real exposure, so it is
		# only allowed as an explicit write-off.
		if self.status == "Resolved" and (self.overdue or 0) > 0:
			frappe.throw(
				_("This case still has {0} overdue. Use 'Written Off' if the debt is "
				  "being written off, or collect the balance first.").format(self.overdue)
			)

	@frappe.whitelist()
	def refresh_from_ledger(self):
		from ags_edusmart.ags_collections.ageing import refresh_case_for_payer

		refresh_case_for_payer(self.payer_account, create_if_missing=False)
		self.reload()
		return self.as_dict()
