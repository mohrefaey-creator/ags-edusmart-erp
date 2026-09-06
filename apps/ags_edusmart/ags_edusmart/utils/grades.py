"""Grade / year-level parsing.

Programs in Frappe Education are free text ("Grade 5", "KG2", "Year 11"), so any
ordering question - is this division's range valid, which sibling is older, does
this discount tier apply - has to go through a parser rather than a sort on the
name.

The anchor at the start of the string is deliberate. A loose search for the first
digit reads "KG2" as grade 2, filing a kindergarten child with seven-year-olds,
and reads "Room 42" as a year group. Every real shape here leads with its year.
"""

from __future__ import annotations

import re

import frappe

# Anchored: optional "Grade"/"Year" word, then the number, then a non-digit.
_GRADE_RE = re.compile(r"^\s*(?:grades?|years?)?\s*(\d{1,2})(?!\d)", re.IGNORECASE)

# Kindergarten levels sort below grade 1 but are real levels, not "unknown".
_KG_RE = re.compile(r"^\s*(?:kg|kindergarten|pre-?k)\s*(\d)?", re.IGNORECASE)


def parse_grade_level(program: str | None) -> int | None:
	"""Return the year level for a Program name, or None when unparseable.

	Grade 0 is a real level (KG1 maps to -1, KG2 to 0), so callers must test
	``is None`` rather than falsiness.
	"""
	if not program:
		return None

	name = str(program).strip()

	kg = _KG_RE.match(name)
	if kg:
		# KG1 -> -1, KG2 -> 0, bare "Kindergarten" -> -1.
		year = int(kg.group(1)) if kg.group(1) else 1
		return year - 2

	match = _GRADE_RE.match(name)
	if match:
		return int(match.group(1))
	return None


def sort_programs(programs: list[str]) -> list[str]:
	"""Order programs by year level, keeping unparseable names last and stable."""
	def key(name: str) -> tuple[int, int | float, str]:
		level = parse_grade_level(name)
		return (1, 0, name) if level is None else (0, level, name)

	return sorted(programs, key=key)


def program_of_student(student: str, academic_year: str | None = None) -> str | None:
	"""Current Program for a student, from the latest submitted enrollment."""
	filters = {"student": student, "docstatus": 1}
	if academic_year:
		filters["academic_year"] = academic_year
	rows = frappe.get_all(
		"Program Enrollment",
		filters=filters,
		fields=["program"],
		order_by="enrollment_date desc, creation desc",
		limit=1,
	)
	return rows[0].program if rows else None
