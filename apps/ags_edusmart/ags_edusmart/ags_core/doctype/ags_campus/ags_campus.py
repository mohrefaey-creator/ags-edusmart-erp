import frappe
from frappe import _
from frappe.model.document import Document


class AGSCampus(Document):
	def validate(self):
		self.validate_cost_center_company()

	def validate_cost_center_company(self):
		"""A campus pointing at a cost center in another company would split the
		ledger silently, so this is a hard stop rather than a warning."""
		if not self.cost_center:
			return
		cc_company = frappe.db.get_value("Cost Center", self.cost_center, "company")
		if cc_company and cc_company != self.company:
			frappe.throw(
				_("Cost Center {0} belongs to company {1}, but this campus belongs to {2}.").format(
					self.cost_center, cc_company, self.company
				),
				title=_("Company Mismatch"),
			)

	def on_trash(self):
		linked = frappe.db.count("AGS School Division", {"campus": self.name})
		if linked:
			frappe.throw(
				_("Cannot delete: {0} school division(s) still reference this campus.").format(linked)
			)
