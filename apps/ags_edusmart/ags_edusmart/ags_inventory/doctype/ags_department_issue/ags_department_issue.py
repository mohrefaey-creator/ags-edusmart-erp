"""Department Issue - the school-facing "Issue Materials" (SKILL sec. 9.4/9.5).

A storekeeper never sees "Stock Entry / Material Issue". They pick a store, a
department and some items; this posts the native Stock Entry so there is still
exactly one stock ledger, and attributes the consumption to the department's cost
center so "Stationery cost per student" is answerable later.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class AGSDepartmentIssue(Document):
	def validate(self):
		self.set_defaults()
		self.fetch_rates_and_availability()
		self.calculate_totals()
		self.validate_stock()

	def on_submit(self):
		entry = self.make_stock_entry()
		self.db_set("stock_entry", entry.name)
		self.db_set("status", "Issued")

	def on_cancel(self):
		self.ignore_linked_doctypes = ("Stock Ledger Entry", "GL Entry")
		if self.stock_entry:
			entry = frappe.get_doc("Stock Entry", self.stock_entry)
			if entry.docstatus == 1:
				entry.flags.ignore_permissions = True
				entry.cancel()
		self.db_set("status", "Cancelled")

	# -------------------------------------------------------------- defaults
	def set_defaults(self):
		if not self.company and self.campus:
			self.company = frappe.db.get_value("AGS Campus", self.campus, "company")
		if not self.source_warehouse and self.campus:
			self.source_warehouse = frappe.db.get_value(
				"AGS Campus", self.campus, "default_warehouse"
			)
		if not self.cost_center and self.department:
			# Department -> cost center, falling back to the campus cost center.
			self.cost_center = frappe.db.get_value(
				"Department", self.department, "payroll_cost_center"
			) or frappe.db.get_value("AGS Campus", self.campus, "cost_center")

	def fetch_rates_and_availability(self):
		from erpnext.stock.utils import get_stock_balance

		for row in self.items:
			if not row.uom:
				row.uom = frappe.db.get_value("Item", row.item_code, "stock_uom")
			row.available_qty = flt(
				get_stock_balance(row.item_code, self.source_warehouse, self.posting_date)
			)
			if not row.rate:
				row.rate = flt(
					frappe.db.get_value(
						"Bin",
						{"item_code": row.item_code, "warehouse": self.source_warehouse},
						"valuation_rate",
					)
				)
			row.amount = flt(flt(row.qty) * flt(row.rate), 2)

	def calculate_totals(self):
		self.total_qty = flt(sum(flt(r.qty) for r in self.items), 3)
		self.total_amount = flt(sum(flt(r.amount) for r in self.items), 2)

	def validate_stock(self):
		for row in self.items:
			if flt(row.qty) <= 0:
				frappe.throw(_("Row {0}: quantity must be greater than zero.").format(row.idx))
			if flt(row.qty) > flt(row.available_qty):
				frappe.throw(
					_("Row {0}: only {1} {2} of {3} available in {4}.").format(
						row.idx, row.available_qty, row.uom, row.item_code,
						self.source_warehouse
					),
					title=_("Insufficient Stock"),
				)

	# ------------------------------------------------------------ stock entry
	def make_stock_entry(self):
		entry = frappe.new_doc("Stock Entry")
		entry.stock_entry_type = "Material Issue"
		entry.purpose = "Material Issue"
		entry.company = self.company
		entry.posting_date = self.posting_date
		entry.set_posting_time = 1
		entry.remarks = _("AGS Department Issue {0} - {1}").format(self.name, self.purpose)

		for row in self.items:
			entry.append("items", {
				"item_code": row.item_code,
				"qty": row.qty,
				"uom": row.uom,
				"stock_uom": frappe.db.get_value("Item", row.item_code, "stock_uom"),
				"conversion_factor": 1,
				"s_warehouse": self.source_warehouse,
				"cost_center": self.cost_center,
			})

		entry.flags.ignore_permissions = True
		entry.insert()
		entry.submit()
		return entry


@frappe.whitelist()
def department_consumption(company: str, from_date: str, to_date: str,
                           campus: str | None = None) -> list[dict]:
	"""Consumption by department, for the inventory dashboard (SKILL sec. 9.6)."""
	conditions = ["di.docstatus = 1", "di.company = %(company)s",
	              "di.posting_date between %(from_date)s and %(to_date)s"]
	params = {"company": company, "from_date": from_date, "to_date": to_date}
	if campus:
		conditions.append("di.campus = %(campus)s")
		params["campus"] = campus

	return frappe.db.sql(
		f"""
		select di.department, di.campus,
		       sum(di.total_amount) as amount,
		       count(distinct di.name) as issues
		from `tabAGS Department Issue` di
		where {" and ".join(conditions)}
		group by di.department, di.campus
		order by amount desc
		""",
		params,
		as_dict=True,
	)
