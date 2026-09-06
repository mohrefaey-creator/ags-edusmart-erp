import frappe
from frappe import _
from frappe.model.document import Document


class AGSPayerAccount(Document):
	def validate(self):
		self.validate_customer()
		self.validate_students()
		self.sync_sibling_index()

	def on_update(self):
		self.link_students_back()

	def validate_customer(self):
		company = frappe.db.get_value("Customer", self.customer, "name")
		if not company:
			frappe.throw(_("Customer {0} does not exist.").format(self.customer))
		duplicate = frappe.db.get_value(
			"AGS Payer Account",
			{"customer": self.customer, "name": ("!=", self.name)},
			"name",
		)
		if duplicate:
			frappe.throw(
				_("Customer {0} is already used by payer account {1}. One customer "
				  "per payer keeps sibling invoices on a single statement.").format(
					self.customer, duplicate
				)
			)

	def validate_students(self):
		seen = set()
		for row in self.students:
			if row.student in seen:
				frappe.throw(_("Student {0} is listed twice.").format(row.student))
			seen.add(row.student)

	def sync_sibling_index(self):
		from ags_edusmart.ags_fees.discounts import sibling_index

		if not self.name or self.is_new():
			return
		for row in self.students:
			row.sibling_index = sibling_index(self.name, row.student)

	def link_students_back(self):
		# Keeps Student.ags_payer_account in step so the portal and the
		# permission query can go either direction without a join table.
		for row in self.students:
			current = frappe.db.get_value("Student", row.student, "ags_payer_account")
			if current != self.name and row.is_primary:
				frappe.db.set_value(
					"Student", row.student, "ags_payer_account", self.name,
					update_modified=False,
				)

	@frappe.whitelist()
	def refresh_summary(self):
		from ags_edusmart.ags_fees.payer import refresh_payer_account

		return refresh_payer_account(self.name)
