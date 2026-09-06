"""Shared query helpers for the insight modules.

Two jobs: keep every analyzer's scope handling identical, and degrade honestly
when an optional field is absent on a site (an accounting dimension that was
never created, for instance) rather than raising an opaque SQL error.
"""

from __future__ import annotations

import frappe
from frappe.utils import add_months, getdate


def has_field(doctype: str, fieldname: str) -> bool:
	try:
		return bool(frappe.get_meta(doctype).has_field(fieldname))
	except Exception:
		return False


def campus_clause(scope, alias: str, doctype: str) -> tuple[str, dict]:
	"""Campus restriction for a doctype, or a no-op if it carries no campus.

	A doctype with no campus field cannot be campus-restricted. Rather than
	silently returning group-wide numbers to a campus-bound user, callers pair
	this with ``campus_note()`` so the answer says the restriction could not be
	applied.
	"""
	campuses = scope.campus_filter
	if campuses is None:
		return "1 = 1", {}
	if not campuses:
		return "1 = 0", {}

	field = "campus" if has_field(doctype, "campus") else (
		"ags_campus" if has_field(doctype, "ags_campus") else None
	)
	if not field:
		return "1 = 1", {}
	return f"{alias}.{field} in %(scope_campuses)s", {"scope_campuses": campuses}


def campus_note(scope, doctype: str) -> list[str]:
	"""A note to attach when campus scoping could not be applied."""
	if scope.campus_filter is None:
		return []
	if has_field(doctype, "campus") or has_field(doctype, "ags_campus"):
		return []
	return [
		frappe._("{0} carries no campus field, so this figure is group-wide "
		         "rather than restricted to your campuses.").format(frappe._(doctype))
	]


def prior_period(from_date: str, to_date: str) -> tuple[str, str]:
	"""The equivalent window one year earlier.

	Year-on-year, not the immediately preceding window: a school year is
	seasonal, and comparing March against February would report the academic
	calendar as if it were a business trend.
	"""
	start = getdate(from_date)
	end = getdate(to_date)
	return str(add_months(start, -12)), str(add_months(end, -12))


def account_totals(scope, root_type: str, from_date: str, to_date: str) -> dict[str, float]:
	"""Signed totals per account name for one root type over a window."""
	# Income is credit-positive, expense is debit-positive; normalise both to a
	# positive magnitude so drivers read naturally.
	sign = "credit - debit" if root_type == "Income" else "debit - credit"

	conditions = ["gle.is_cancelled = 0", "a.root_type = %(root_type)s",
	              "gle.posting_date between %(from_date)s and %(to_date)s"]
	params = {
		"root_type": root_type,
		"from_date": from_date,
		"to_date": to_date,
	}
	if scope.company:
		conditions.append("gle.company = %(company)s")
		params["company"] = scope.company

	clause, campus_params = campus_clause(scope, "gle", "GL Entry")
	conditions.append(clause)
	params.update(campus_params)

	rows = frappe.db.sql(
		f"""
		select a.account_name as label, sum({sign}) as amount
		from `tabGL Entry` gle
		inner join `tabAccount` a on a.name = gle.account
		where {" and ".join(conditions)}
		group by a.account_name
		having sum({sign}) != 0
		""",
		params,
		as_dict=True,
	)
	return {row.label: float(row.amount or 0) for row in rows}


def root_total(scope, root_type: str, from_date: str, to_date: str) -> float:
	return float(sum(account_totals(scope, root_type, from_date, to_date).values()))
