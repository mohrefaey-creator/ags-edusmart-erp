"""KPI refresh and read (SKILL sec. 26/27).

Dashboards read snapshots, never live aggregates. That is the whole point: at
07:00 on a school day a few hundred people open a dashboard within the same
fifteen minutes, and each live KPI would be a full-table scan over GL Entry. One
background pass computes each scope once; every reader then does a single
indexed row lookup.

Each snapshot is keyed by ``scope_key`` (code + every dimension) and upserted, so
the table stays one row per scope instead of growing without bound.
"""

from __future__ import annotations

import hashlib

import frappe
from frappe.utils import add_to_date, flt, now, nowdate

from ags_edusmart.ags_dashboards import kpi_library

SCOPE_FIELDS = (
	"company", "campus", "school_division", "program", "department", "academic_year",
)


def scope_key(code: str, scope: dict) -> str:
	parts = [code] + [str(scope.get(f) or "") for f in SCOPE_FIELDS]
	raw = "|".join(parts)
	# Hashed because the raw key exceeds a Data column once six dimensions are set.
	return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def compute(definition, scope: dict) -> float | None:
	if definition.source == "SQL":
		return _compute_sql(definition, scope)

	fn = kpi_library.resolve(definition.method_path or "")
	if not fn:
		frappe.log_error(
			title="AGS KPI: unknown method",
			message=f"{definition.code} -> {definition.method_path}",
		)
		return None
	return flt(fn(scope))


def _compute_sql(definition, scope: dict) -> float | None:
	query = (definition.sql_query or "").strip()
	if not query:
		return None
	# Read-only by construction: anything but a single SELECT is refused.
	lowered = query.lower().lstrip("(")
	if not lowered.startswith("select"):
		frappe.log_error(
			title="AGS KPI: non-SELECT query refused",
			message=f"{definition.code}",
		)
		return None
	if ";" in query.rstrip().rstrip(";"):
		frappe.log_error(
			title="AGS KPI: multi-statement query refused",
			message=f"{definition.code}",
		)
		return None

	params = {f: scope.get(f) for f in SCOPE_FIELDS}
	params["from_date"] = scope.get("from_date")
	params["to_date"] = scope.get("to_date") or nowdate()
	rows = frappe.db.sql(query, params)
	return flt(rows[0][0]) if rows and rows[0] and rows[0][0] is not None else 0.0


def scopes_for(definition) -> list[dict]:
	"""Cartesian product of the dimensions this KPI is flagged to drill into.

	Bounded on purpose: company x campus x academic year. Finer drilldowns are
	computed on demand rather than pre-materialised for every grade in the group.
	"""
	companies = frappe.get_all("Company", pluck="name") or [None]
	out: list[dict] = []

	for company in companies:
		campuses = [None]
		if definition.drilldown_campus:
			campuses += frappe.get_all(
				"AGS Campus", filters={"company": company, "is_active": 1}, pluck="name"
			)

		years = [None]
		if definition.drilldown_academic_year:
			current = frappe.db.get_single_value("AGS Settings", "current_academic_year")
			if current:
				years = [None, current]

		for campus in campuses:
			for year in years:
				out.append({
					"company": company,
					"campus": campus,
					"academic_year": year,
				})
	return out


def refresh_kpi(code: str, force: bool = False) -> int:
	definition = frappe.get_cached_doc("AGS KPI Definition", code)
	if not definition.is_active:
		return 0

	written = 0
	for scope in scopes_for(definition):
		key = scope_key(code, scope)
		existing = frappe.db.get_value(
			"AGS KPI Snapshot", {"scope_key": key}, ["name", "computed_on"], as_dict=True
		)
		if existing and not force:
			interval = int(definition.refresh_interval_minutes or 60)
			if existing.computed_on and existing.computed_on > add_to_date(
				now(), minutes=-interval
			):
				continue

		try:
			value = compute(definition, scope)
		except Exception:
			frappe.log_error(
				title="AGS KPI: computation failed",
				message=f"{code} {scope}\n{frappe.get_traceback()}",
			)
			continue
		if value is None:
			continue

		payload = {
			"kpi": code,
			"code": code,
			"value": value,
			"computed_on": now(),
			"scope_key": key,
			**{f: scope.get(f) for f in SCOPE_FIELDS},
		}
		if existing:
			frappe.db.set_value(
				"AGS KPI Snapshot", existing.name, payload, update_modified=False
			)
		else:
			doc = frappe.get_doc({"doctype": "AGS KPI Snapshot", **payload})
			doc.flags.ignore_permissions = True
			try:
				doc.insert()
			except frappe.DuplicateEntryError:
				# Another worker wrote this scope first; its value is as fresh.
				continue
		written += 1

	return written


def refresh_due_kpis(limit: int = 40) -> dict:
	codes = frappe.get_all(
		"AGS KPI Definition", filters={"is_active": 1}, pluck="name", limit=limit
	)
	total = 0
	for code in codes:
		try:
			total += refresh_kpi(code)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(
				title="AGS KPI: refresh failed", message=f"{code}\n{frappe.get_traceback()}"
			)
	return {"snapshots": total, "kpis": len(codes)}


@frappe.whitelist()
def read(codes=None, company=None, campus=None, academic_year=None) -> list[dict]:
	"""Dashboard read path: one indexed lookup per KPI, permission filtered."""
	from ags_edusmart.ags_core.permissions import get_user_scope

	if isinstance(codes, str):
		codes = [c.strip() for c in codes.split(",") if c.strip()]

	user_scope = get_user_scope()
	if campus and not user_scope["unrestricted"] and campus not in user_scope["campuses"]:
		frappe.throw(frappe._("Not permitted for this campus."), frappe.PermissionError)
	if not campus and not user_scope["unrestricted"]:
		# A campus-bound user never sees the group-wide roll-up.
		if not user_scope["campuses"]:
			return []
		campus = user_scope["campuses"][0]

	definitions = frappe.get_all(
		"AGS KPI Definition",
		filters={"is_active": 1, **({"code": ("in", codes)} if codes else {})},
		fields=["name", "code", "kpi_name", "category", "unit", "direction",
		        "target_value", "warning_threshold"],
	)

	roles = set(frappe.get_roles())
	out = []
	for definition in definitions:
		if not _visible(definition.name, roles):
			continue
		key = scope_key(
			definition.code,
			{"company": company, "campus": campus, "academic_year": academic_year},
		)
		snapshot = frappe.db.get_value(
			"AGS KPI Snapshot", {"scope_key": key}, ["value", "computed_on"], as_dict=True
		)
		out.append({
			**definition,
			"value": flt(snapshot.value) if snapshot else None,
			"computed_on": snapshot.computed_on if snapshot else None,
			"stale": snapshot is None,
		})
	return out


def _visible(kpi_name: str, roles: set) -> bool:
	allowed = frappe.get_all(
		"AGS KPI Role",
		filters={"parent": kpi_name, "parenttype": "AGS KPI Definition"},
		pluck="role",
	)
	if not allowed:
		return True
	return bool(set(allowed) & roles)
