"""AGS Fee Plan - the priced, student-specific plan (SKILL sec. 17.5).

Pipeline: Fee Structure -> components -> discount rules -> installments -> invoices.

The plan is the single source of truth for what a student owes. Invoices are
generated *from* installments (one invoice per installment), which is what keeps
the parent statement and the AR ledger reconcilable.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, add_months, flt, getdate

from ags_edusmart.ags_fees.discounts import ComponentBase, apply_scholarship, compute, sibling_index


class AGSFeePlan(Document):
	# ------------------------------------------------------------- lifecycle
	def validate(self):
		self.set_defaults()
		self.validate_payer_link()
		self.pull_structure_if_empty()
		self.calculate()
		self.build_schedule()
		self.validate_schedule_total()

	def on_submit(self):
		self.db_set("status", "Active")
		self.refresh_payer_summary()

	def on_cancel(self):
		self.ignore_linked_doctypes = ("GL Entry",)
		open_invoices = [
			row.sales_invoice for row in self.installments
			if row.sales_invoice and frappe.db.get_value(
				"Sales Invoice", row.sales_invoice, "docstatus"
			) == 1
		]
		if open_invoices:
			frappe.throw(
				_("Cancel the linked invoice(s) first: {0}").format(", ".join(open_invoices))
			)
		self.db_set("status", "Cancelled")
		self.refresh_payer_summary()

	# -------------------------------------------------------------- defaults
	def set_defaults(self):
		if not self.company and self.campus:
			self.company = frappe.db.get_value("AGS Campus", self.campus, "company")
		if not self.campus:
			self.campus = frappe.db.get_value("Student", self.student, "ags_campus")
		# Not `if not self.currency`: for a Link-to-Currency field Frappe applies
		# the *user* default (Global Defaults, INR out of the box) ahead of the
		# field's own default, so a new plan arrives already populated with the
		# wrong currency. The receivable account is in company currency, and
		# billing a parent in anything else breaks the AR ledger, so this is
		# aligned rather than merely defaulted.
		company_currency = frappe.get_cached_value(
			"Company", self.company, "default_currency"
		)
		if company_currency and self.currency != company_currency:
			self.currency = company_currency
		if not self.cost_center and self.campus:
			self.cost_center = frappe.db.get_value("AGS Campus", self.campus, "cost_center")
		if not self.receivable_account and self.campus:
			self.receivable_account = frappe.db.get_value(
				"AGS Campus", self.campus, "default_receivable_account"
			)

	def validate_payer_link(self):
		"""The student must actually be listed on the payer account, otherwise a
		sibling discount would be computed against someone else's family."""
		linked = frappe.db.exists(
			"AGS Payer Student",
			{
				"parent": self.payer_account,
				"parenttype": "AGS Payer Account",
				"student": self.student,
			},
		)
		if not linked:
			frappe.throw(
				_("Student {0} is not listed on payer account {1}. Add the child there first.")
				.format(self.student, self.payer_account),
				title=_("Payer Mismatch"),
			)

	# ------------------------------------------------------------ components
	def pull_structure_if_empty(self):
		if self.components or not self.fee_structure:
			return

		structure = frappe.get_cached_doc("Fee Structure", self.fee_structure)
		for row in structure.components:
			item = row.item or frappe.db.get_value("Fee Category", row.fees_category, "item")
			self.append("components", {
				"fees_category": row.fees_category,
				"item": item,
				"description": row.description,
				"gross_amount": flt(row.amount),
				"is_discountable": 1,
				"income_account": _income_account_for(item, self.company),
			})
		if not self.receivable_account:
			self.receivable_account = structure.receivable_account

	def calculate(self):
		if not self.components:
			frappe.throw(_("Add at least one fee component."))

		working = [
			ComponentBase(
				row_name=row.name or f"row-{row.idx}",
				fees_category=row.fees_category,
				gross=flt(row.gross_amount),
				discountable=bool(row.is_discountable),
			)
			for row in self.components
		]
		by_key = {c.row_name: c for c in working}

		# Discount rows the user pinned by hand (scholarships, approved
		# exceptions) are preserved; auto-matched rule rows are rebuilt.
		manual = [
			row for row in (self.discounts or [])
			if row.scholarship or row.status in ("Pending Approval", "Rejected")
			or (row.approval_reference and row.status == "Applied")
		]
		self.discounts = []

		for row in manual:
			if row.scholarship and row.status == "Applied":
				result = apply_scholarship(row.scholarship, working)
				if result:
					self._append_discount(result)
					continue
			self.append("discounts", {
				"discount_rule": row.discount_rule,
				"scholarship": row.scholarship,
				"discount_type": row.discount_type,
				"calculation": row.calculation,
				"value": row.value,
				"discount_amount": flt(row.discount_amount) if row.status == "Applied" else 0,
				"status": row.status,
				"approval_reference": row.approval_reference,
				"notes": row.notes,
			})
			if row.status == "Applied" and flt(row.discount_amount):
				_spread_manual(working, flt(row.discount_amount))

		if self.auto_apply_discounts:
			ctx = {
				"company": self.company,
				"campus": self.campus,
				"academic_year": self.academic_year,
				"program": self.program,
				"student_category": self.student_category,
				"division_type": frappe.db.get_value(
					"AGS School Division", self.school_division, "division_type"
				) if self.school_division else None,
				"sibling_index": sibling_index(self.payer_account, self.student),
			}
			for result in compute(working, ctx):
				self._append_discount(result)

		for row in self.components:
			key = row.name or f"row-{row.idx}"
			comp = by_key[key]
			row.discount_amount = flt(comp.discount, 2)
			row.net_amount = flt(comp.net, 2)

		self.gross_total = flt(sum(flt(r.gross_amount) for r in self.components), 2)
		self.discount_total = flt(sum(flt(r.discount_amount) for r in self.components), 2)
		self.net_total = flt(self.gross_total - self.discount_total, 2)

	def _append_discount(self, result):
		self.append("discounts", {
			"discount_rule": result.rule,
			"scholarship": result.scholarship,
			"discount_type": result.discount_type,
			"calculation": result.calculation,
			"value": result.value,
			"discount_amount": result.amount if result.status == "Applied" else 0,
			"status": result.status,
			"notes": result.notes,
		})

	# ------------------------------------------------------------- schedule
	def build_schedule(self):
		"""Rebuild installments, preserving any that already carry an invoice."""
		invoiced = {
			row.installment_no: row for row in (self.installments or []) if row.sales_invoice
		}

		count, dates = self._schedule_dates()
		# Amounts come from the per-component allocation rather than a split of
		# the plan total, so an invoice line always lands on the right revenue
		# account and the installment still sums exactly to the net payable.
		allocation = self.component_allocation(count)
		amounts = [flt(sum(r["amount"] for r in rows), 2) for rows in allocation]

		rebuilt = []
		for index in range(count):
			number = index + 1
			if number in invoiced:
				rebuilt.append(invoiced[number].as_dict())
				continue
			rebuilt.append({
				"installment_no": number,
				"label": _installment_label(self.schedule_type, number, count),
				"due_date": dates[index],
				"amount": amounts[index],
				"paid_amount": 0,
				"outstanding_amount": amounts[index],
				"status": "Pending",
			})

		self.installments = []
		for row in rebuilt:
			self.append("installments", row)

	def component_allocation(self, count: int) -> list[list[dict]]:
		"""Split every component's net across ``count`` installments.

		Each component is split independently and the remainder lands on its own
		last slice, so no rounding drift accumulates into the plan total.
		"""
		splits = {
			row.idx: _split_amount(flt(row.net_amount), count) for row in self.components
		}
		matrix: list[list[dict]] = []
		for index in range(count):
			rows = []
			for row in self.components:
				amount = splits[row.idx][index]
				if not amount:
					continue
				rows.append({
					"idx": row.idx,
					"fees_category": row.fees_category,
					"item": row.item,
					"description": row.description,
					"income_account": row.income_account,
					"amount": amount,
				})
			matrix.append(rows)
		return matrix

	def _schedule_dates(self) -> tuple[int, list]:
		start = getdate(self.first_due_date)

		if self.schedule_type == "Annual":
			return 1, [start]

		if self.schedule_type == "By Term":
			terms = frappe.get_all(
				"Academic Term",
				filters={"academic_year": self.academic_year},
				fields=["name", "term_start_date"],
				order_by="term_start_date asc",
			)
			if terms:
				dates = [getdate(t.term_start_date or start) for t in terms]
				# Never bill before the plan's own first due date.
				dates = [max(d, start) for d in dates]
				return len(dates), dates
			return 3, [add_months(start, i * 4) for i in range(3)]

		if self.schedule_type == "Quarterly":
			return 4, [add_months(start, i * 3) for i in range(4)]

		if self.schedule_type == "Monthly":
			count = 10  # a school year, not a calendar year
			return count, [add_months(start, i) for i in range(count)]

		count = max(1, int(self.number_of_installments or 1))
		gap = max(1, int(self.installment_gap_days or 30))
		return count, [add_days(start, i * gap) for i in range(count)]

	def validate_schedule_total(self):
		total = flt(sum(flt(r.amount) for r in self.installments), 2)
		if abs(total - flt(self.net_total, 2)) > 0.01:
			frappe.throw(
				_("Installments total {0} does not match the net payable {1}.").format(
					total, self.net_total
				)
			)

	# --------------------------------------------------------------- totals
	def refresh_totals(self):
		invoiced = paid = 0.0
		for row in self.installments:
			if not row.sales_invoice:
				continue
			inv = frappe.db.get_value(
				"Sales Invoice", row.sales_invoice,
				["grand_total", "outstanding_amount", "docstatus", "status"],
				as_dict=True,
			)
			if not inv or inv.docstatus != 1:
				continue
			row_paid = flt(inv.grand_total) - flt(inv.outstanding_amount)
			invoiced += flt(inv.grand_total)
			paid += row_paid
			row.db_set("paid_amount", flt(row_paid, 2), update_modified=False)
			row.db_set(
				"outstanding_amount", flt(inv.outstanding_amount, 2), update_modified=False
			)
			row.db_set("status", _installment_status(row, inv), update_modified=False)

		self.db_set("invoiced_total", flt(invoiced, 2), update_modified=False)
		self.db_set("paid_total", flt(paid, 2), update_modified=False)
		self.db_set(
			"outstanding_total", flt(self.net_total - paid, 2), update_modified=False
		)
		if flt(self.net_total - paid, 2) <= 0 and invoiced > 0:
			self.db_set("status", "Completed", update_modified=False)

	def refresh_payer_summary(self):
		from ags_edusmart.ags_fees.payer import refresh_payer_account

		if self.payer_account:
			refresh_payer_account(self.payer_account)

	# ------------------------------------------------------------ invoicing
	@frappe.whitelist()
	def create_invoice(self, installment_no: int):
		from ags_edusmart.ags_fees.invoicing import create_invoice_for_installment

		return create_invoice_for_installment(self.name, int(installment_no))


