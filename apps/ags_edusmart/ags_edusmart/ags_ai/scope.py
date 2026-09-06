"""The scope every AI answer is computed under.

SKILL sec. 28 ends with a hard requirement: "AI should respect role permissions
and never expose data beyond the user's authorization scope."

The way that requirement gets broken is always the same - a language model is
handed database access and asked to be careful. It will not be. So in this layer
the model never touches data at all: analyzers run ordinary, permission-scoped
queries, and the scope is resolved here, once, from the same
``ags_core.permissions`` machinery that scopes the desk and the portal.

A ``Scope`` is also *carried into the answer*, so every finding states the basis
it was computed on. A principal asking "what is outstanding tuition?" and a CFO
asking the same question get different numbers, and both answers say so.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import frappe
from frappe import _
from frappe.utils import add_months, getdate, nowdate

from ags_edusmart.ags_core.permissions import get_user_scope


@dataclass
class Scope:
	"""Resolved, permission-checked query scope for one AI question."""

	user: str
	company: str | None = None
	campuses: list[str] = field(default_factory=list)
	unrestricted: bool = False
	academic_year: str | None = None
	from_date: str | None = None
	to_date: str | None = None
	roles: set[str] = field(default_factory=set)

	# ------------------------------------------------------------ predicates
	@property
	def campus_filter(self) -> list[str] | None:
		"""None means "no campus restriction". A list means restrict to it.

		An empty list is never returned: a campus-bound user with no granted
		campuses is refused outright in ``resolve()`` rather than silently
		receiving group-wide numbers.
		"""
		return None if self.unrestricted else self.campuses

	def describe(self) -> str:
		"""Human-readable basis, shown with every answer."""
		parts = []
		if self.company:
			parts.append(self.company)
		if self.unrestricted:
			parts.append(_("all campuses"))
		elif self.campuses:
			parts.append(", ".join(self.campuses))
		if self.academic_year:
			parts.append(self.academic_year)
		if self.from_date and self.to_date:
			parts.append(f"{self.from_date} → {self.to_date}")
		return " · ".join(parts)

	# ------------------------------------------------------------ SQL helper
	def sql_conditions(self, alias: str, *, campus_field: str = "campus",
	                   company_field: str = "company",
	                   date_field: str | None = None) -> tuple[str, dict]:
		"""Conditions and params that pin a query to this scope.

		Every analyzer builds its WHERE clause through here, so a new analyzer
		cannot accidentally omit the campus restriction - the omission would have
		to be deliberate and visible in review.
		"""
		conditions: list[str] = []
		params: dict = {}

		if self.company:
			conditions.append(f"{alias}.{company_field} = %(scope_company)s")
			params["scope_company"] = self.company

		campuses = self.campus_filter
		if campuses is not None:
			if not campuses:
				# Belt and braces: resolve() already refuses this case.
				conditions.append("1 = 0")
			else:
				conditions.append(f"{alias}.{campus_field} in %(scope_campuses)s")
				params["scope_campuses"] = campuses

		if date_field and self.from_date and self.to_date:
			conditions.append(
				f"{alias}.{date_field} between %(scope_from)s and %(scope_to)s"
			)
			params["scope_from"] = self.from_date
			params["scope_to"] = self.to_date

		return (" and ".join(conditions) if conditions else "1 = 1"), params


def resolve(company: str | None = None, campus: str | None = None,
            academic_year: str | None = None, from_date: str | None = None,
            to_date: str | None = None, user: str | None = None) -> Scope:
	"""Build the scope for the calling user, honouring but never widening it.

	A requested campus is *intersected* with what the user may see, never
	trusted. Asking for a campus outside your grant is refused rather than
	quietly downgraded, so a user cannot probe which campuses exist by watching
	the numbers change.
	"""
	user = user or frappe.session.user
	if user == "Guest":
		frappe.throw(_("Please sign in."), frappe.PermissionError)

	granted = get_user_scope(user)
	unrestricted = bool(granted["unrestricted"])
	campuses = list(granted["campuses"])

	if campus:
		if not unrestricted and campus not in campuses:
			frappe.throw(
				_("You do not have access to campus {0}.").format(campus),
				frappe.PermissionError,
			)
		campuses = [campus]
		unrestricted = False
	elif not unrestricted and not campuses:
		frappe.throw(
			_("No campus is granted to your account, so no data can be reported. "
			  "Ask an administrator to set up your AGS User Scope."),
			frappe.PermissionError,
		)

	settings = frappe.get_cached_doc("AGS Settings")
	company = company or settings.default_company or frappe.defaults.get_user_default("Company")
	academic_year = academic_year or settings.current_academic_year

	# Default window: the trailing twelve months. Long enough for a
	# year-on-year comparison, short enough that the queries stay indexed.
	to_date = to_date or nowdate()
	from_date = from_date or str(add_months(getdate(to_date), -12))

	return Scope(
		user=user,
		company=company,
		campuses=campuses,
		unrestricted=unrestricted,
		academic_year=academic_year,
		from_date=str(from_date),
		to_date=str(to_date),
		roles=set(frappe.get_roles(user)),
	)
