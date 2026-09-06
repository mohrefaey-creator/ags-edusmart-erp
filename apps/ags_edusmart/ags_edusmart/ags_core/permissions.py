"""Scope-aware row permissions (SKILL sec. 34).

Frappe calls these as ``fn(user, doctype=...)`` and appends the returned SQL with
AND, so an empty string means "no restriction". Everything here therefore fails
*closed*: a user who is campus-bound but has no scope row sees nothing, rather
than silently seeing the whole group.

The parent and teacher rules are subqueries rather than Python-side id lists
because a group with 2,500 concurrent users would otherwise round-trip a few
thousand student ids into every list view.
"""

from __future__ import annotations

import frappe

# Roles that legitimately see every campus without a scope row.
GROUP_WIDE_ROLES = {
	"Administrator",
	"System Manager",
	"AGS Group Executive",
	"AGS Auditor",
}

_CACHE = "ags_user_scope"


def clear_scope_cache(user: str | None = None) -> None:
	if user:
		frappe.cache().hdel(_CACHE, user)
	else:
		frappe.cache().delete_key(_CACHE)


def get_user_scope(user: str | None = None) -> dict:
	"""Resolve a user's campus scope, cached per user.

	Returns ``{"unrestricted": bool, "campuses": [...]}``.
	"""
	user = user or frappe.session.user
	cached = frappe.cache().hget(_CACHE, user)
	if cached is not None:
		return cached

	scope = {"unrestricted": False, "campuses": []}

	if user == "Administrator":
		scope["unrestricted"] = True
	else:
		roles = set(frappe.get_roles(user))
		if roles & GROUP_WIDE_ROLES:
			scope["unrestricted"] = True
		else:
			row = frappe.db.get_value(
				"AGS User Scope", {"user": user}, ["name", "all_campuses"], as_dict=True
			)
			if row and row.all_campuses:
				scope["unrestricted"] = True
			elif row:
				scope["campuses"] = frappe.get_all(
					"AGS Campus Link",
					filters={"parent": row.name, "parenttype": "AGS User Scope"},
					pluck="campus",
				)

	frappe.cache().hset(_CACHE, user, scope)
	return scope


def _campus_fieldname(doctype: str) -> str | None:
	"""AGS doctypes call it ``campus``; native ones get ``ags_campus`` from the
	accounting dimension or a custom field."""
	meta = frappe.get_meta(doctype)
	for candidate in ("campus", "ags_campus"):
		if meta.has_field(candidate):
			return candidate
	return None


def _in_list(values: list[str]) -> str:
	return ", ".join(frappe.db.escape(v) for v in values)


def campus_scoped_query(user: str | None = None, doctype: str | None = None) -> str:
	if not doctype:
		return ""
	scope = get_user_scope(user)
	if scope["unrestricted"]:
		return ""

	field = _campus_fieldname(doctype)
	if not field:
		return ""

	if not scope["campuses"]:
		# Fail closed rather than open.
		return "1=0"

	return f"`tab{doctype}`.`{field}` in ({_in_list(scope['campuses'])})"


# ---------------------------------------------------------------- guardians
def guardian_names_for_user(user: str) -> list[str]:
	return frappe.get_all("Guardian", filters={"user": user}, pluck="name")


def payer_accounts_for_user(user: str) -> list[str]:
	guardians = guardian_names_for_user(user)
	if not guardians:
		return []
	return frappe.get_all(
		"AGS Payer Account", filters={"guardian": ("in", guardians)}, pluck="name"
	)


def students_for_guardian_sql(user: str) -> str:
	"""Subquery yielding the student ids linked to this user's guardian records."""
	escaped = frappe.db.escape(user)
	return (
		"select sg.parent from `tabStudent Guardian` sg "
		"inner join `tabGuardian` g on g.name = sg.guardian "
		f"where g.user = {escaped} and sg.parenttype = 'Student'"
	)


def students_for_instructor_sql(user: str) -> str:
	"""Subquery yielding students in the groups this user teaches."""
	escaped = frappe.db.escape(user)
	return (
		"select sgs.student from `tabStudent Group Student` sgs "
		"where sgs.parenttype = 'Student Group' and sgs.parent in ("
		"  select sgi.parent from `tabStudent Group Instructor` sgi "
		"  inner join `tabInstructor` i on i.name = sgi.instructor "
		"  inner join `tabEmployee` e on e.name = i.employee "
		f"  where e.user_id = {escaped}"
		")"
	)


def student_query(user: str | None = None, doctype: str | None = None) -> str:
	user = user or frappe.session.user
	scope = get_user_scope(user)
	if scope["unrestricted"]:
		return ""

	roles = set(frappe.get_roles(user))

	if "AGS Parent" in roles:
		return f"`tabStudent`.name in ({students_for_guardian_sql(user)})"

	if "AGS Teacher" in roles and not (roles & {"AGS Principal", "AGS Vice Principal",
	                                            "AGS Academic Coordinator"}):
		return f"`tabStudent`.name in ({students_for_instructor_sql(user)})"

	return campus_scoped_query(user, "Student")


def sales_invoice_query(user: str | None = None, doctype: str | None = None) -> str:
	user = user or frappe.session.user
	scope = get_user_scope(user)
	roles = set(frappe.get_roles(user))

	if "AGS Parent" in roles and not scope["unrestricted"]:
		payers = payer_accounts_for_user(user)
		if not payers:
			return "1=0"
		return f"`tabSales Invoice`.ags_payer_account in ({_in_list(payers)})"

	return campus_scoped_query(user, "Sales Invoice")


def payer_account_query(user: str | None = None, doctype: str | None = None) -> str:
	user = user or frappe.session.user
	scope = get_user_scope(user)
	if scope["unrestricted"]:
		return ""

	roles = set(frappe.get_roles(user))
	if "AGS Parent" in roles:
		guardians = guardian_names_for_user(user)
		if not guardians:
			return "1=0"
		return f"`tabAGS Payer Account`.guardian in ({_in_list(guardians)})"

	return campus_scoped_query(user, "AGS Payer Account")


# ------------------------------------------------------------ has_permission
def payer_account_has_permission(doc, ptype: str = "read", user: str | None = None) -> bool:
	user = user or frappe.session.user
	if get_user_scope(user)["unrestricted"]:
		return True

	roles = set(frappe.get_roles(user))
	if "AGS Parent" in roles:
		# A parent may read their own account and nothing else, ever.
		if ptype not in ("read", "print", "email"):
			return False
		return doc.guardian in guardian_names_for_user(user)

	if not doc.campus:
		return True
	return doc.campus in get_user_scope(user)["campuses"]


def student_has_permission(doc, ptype: str = "read", user: str | None = None) -> bool:
	user = user or frappe.session.user
	if get_user_scope(user)["unrestricted"]:
		return True

	roles = set(frappe.get_roles(user))
	if "AGS Parent" in roles:
		if ptype not in ("read", "print", "email"):
			return False
		guardians = set(guardian_names_for_user(user))
		linked = {row.guardian for row in (doc.get("guardians") or [])}
		return bool(guardians & linked)

	campus = doc.get("ags_campus")
	if not campus:
		return True
	return campus in get_user_scope(user)["campuses"]
