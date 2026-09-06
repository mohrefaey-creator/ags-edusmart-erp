"""The discount engine (SKILL sec. 17.6 / 17.7).

Three properties the school actually cares about, in order:

1. Eligibility is per fee component. "Second child: 10% tuition only" means the
   books and transport lines are untouched, so a discount is never computed on
   the plan total - it is computed on the eligible base and then distributed
   back across those components.
2. Order matters once discounts stack. Rules run by ``priority``, each seeing the
   net left by the ones before it, so two stacked 10% rules take 19%, not 20%.
3. A discount above its threshold is *proposed*, never silently applied. Those
   rows land as ``Pending Approval`` and are excluded from the payable total
   until an AGS Discount Application approves them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import frappe
from frappe.utils import flt, getdate, nowdate


@dataclass
class ComponentBase:
	"""Mutable working copy of one fee component during the discount pass."""

	row_name: str
	fees_category: str
	gross: float
	discountable: bool
	discount: float = 0.0

	@property
	def net(self) -> float:
		return flt(self.gross - self.discount, 2)


@dataclass
class DiscountResult:
	rule: str | None
	scholarship: str | None
	discount_type: str
	calculation: str
	value: float
	amount: float
	status: str = "Applied"
	notes: str = ""
	per_component: dict[str, float] = field(default_factory=dict)


def sibling_index(payer_account: str, student: str) -> int:
	"""1 = eldest enrolled child on this payer account.

	Ordered by date of birth so the tier does not move when a younger sibling is
	registered first. Students with no DOB sort last but keep a stable order.
	"""
	rows = frappe.get_all(
		"AGS Payer Student",
		filters={"parent": payer_account, "parenttype": "AGS Payer Account", "is_active": 1},
		fields=["student"],
		order_by="idx asc",
	)
	if not rows:
		return 1

	students = [r.student for r in rows]
	dobs = frappe.get_all(
		"Student",
		filters={"name": ("in", students)},
		fields=["name", "date_of_birth"],
	)
	dob_map = {r.name: r.date_of_birth for r in dobs}

	def sort_key(name: str):
		dob = dob_map.get(name)
		return (1, name) if dob is None else (0, getdate(dob).toordinal(), name)

	ordered = sorted(students, key=sort_key)
	try:
		return ordered.index(student) + 1
	except ValueError:
		return len(ordered) + 1


def _rule_matches(rule: dict, ctx: dict) -> bool:
	"""A blank condition on the rule means 'any'."""
	for rule_field, ctx_key in (
		("company", "company"),
		("campus", "campus"),
		("academic_year", "academic_year"),
		("program", "program"),
		("student_category", "student_category"),
		("division_type", "division_type"),
	):
		expected = rule.get(rule_field)
		if expected and expected != ctx.get(ctx_key):
			return False

	today = getdate(nowdate())
	if rule.get("valid_from") and getdate(rule["valid_from"]) > today:
		return False
	if rule.get("valid_to") and getdate(rule["valid_to"]) < today:
		return False

	if rule.get("discount_type") == "Sibling Discount":
		index = ctx.get("sibling_index") or 1
		low = rule.get("sibling_index_from") or 1
		high = rule.get("sibling_index_to") or 0
		if index < low:
			return False
		if high and index > high:
			return False

	return True


def _eligible_rows(rule: dict, components: list[ComponentBase]) -> list[ComponentBase]:
	if rule.get("apply_to_all_components"):
		return [c for c in components if c.discountable]

	categories = set(
		frappe.get_all(
			"AGS Discount Rule Component",
			filters={"parent": rule["name"], "parenttype": "AGS Discount Rule"},
			pluck="fees_category",
		)
	)
	return [c for c in components if c.discountable and c.fees_category in categories]


def _apply(rule: dict, components: list[ComponentBase]) -> DiscountResult | None:
	rows = _eligible_rows(rule, components)
	base = flt(sum(c.net for c in rows), 2)
	if base <= 0:
		return None

	if rule["calculation"] == "Percent":
		amount = flt(base * flt(rule["value"]) / 100.0, 2)
	else:
		amount = min(flt(rule["value"]), base)

	cap = flt(rule.get("max_amount"))
	if cap:
		amount = min(amount, cap)
	amount = flt(amount, 2)
	if amount <= 0:
		return None

	result = DiscountResult(
		rule=rule["name"],
		scholarship=None,
		discount_type=rule["discount_type"],
		calculation=rule["calculation"],
		value=flt(rule["value"]),
		amount=amount,
		status="Pending Approval" if rule.get("requires_approval") else "Applied",
	)

	# Distribute pro-rata across the eligible rows. The last row absorbs the
	# rounding remainder so the component discounts always sum to `amount`.
	if result.status == "Applied":
		remaining = amount
		for idx, row in enumerate(rows):
			if idx == len(rows) - 1:
				share = remaining
			else:
				share = flt(amount * (row.net / base), 2)
				remaining = flt(remaining - share, 2)
			row.discount = flt(row.discount + share, 2)
			result.per_component[row.row_name] = flt(
				result.per_component.get(row.row_name, 0) + share, 2
			)
	else:
		result.notes = "Requires approval before it reduces the payable amount."

	return result


def compute(components: list[ComponentBase], ctx: dict) -> list[DiscountResult]:
	"""Run every matching rule against the working components, in priority order."""
	rules = frappe.get_all(
		"AGS Discount Rule",
		filters={"is_active": 1},
		fields=[
			"name", "discount_type", "calculation", "value", "max_amount", "priority",
			"stackable", "requires_approval", "apply_to_all_components", "company",
			"campus", "academic_year", "program", "student_category", "division_type",
			"sibling_index_from", "sibling_index_to", "valid_from", "valid_to",
		],
		order_by="priority asc, name asc",
	)

	matching = [r for r in rules if _rule_matches(r, ctx)]
	if not matching:
		return []

	# A non-stackable rule wins alone: the highest-priority one suppresses the rest.
	exclusive = next((r for r in matching if not r.get("stackable")), None)
	if exclusive:
		matching = [exclusive]

	results: list[DiscountResult] = []
	for rule in matching:
		applied = _apply(rule, components)
		if applied:
			results.append(applied)
	return results


def apply_scholarship(scholarship_name: str, components: list[ComponentBase]) -> DiscountResult | None:
	"""Scholarships are applied explicitly, never auto-matched."""
	sch = frappe.get_cached_doc("AGS Scholarship", scholarship_name)
	if not sch.is_active:
		frappe.throw(frappe._("Scholarship {0} is not active.").format(scholarship_name))

	if not sch.apply_to_all_components:
		categories = {row.fees_category for row in sch.components}
		rows = [c for c in components if c.discountable and c.fees_category in categories]
	else:
		rows = [c for c in components if c.discountable]

	base = flt(sum(c.net for c in rows), 2)
	if base <= 0:
		return None

	if sch.calculation == "Percent":
		amount = flt(base * flt(sch.value) / 100.0, 2)
	else:
		amount = min(flt(sch.value), base)
	if flt(sch.max_amount_per_student):
		amount = min(amount, flt(sch.max_amount_per_student))
	amount = flt(amount, 2)
	if amount <= 0:
		return None

	result = DiscountResult(
		rule=None,
		scholarship=sch.name,
		discount_type="Scholarship",
		calculation=sch.calculation,
		value=flt(sch.value),
		amount=amount,
	)

	remaining = amount
	for idx, row in enumerate(rows):
		share = remaining if idx == len(rows) - 1 else flt(amount * (row.net / base), 2)
		if idx != len(rows) - 1:
			remaining = flt(remaining - share, 2)
		row.discount = flt(row.discount + share, 2)
		result.per_component[row.row_name] = share

	return result
