"""Commitment accounting and the approval matrix (SKILL sec. 7.1, 8.3, 23).

The property under test is the one ERPNext does not give you: budget that is
already *promised* stops being available before any invoice exists.
"""

from __future__ import annotations

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, nowdate

from ags_edusmart.ags_approvals import engine
from ags_edusmart.ags_procurement import commitments
from ags_edusmart.setup import demo

BUDGET_AMOUNT = 100000.0


def stock_item() -> str:
	"""A real stock item to requisition. Shared by both test classes."""
	code = "TEST-GLOVES"
	if frappe.db.exists("Item", code):
		return code
	doc = frappe.get_doc({
		"doctype": "Item",
		"item_code": code,
		"item_name": "Laboratory Gloves",
		"item_group": "Fee Component",
		"stock_uom": "Nos",
		"is_stock_item": 1,
		"valuation_rate": 100,
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


class TestCommitmentAccounting(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.data = demo.build()
		cls.company = cls.data["company"]
		cls.campus = cls.data["campuses"][0]
		cls.cost_center = frappe.db.get_value("AGS Campus", cls.campus, "cost_center")
		cls.account = cls._expense_account()
		cls.item = stock_item()
		cls.fiscal_year = commitments.fiscal_year_for(nowdate())
		cls._budget()

	@classmethod
	def _expense_account(cls):
		name = f"Teaching Materials - {demo.ABBR}"
		if not frappe.db.exists("Account", name):
			return demo._account("Teaching Materials", "Direct Expenses", cls.company, "Expense")
		return name

	@classmethod
	def _budget(cls):
		"""Budget in the v16 shape: account and amount live on the Budget itself,
		bounded by a from/to fiscal year rather than a single one."""
		existing = frappe.db.exists("Budget", {
			"company": cls.company,
			"cost_center": cls.cost_center,
			"account": cls.account,
			"docstatus": 1,
		})
		if existing:
			return
		doc = frappe.get_doc({
			"doctype": "Budget",
			"company": cls.company,
			"budget_against": "Cost Center",
			"cost_center": cls.cost_center,
			"account": cls.account,
			"budget_amount": BUDGET_AMOUNT,
			"from_fiscal_year": cls.fiscal_year,
			"to_fiscal_year": cls.fiscal_year,
			"distribution_frequency": "Yearly",
			"applicable_on_material_request": 1,
			"applicable_on_purchase_order": 1,
			"applicable_on_booking_actual_expenses": 1,
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()

	# ------------------------------------------------------------- budget
	def test_budget_is_visible_before_anything_is_committed(self):
		status = commitments.available_budget(
			self.company, self.account, self.cost_center, self.fiscal_year
		)
		self.assertTrue(status["has_budget"])
		self.assertEqual(flt(status["budget"]), BUDGET_AMOUNT)

	def _material_request(self, qty, rate):
		doc = frappe.get_doc({
			"doctype": "Material Request",
			"material_request_type": "Purchase",
			"company": self.company,
			"transaction_date": nowdate(),
			"schedule_date": nowdate(),
			"ags_campus": self.campus,
			"ags_purpose": "Grade 9 Laboratory",
			"ags_budget_account": self.account,
			"items": [{
				"item_code": self.item,
				"qty": qty,
				"rate": rate,
				"schedule_date": nowdate(),
				"warehouse": frappe.db.get_value(
					"Warehouse", {"company": self.company, "is_group": 0}, "name"
				),
				"cost_center": self.cost_center,
			}],
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		return doc

	def test_estimated_total_and_available_budget_are_stamped(self):
		# Compared against what the engine currently reports rather than the
		# original budget: sibling tests in this class leave real commitments
		# behind, and hard-coding the full amount would only test their ordering.
		expected = commitments.available_budget(
			self.company, self.account, self.cost_center, self.fiscal_year
		)["available"]

		request = self._material_request(qty=100, rate=50)
		self.assertEqual(flt(request.ags_estimated_total), 5000.0)
		self.assertEqual(flt(request.ags_budget_available), flt(expected))

	def test_approved_request_consumes_budget_before_any_invoice_exists(self):
		"""The whole point of SKILL sec. 7.1."""
		before = commitments.available_budget(
			self.company, self.account, self.cost_center, self.fiscal_year
		)["available"]

		request = self._material_request(qty=100, rate=300)  # 30,000
		request.submit()

		commitment = frappe.db.get_value(
			"AGS Budget Commitment",
			{"source_doctype": "Material Request", "source_name": request.name},
			["amount", "status"],
			as_dict=True,
		)
		self.assertIsNotNone(commitment, "submitting a request must reserve budget")
		self.assertEqual(flt(commitment.amount), 30000.0)
		self.assertEqual(commitment.status, "Open")

		after = commitments.available_budget(
			self.company, self.account, self.cost_center, self.fiscal_year
		)["available"]
		self.assertEqual(flt(before - after), 30000.0)

	def test_cancelling_a_request_releases_the_reservation(self):
		request = self._material_request(qty=10, rate=1000)  # 10,000
		request.submit()
		committed = commitments.available_budget(
			self.company, self.account, self.cost_center, self.fiscal_year
		)["committed"]
		self.assertGreaterEqual(flt(committed), 10000.0)

		request.cancel()
		status = frappe.db.get_value(
			"AGS Budget Commitment",
			{"source_doctype": "Material Request", "source_name": request.name},
			"status",
		)
		self.assertEqual(status, "Released")

	def test_reconcile_releases_commitments_whose_source_was_cancelled(self):
		request = self._material_request(qty=5, rate=200)
		request.submit()
		name = frappe.db.get_value(
			"AGS Budget Commitment",
			{"source_doctype": "Material Request", "source_name": request.name},
			"name",
		)
		# Simulate the crash window: the document is cancelled but the release
		# never ran, so budget stays wrongly reserved until reconciliation.
		request.flags.ignore_permissions = True
		request.cancel()
		frappe.db.set_value("AGS Budget Commitment", name, "status", "Open")

		commitments.reconcile_commitments()
		self.assertEqual(
			frappe.db.get_value("AGS Budget Commitment", name, "status"), "Released"
		)


class TestApprovalMatrix(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		demo.build()
		cls.item = stock_item()

	def test_levels_are_cumulative_across_thresholds(self):
		"""SKILL sec. 8.3: 30,000 needs head + finance + principal, not principal alone."""
		matrix = "Purchase Request Thresholds"

		small = engine.required_levels(matrix, 3000)
		self.assertEqual([lvl.approver_role for lvl in small], ["AGS Department Head"])

		mid = engine.required_levels(matrix, 12000)
		self.assertEqual(
			[lvl.approver_role for lvl in mid],
			["AGS Department Head", "AGS Finance Manager"],
		)

		large = engine.required_levels(matrix, 30000)
		self.assertEqual(
			[lvl.approver_role for lvl in large],
			["AGS Department Head", "AGS Finance Manager", "AGS Principal"],
		)

		huge = engine.required_levels(matrix, 150000)
		self.assertEqual(len(huge), 4)
		self.assertEqual(huge[-1].approver_role, "AGS Group Executive")

	def test_discount_tiers_match_the_specified_bands(self):
		"""SKILL sec. 17.7: 0-5 officer, 5-15 manager, 15-25 director, >25 CFO."""
		matrix = "Discount Approval Tiers"

		self.assertEqual(
			[lvl.approver_role for lvl in engine.required_levels(matrix, 3)],
			["AGS Accountant"],
		)
		# Above 5% the accountant band no longer applies (it is capped at 5).
		roles_at_ten = [lvl.approver_role for lvl in engine.required_levels(matrix, 10)]
		self.assertNotIn("AGS Accountant", roles_at_ten)
		self.assertIn("AGS Finance Manager", roles_at_ten)

		roles_at_thirty = [lvl.approver_role for lvl in engine.required_levels(matrix, 30)]
		self.assertIn("AGS Group Executive", roles_at_thirty)

	def test_purchase_order_is_blocked_by_an_unapproved_request(self):
		company = demo.COMPANY
		campus = "Jeddah"
		cost_center = frappe.db.get_value("AGS Campus", campus, "cost_center")

		request = frappe.get_doc({
			"doctype": "Material Request",
			"material_request_type": "Purchase",
			"company": company,
			"transaction_date": nowdate(),
			"schedule_date": nowdate(),
			"ags_campus": campus,
			"ags_purpose": "Blocked order test",
			"items": [{
				"item_code": self.item,
				"qty": 10,
				"rate": 900,
				"schedule_date": nowdate(),
				"warehouse": frappe.db.get_value(
					"Warehouse", {"company": company, "is_group": 0}, "name"
				),
				"cost_center": cost_center,
			}],
		})
		request.flags.ignore_permissions = True
		request.insert()
		request.submit()

		# Submitting raised an approval request, so the guard must refuse.
		self.assertTrue(
			frappe.db.exists("AGS Approval Request", {
				"reference_doctype": "Material Request",
				"reference_name": request.name,
				"status": "Pending",
			}),
			"submitting a purchase request should open an approval request",
		)

		with self.assertRaises(frappe.ValidationError):
			engine.assert_approved("Material Request", request.name)
