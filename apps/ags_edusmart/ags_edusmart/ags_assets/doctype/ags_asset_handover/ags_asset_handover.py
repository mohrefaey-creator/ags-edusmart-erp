import frappe
from frappe import _
from frappe.model.document import Document


class AGSAssetHandover(Document):
	def validate(self):
		self.validate_parties()
		self.validate_assets()

	def on_submit(self):
		movement = self.make_asset_movement()
		self.db_set("asset_movement", movement.name)
		self.db_set(
			"status",
			"Pending Acknowledgement" if self.requires_acknowledgement else "Active",
		)

	def on_cancel(self):
		self.ignore_linked_doctypes = ("Asset Movement",)
		if self.asset_movement:
			movement = frappe.get_doc("Asset Movement", self.asset_movement)
			if movement.docstatus == 1:
				movement.flags.ignore_permissions = True
				movement.cancel()
		self.db_set("status", "Cancelled")

	def validate_parties(self):
		if self.handover_type == "Issue To Employee" and not self.to_employee:
			frappe.throw(_("Select the employee receiving the assets."))
		if self.handover_type == "Return To Store" and not self.to_location:
			frappe.throw(_("Select the location the assets are returning to."))
		if self.handover_type == "Transfer Between Employees":
			if not (self.from_employee and self.to_employee):
				frappe.throw(_("A transfer needs both a from and a to employee."))
			if self.from_employee == self.to_employee:
				frappe.throw(_("From and to employee are the same."))

	def validate_assets(self):
		if not self.assets:
			frappe.throw(_("Add at least one asset."))

		seen = set()
		for row in self.assets:
			if row.asset in seen:
				frappe.throw(_("Asset {0} is listed twice.").format(row.asset))
			seen.add(row.asset)

			# An asset already signed out to someone else must be returned first.
			held_by = frappe.db.get_value("Asset", row.asset, "custodian")
			if (
				self.handover_type == "Issue To Employee"
				and held_by
				and held_by != self.to_employee
			):
				frappe.throw(
					_("Asset {0} is currently held by {1}. Record a return or a "
					  "transfer instead.").format(row.asset, held_by)
				)

	def make_asset_movement(self):
		purpose = {
			"Issue To Employee": "Issue",
			"Return To Store": "Receipt",
			"Transfer Between Employees": "Transfer",
		}[self.handover_type]

		movement = frappe.new_doc("Asset Movement")
		movement.company = self.company
		movement.purpose = purpose
		movement.transaction_date = self.handover_date
		movement.reference_doctype = self.doctype
		movement.reference_name = self.name

		for row in self.assets:
			entry = {"asset": row.asset}
			if purpose == "Issue":
				entry["to_employee"] = self.to_employee
				entry["source_location"] = self.from_location
			elif purpose == "Receipt":
				entry["from_employee"] = self.from_employee
				entry["target_location"] = self.to_location
			else:
				entry["from_employee"] = self.from_employee
				entry["to_employee"] = self.to_employee
			movement.append("assets", entry)

		movement.flags.ignore_permissions = True
		movement.insert()
		movement.submit()
		return movement
