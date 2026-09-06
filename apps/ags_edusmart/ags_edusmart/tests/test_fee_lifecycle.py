"""End-to-end fee lifecycle against a real ledger.

Enrollment pricing -> discounts -> installments -> Sales Invoice -> Payment Entry
-> payer statement -> collection case.

The assertions are the handover's own worked example (SKILL sec. 17.3, 17.6, 18),
so a regression here is visible as a number that no longer matches the spec.
"""

from __future__ import annotations

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, getdate, nowdate

from ags_edusmart.ags_collections.ageing import compute_ageing, refresh_case_for_payer
from ags_edusmart.ags_fees.discounts import sibling_index
from ags_edusmart.ags_fees.invoicing import create_invoice_for_installment
from ags_edusmart.ags_fees.payer import compute_summary, refresh_payer_account
from ags_edusmart.setup import demo


class TestFeeLifecycle(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.data = demo.build()
		cls.payer = cls.data["payer"]
		cls.company = cls.data["company"]
		cls.campus = cls.data["campuses"][0]
		cls.structure = cls.data["fee_structure"]
		cls.year = cls.data["academic_year"]
		cls.ali = frappe.db.get_value("Student", {"first_name": "Ali"}, "name")
		cls.sara = frappe.db.get_value("Student", {"first_name": "Sara"}, "name")
		cls.omar = frappe.db.get_value("Student", {"first_name": "Omar"}, "name")

	# ------------------------------------------------------------- siblings
	def test_sibling_index_is_by_age_eldest_first(self):
		# Registration order must not move the tier; date of birth decides.
		self.assertEqual(sibling_index(self.payer, self.ali), 1)
		self.assertEqual(sibling_index(self.payer, self.sara), 2)
		self.assertEqual(sibling_index(self.payer, self.omar), 3)

	# ----------------------------------------------------------- pricing
	def _make_plan(self, student, program):
		plan = frappe.get_doc({
			"doctype": "AGS Fee Plan",
			"student": student,
			"payer_account": self.payer,
			"company": self.company,
			"campus": self.campus,
			"academic_year": self.year,
			"program": program,
			"fee_structure": self.structure,
			"schedule_type": "By Term",
			"first_due_date": add_days(nowdate(), 7),
			"auto_apply_discounts": 1,
		})
		plan.flags.ignore_permissions = True
		plan.insert()
		return plan

	def test_eldest_child_gets_no_sibling_discount(self):
		plan = self._make_plan(self.ali, "Grade 8")
		self.assertEqual(flt(plan.gross_total), 24500.0)
		self.assertEqual(flt(plan.discount_total), 0.0)
		self.assertEqual(flt(plan.net_total), 24500.0)

	def test_second_child_gets_ten_percent_of_tuition_only(self):
		"""SKILL sec. 17.6: tuition eligible; books, registration excluded."""
		plan = self._make_plan(self.sara, "Grade 5")
		self.assertEqual(flt(plan.gross_total), 24500.0)
		self.assertEqual(flt(plan.discount_total), 2000.0)  # 10% of 20,000
		self.assertEqual(flt(plan.net_total), 22500.0)

		by_category = {r.fees_category: r for r in plan.components}
		self.assertEqual(flt(by_category["Tuition Fee"].discount_amount), 2000.0)
		self.assertEqual(flt(by_category["Tuition Fee"].net_amount), 18000.0)
		# Every non-tuition line must be untouched.
		for category in ("Registration Fee", "Books", "Activity Fee", "Technology Fee"):
			self.assertEqual(
				flt(by_category[category].discount_amount), 0.0,
				f"{category} must not be discounted by the sibling rule",
			)

	def test_third_child_gets_fifteen_percent_of_tuition_only(self):
		plan = self._make_plan(self.omar, "KG2")
		self.assertEqual(flt(plan.discount_total), 3000.0)  # 15% of 20,000
		self.assertEqual(flt(plan.net_total), 21500.0)

	# ---------------------------------------------------------- installments
	def test_installments_sum_to_the_net_payable(self):
		plan = self._make_plan(self.sara, "Grade 5")
		total = flt(sum(flt(r.amount) for r in plan.installments), 2)
		self.assertEqual(total, flt(plan.net_total))
		self.assertEqual(len(plan.installments), 3)  # three academic terms

	def test_component_allocation_reconciles_per_installment(self):
		plan = self._make_plan(self.sara, "Grade 5")
		allocation = plan.component_allocation(len(plan.installments))
		for index, rows in enumerate(allocation):
			self.assertEqual(
				flt(sum(r["amount"] for r in rows), 2),
				flt(plan.installments[index].amount),
			)
		# And the whole matrix reconciles to the plan.
		grand = flt(sum(r["amount"] for rows in allocation for r in rows), 2)
		self.assertEqual(grand, flt(plan.net_total))

	def test_plan_rejects_a_student_not_on_the_payer_account(self):
		stranger = frappe.get_doc({
			"doctype": "Student",
			"naming_series": demo._student_series(),
			"first_name": "Unrelated",
			"last_name": "Child",
			"student_email_id": "unrelated.child@example.com",
			"date_of_birth": "2014-01-01",
		})
		stranger.flags.ignore_permissions = True
		stranger.insert()

		with self.assertRaises(frappe.ValidationError):
			self._make_plan(stranger.name, "Grade 5")

	# --------------------------------------------------------------- money
	def test_invoice_payment_and_statement(self):
		# Deltas, not absolutes. The reference dataset commits a part-paid
		# invoice for this same family (demo.run_finance_journey), so a test that
		# assumed an empty ledger would pass only on a pristine site.
		payer_customer = frappe.db.get_value(
			"AGS Payer Account", self.payer, "customer"
		)
		opening = compute_summary(payer_customer)

		plan = self._make_plan(self.sara, "Grade 5")
		plan.submit()

		invoice_name = create_invoice_for_installment(plan.name, 1)
		invoice = frappe.get_doc("Sales Invoice", invoice_name)

		# Billed to the payer's customer, not the student's - that is what puts
		# three siblings on one statement.
		self.assertEqual(invoice.customer, payer_customer)
		self.assertEqual(invoice.ags_student, self.sara)
		self.assertEqual(flt(invoice.grand_total), 7500.0)
		self.assertEqual(invoice.docstatus, 1)

		# Revenue landed on more than one income account, because the installment
		# carries a slice of every fee component.
		accounts = {row.income_account for row in invoice.items}
		self.assertGreater(len(accounts), 1)

		after_invoice = compute_summary(payer_customer)
		self.assertEqual(
			flt(after_invoice["outstanding"] - opening["outstanding"], 2), 7500.0
		)
		self.assertEqual(
			flt(after_invoice["total_billed"] - opening["total_billed"], 2), 7500.0
		)

		self._pay(invoice, 3000.0)

		after_payment = compute_summary(payer_customer)
		self.assertEqual(
			flt(after_payment["total_paid"] - opening["total_paid"], 2), 3000.0
		)
		self.assertEqual(
			flt(after_payment["outstanding"] - opening["outstanding"], 2), 4500.0
		)

		refresh_payer_account(self.payer)
		stored = flt(
			frappe.db.get_value("AGS Payer Account", self.payer, "outstanding")
		)
		self.assertEqual(flt(stored - opening["outstanding"], 2), 4500.0)

		plan.reload()
		plan.refresh_totals()
		plan.reload()
		self.assertEqual(flt(plan.paid_total), 3000.0)
		self.assertEqual(flt(plan.installments[0].paid_amount), 3000.0)
		self.assertEqual(plan.installments[0].status, "Partially Paid")

	def _pay(self, invoice, amount):
		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

		payment = get_payment_entry("Sales Invoice", invoice.name)
		payment.paid_amount = amount
		payment.received_amount = amount
		payment.reference_no = "TEST-PAY"
		payment.reference_date = nowdate()
		payment.references = []
		payment.append("references", {
			"reference_doctype": "Sales Invoice",
			"reference_name": invoice.name,
			"total_amount": invoice.grand_total,
			"outstanding_amount": invoice.outstanding_amount,
			"allocated_amount": amount,
		})
		payment.flags.ignore_permissions = True
		payment.insert()
		payment.submit()
		return payment

	# ---------------------------------------------------------- collections
	def test_overdue_invoice_opens_a_collection_case_with_correct_buckets(self):
		# A By Term schedule clamps every due date forward to the term start, so
		# it cannot produce a genuinely aged debt. A custom schedule can.
		plan = self._make_plan(self.sara, "Grade 5")
		plan.schedule_type = "Custom"
		plan.number_of_installments = 2
		plan.installment_gap_days = 30
		plan.first_due_date = add_days(nowdate(), -45)
		plan.save()
		plan.submit()

		self.assertEqual(
			plan.installments[0].due_date, getdate(add_days(nowdate(), -45))
		)

		create_invoice_for_installment(plan.name, 1)

		payer_customer = frappe.db.get_value("AGS Payer Account", self.payer, "customer")
		ageing = compute_ageing(payer_customer)
		self.assertGreater(flt(ageing["overdue"]), 0)
		self.assertGreaterEqual(ageing["days_overdue"], 45)
		self.assertGreater(flt(ageing["buckets"]["bucket_31_60"]), 0)

		case = refresh_case_for_payer(self.payer)
		self.assertIsNotNone(case)
		doc = frappe.get_doc("AGS Collection Case", case)
		self.assertGreater(flt(doc.overdue), 0)
		self.assertEqual(doc.payer_account, self.payer)
