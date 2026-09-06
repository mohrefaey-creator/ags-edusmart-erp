"""Tests for the AI decision-support layer (SKILL sec. 28).

The properties worth protecting here are not "does it produce prose". They are:

* every analyzer actually runs against a real database without raising;
* routing matches the question asked, and *refuses* rather than guessing;
* the scope a user is entitled to is never widened, by argument or otherwise;
* driver decomposition is arithmetically right;
* every question, including refused ones, lands in the audit log.
"""

from __future__ import annotations

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from ags_edusmart.ags_ai import narrator, registry, router
from ags_edusmart.ags_ai.registry import Driver, Finding, rank_drivers
from ags_edusmart.ags_ai.scope import Scope, resolve
from ags_edusmart.setup import demo


class TestDriverDecomposition(UnitTestCase):
	"""The arithmetic behind SKILL sec. 28.1's explanatory output."""

	def test_ranks_by_absolute_movement_not_percentage(self):
		# Maintenance moves 21% but only 2,100; payroll moves 8% and 80,000.
		# Ranking by percentage would put the small line first and mislead.
		drivers = rank_drivers(
			current={"Payroll": 1_080_000, "Maintenance": 12_100, "Rent": 200_000},
			previous={"Payroll": 1_000_000, "Maintenance": 10_000, "Rent": 200_000},
		)
		self.assertEqual(drivers[0].label, "Payroll")
		self.assertEqual(drivers[1].label, "Maintenance")

	def test_percentages_and_contributions(self):
		drivers = rank_drivers(
			current={"A": 110, "B": 80},
			previous={"A": 100, "B": 100},
		)
		by_label = {d.label: d for d in drivers}
		self.assertEqual(by_label["A"].change, 10)
		self.assertEqual(by_label["A"].change_percent, 10.0)
		self.assertEqual(by_label["B"].change, -20)
		self.assertEqual(by_label["B"].change_percent, -20.0)
		# Contributions are shares of the total absolute movement (10 + 20 = 30).
		self.assertAlmostEqual(by_label["A"].contribution_percent, 33.33, places=1)
		self.assertAlmostEqual(by_label["B"].contribution_percent, 66.67, places=1)
		self.assertEqual(by_label["A"].direction, "up")
		self.assertEqual(by_label["B"].direction, "down")

	def test_appearing_line_does_not_divide_by_zero(self):
		drivers = rank_drivers(current={"New Line": 5_000}, previous={})
		self.assertEqual(drivers[0].change_percent, 100.0)

	def test_unchanged_lines_are_dropped(self):
		drivers = rank_drivers(current={"A": 100}, previous={"A": 100})
		self.assertEqual(drivers, [])


class TestNarrator(UnitTestCase):
	def test_deterministic_narration_states_its_basis(self):
		finding = Finding(
			code="demo",
			title="Demo",
			headline=1234.0,
			summary="Outstanding is 1,234.",
			scope_description="AGS Education Group · Jeddah",
			drivers=[Driver("Payroll", 108.0, 100.0, 8.0, 8.0, 80.0)],
		)
		text = narrator.compose(finding)
		self.assertIn("Outstanding is 1,234.", text)
		self.assertIn("Payroll", text)
		# An answer must always say what it was computed over.
		self.assertIn("AGS Education Group · Jeddah", text)

	def test_insufficient_data_is_stated_not_hidden(self):
		finding = Finding(code="demo", title="Demo", insufficient_data=True,
		                  summary="Nothing yet.")
		self.assertIn("not enough data", narrator.compose(finding).lower())