# ------------------------------------------------------------------ helpers
def _income_account_for(item: str | None, company: str) -> str | None:
	if not item:
		return None
	return frappe.db.get_value(
		"Item Default", {"parent": item, "company": company}, "income_account"
	)


def _split_amount(total: float, count: int) -> list[float]:
	"""Even split with the remainder on the final installment, so the parts
	always sum back to the total."""
	total = flt(total, 2)
	if count <= 1:
		return [total]
	each = flt(total / count, 2)
	parts = [each] * (count - 1)
	parts.append(flt(total - each * (count - 1), 2))
	return parts


def _installment_label(schedule_type: str, number: int, count: int) -> str:
	if schedule_type == "Annual":
		return _("Full Year")
	if schedule_type == "By Term":
		return _("Term {0}").format(number)
	if schedule_type == "Quarterly":
		return _("Quarter {0}").format(number)
	if schedule_type == "Monthly":
		return _("Month {0}").format(number)
	return _("Installment {0} of {1}").format(number, count)


def _installment_status(row, invoice) -> str:
	outstanding = flt(invoice.outstanding_amount)
	if outstanding <= 0:
		return "Paid"
	if outstanding < flt(invoice.grand_total):
		return "Partially Paid"
	if row.due_date and getdate(row.due_date) < getdate():
		return "Overdue"
	return "Invoiced"


def _spread_manual(components: list[ComponentBase], amount: float) -> None:
	"""Distribute an already-approved manual discount across discountable rows."""
	rows = [c for c in components if c.discountable and c.net > 0]
	base = flt(sum(c.net for c in rows), 2)
	if base <= 0 or amount <= 0:
		return
	amount = min(amount, base)
	remaining = amount
	for idx, row in enumerate(rows):
		share = remaining if idx == len(rows) - 1 else flt(amount * (row.net / base), 2)
		if idx != len(rows) - 1:
			remaining = flt(remaining - share, 2)
		row.discount = flt(row.discount + share, 2)
