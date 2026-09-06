import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class AGSQuotationComparison(Document):
	def validate(self):
		self.validate_weights()
		self.score_suppliers()
		self.validate_award()

	def validate_weights(self):
		total = (
			flt(self.weight_price) + flt(self.weight_delivery)
			+ flt(self.weight_warranty) + flt(self.weight_rating)
		)
		if abs(total - 100) > 0.01:
			frappe.throw(
				_("Scoring weights must total 100%. They currently total {0}%.").format(total)
			)

	def score_suppliers(self):
		# Normalise each criterion to 0-100 within this comparison, then weight.
		# Price and delivery are "lower is better", so they are inverted.
		if not self.suppliers:
			return

		prices = [flt(r.price) for r in self.suppliers if flt(r.price) > 0]
		deliveries = [flt(r.delivery_days) for r in self.suppliers if flt(r.delivery_days) > 0]
		warranties = [flt(r.warranty_months) for r in self.suppliers]
		best_price = min(prices) if prices else 0
		best_delivery = min(deliveries) if deliveries else 0
		best_warranty = max(warranties) if warranties else 0

		best_row, best_score = None, -1.0
		for row in self.suppliers:
			price_score = (best_price / flt(row.price) * 100) if flt(row.price) else 0
			delivery_score = (
				best_delivery / flt(row.delivery_days) * 100
			) if flt(row.delivery_days) else 0
			warranty_score = (
				flt(row.warranty_months) / best_warranty * 100
			) if best_warranty else 0
			rating_score = flt(row.historical_rating)

			row.score = flt(
				price_score * flt(self.weight_price) / 100
				+ delivery_score * flt(self.weight_delivery) / 100
				+ warranty_score * flt(self.weight_warranty) / 100
				+ rating_score * flt(self.weight_rating) / 100,
				2,
			)
			row.is_recommended = 0
			if row.score > best_score:
				best_score, best_row = row.score, row

		if best_row:
			best_row.is_recommended = 1
			self.recommended_supplier = best_row.supplier

	def validate_award(self):
		# The recommendation is advisory; the award is a human decision, and
		# departing from the recommendation has to be explained (SKILL sec. 8.4).
		if not self.awarded_supplier:
			self.status = "Awaiting Award" if self.suppliers else "Draft"
			return

		listed = {row.supplier for row in self.suppliers}
		if self.awarded_supplier not in listed:
			frappe.throw(
				_("Awarded supplier {0} is not among the compared suppliers.").format(
					self.awarded_supplier
				)
			)
		if (
			self.recommended_supplier
			and self.awarded_supplier != self.recommended_supplier
			and not (self.justification or "").strip()
		):
			frappe.throw(
				_("Award justification is required when the award differs from the "
				  "system recommendation ({0}).").format(self.recommended_supplier),
				title=_("Justification Required"),
			)
		self.status = "Awarded"

	@frappe.whitelist()
	def make_purchase_order(self):
		if not self.awarded_supplier:
			frappe.throw(_("Select the awarded supplier first."))
		if self.purchase_order:
			return self.purchase_order

		row = next(
			(r for r in self.suppliers if r.supplier == self.awarded_supplier), None
		)
		if not row or not row.supplier_quotation:
			frappe.throw(
				_("The awarded supplier has no linked Supplier Quotation to convert.")
			)

		from erpnext.buying.doctype.supplier_quotation.supplier_quotation import (
			make_purchase_order,
		)

		order = make_purchase_order(row.supplier_quotation)
		order.flags.ignore_permissions = True
		order.insert()
		self.db_set("purchase_order", order.name)
		return order.name