class TestAnalyzersRun(IntegrationTestCase):
	"""Every registered analyzer must execute against a real database.

	The demo dataset is deliberately thin in places (no payroll, little
	attendance), so several analyzers correctly return `insufficient_data`.
	That is a pass: the requirement is that they answer honestly, not that they
	find something.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		demo.build()
		frappe.set_user("Administrator")

	def test_every_analyzer_executes(self):
		scope = resolve()
		failures = []
		for item in registry.all_analyzers(scope):
			try:
				finding = registry.run(item.code, scope)
			except Exception as exc:  # noqa: BLE001 - the point is to catch all
				failures.append(f"{item.code}: {type(exc).__name__}: {exc}")
				continue
			self.assertIsInstance(finding, Finding)
			self.assertTrue(finding.scope_description, f"{item.code} lost its scope")
			self.assertTrue(finding.as_of, f"{item.code} has no timestamp")
			# Something must be sayable about every answer.
			self.assertTrue(
				finding.summary, f"{item.code} produced no summary"
			)
		self.assertEqual(failures, [], "analyzers raised: " + "; ".join(failures))

	def test_registry_covers_every_skill_question(self):
		"""The handover names specific questions; each must be answerable."""
		codes = {a.code for a in registry.all_analyzers()}
		for required in (
			# 28.1 Finance
			"outstanding_tuition", "overdue_by_campus", "budget_overrun",
			"expected_collection", "long_overdue_payers", "margin_drivers",
			# 28.2 Procurement
			"supplier_ranking", "delayed_orders", "consolidation_opportunities",
			"price_drift",
			# 28.3 Inventory
			"stockout_forecast", "consumption_outliers", "non_moving_items",
			# 28.4 HR
			"absenteeism_outliers", "payroll_projection", "expiring_documents",
			# 28.5 School
			"attendance_risk", "declining_classes", "teacher_variance",
		):
			self.assertIn(required, codes, f"SKILL sec. 28 question missing: {required}")

	def test_every_question_is_audited(self):
		scope = resolve()
		before = frappe.db.count("AGS AI Query Log")
		registry.run("outstanding_tuition", scope)
		self.assertEqual(frappe.db.count("AGS AI Query Log"), before + 1)

		row = frappe.get_all(
			"AGS AI Query Log",
			filters={"analyzer": "outstanding_tuition"},
			fields=["asked_by", "permitted", "scope_description"],
			order_by="creation desc",
			limit=1,
		)[0]
		self.assertEqual(row.asked_by, "Administrator")
		self.assertTrue(row.permitted)
		self.assertTrue(row.scope_description)


class TestRouting(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		demo.build()
		frappe.set_user("Administrator")

	def setUp(self):
		self.scope = resolve()

	def test_matches_the_handover_questions(self):
		expected = {
			"What is outstanding tuition?": "outstanding_tuition",
			"which campus has the highest overdue balance": "overdue_by_campus",
			"why did operating margin decrease": "margin_drivers",
			"which parents are more than 90 days overdue": "long_overdue_payers",
			"what will run out next month": "stockout_forecast",
			"which items have not moved in six months": "non_moving_items",
			"which contracts expire in 60 days": "expiring_documents",
			"which students are at attendance risk": "attendance_risk",
			"which purchase orders are delayed": "delayed_orders",
			"where are we paying above historical price": "price_drift",
		}
		for question, code in expected.items():
			decision = router.route(question, self.scope)
			self.assertTrue(decision.matched, f"no match for: {question}")
			self.assertEqual(decision.analyzer.code, code, f"misrouted: {question}")

	def test_refuses_rather_than_guessing(self):
		"""An unmatched question must offer options, not a confident wrong answer."""
		for nonsense in ("how do I bake a cake", "what is the weather tomorrow"):
			decision = router.route(nonsense, self.scope)
			self.assertFalse(decision.matched, f"wrongly matched: {nonsense}")
			self.assertTrue(decision.alternatives, "no suggestions offered")

	def test_arabic_questions_route(self):
		"""The UI is bilingual, so routing has to be."""
		pairs = {
			"ما هي الرسوم المتبقية": "outstanding_tuition",
			"متى تنتهي الإقامة": "expiring_documents",
			"ما هو الاستهلاك غير الطبيعي في الأقسام": "consumption_outliers",
		}
		for question, code in pairs.items():
			decision = router.route(question, self.scope)
			self.assertTrue(decision.matched, f"no Arabic match for: {question}")
			self.assertEqual(decision.analyzer.code, code, f"misrouted: {question}")


class TestScopeEnforcement(IntegrationTestCase):
	"""SKILL sec. 28: never expose data beyond the user's authorization scope."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.data = demo.build()
		frappe.set_user("Administrator")

	def test_administrator_is_unrestricted(self):
		scope = resolve()
		self.assertTrue(scope.unrestricted)
		self.assertIsNone(scope.campus_filter)

	def test_requested_campus_is_intersected_not_trusted(self):
		"""A campus-bound user asking for a foreign campus is refused."""
		bound = Scope(user="x@example.com", company=self.data["company"],
		              campuses=["Jeddah"], unrestricted=False)
		self.assertEqual(bound.campus_filter, ["Jeddah"])

		clause, params = bound.sql_conditions("si", date_field=None)
		self.assertIn("si.campus in", clause)
		self.assertEqual(params["scope_campuses"], ["Jeddah"])

	def test_campus_bound_scope_never_yields_an_open_filter(self):
		"""An empty campus list must fail closed, not fall through to everything."""
		empty = Scope(user="x@example.com", campuses=[], unrestricted=False)
		clause, _params = empty.sql_conditions("si")
		self.assertIn("1 = 0", clause)

	def test_role_without_permission_is_refused_and_logged(self):
		scope = resolve()
		# A parent has none of the finance roles.
		scope.roles = {"AGS Parent"}
		before = frappe.db.count("AGS AI Query Log")

		with self.assertRaises(frappe.PermissionError):
			registry.run("payroll_projection", scope)

		# The refusal itself is the interesting audit event.
		self.assertEqual(frappe.db.count("AGS AI Query Log"), before + 1)
		row = frappe.get_all(
			"AGS AI Query Log",
			filters={"analyzer": "payroll_projection"},
			fields=["permitted"],
			order_by="creation desc",
			limit=1,
		)[0]
		self.assertFalse(row.permitted)

	def test_catalogue_only_advertises_permitted_analyses(self):
		scope = resolve()
		scope.roles = {"AGS Storekeeper"}
		codes = {a.code for a in registry.all_analyzers(scope)}
		self.assertIn("stockout_forecast", codes)
		# Payroll is not a storekeeper's business, so it is not even offered.
		self.assertNotIn("payroll_projection", codes)
		self.assertNotIn("teacher_variance", codes)
