"""Collections analyses (SKILL sec. 28.1, 20).

"Which parents are >90 days overdue?" is a question with a person's name in the
answer, so it is restricted to the roles that legitimately chase debt.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from ags_edusmart.ags_ai.insights._base import campus_clause, campus_note
from ags_edusmart.ags_ai.registry import Finding, analyzer

COLLECTION_ROLES = (
	"AGS Finance Manager", "AGS Accountant", "AGS Collections Officer",
	"AGS Group Executive", "AGS Principal",
)


@analyzer(
	code="long_overdue_payers",
	question="Which parents are more than 90 days overdue?",
	category="Collections",
	keywords=("parent", "payer", "90", "days", "overdue", "chase", "who", "long"),
	roles=COLLECTION_ROLES,
)
def long_overdue_payers(scope, days: int = 90, limit: int = 25, **_params) -> Finding:
	"""Payers whose oldest unpaid invoice passed its due date over `days` ago."""
	clause, params = campus_clause(scope, "si", "Sales Invoice")
	params.update({"company": scope.company, "days": int(days), "limit": int(limit)})

	rows = frappe.db.sql(
		f"""
		select
			si.ags_payer_account as payer,
			pa.payer_name,
			pa.mobile,
			sum(si.outstanding_amount) as outstanding,
			min(si.due_date) as oldest_due,
			datediff(curdate(), min(si.due_date)) as days_overdue,
			count(*) as invoices
		from `tabSales Invoice` si
		inner join `tabAGS Payer Account` pa on pa.name = si.ags_payer_account
		where si.docstatus = 1 and si.outstanding_amount > 0
		  and si.ags_fee_plan is not null
		  and si.company = %(company)s
		  and si.due_date < date_sub(curdate(), interval %(days)s day)
		  and {clause}
		group by si.ags_payer_account, pa.payer_name, pa.mobile
		order by outstanding desc
		limit %(limit)s
		""",
		params,
		as_dict=True,
	)

	finding = Finding(
		code="long_overdue_payers",
		title=_("Payers more than {0} days overdue").format(int(days)),
		unit="Currency",
		notes=campus_note(scope, "Sales Invoice"),
	)

	if not rows:
		finding.headline = 0.0
		finding.summary = _("No payer is more than {0} days overdue.").format(int(days))
		finding.insufficient_data = True
		return finding

	total = flt(sum(flt(r.outstanding) for r in rows), 2)
	finding.headline = total
	finding.rows = [
		{
			"payer": r.payer,
			"payer_name": r.payer_name,
			"mobile": r.mobile,
			"outstanding": flt(r.outstanding, 2),
			"days_overdue": int(r.days_overdue or 0),
			"oldest_due": str(r.oldest_due),
			"invoices": int(r.invoices),
		}
		for r in rows
	]
	finding.summary = _(
		"{0} payer(s) are more than {1} days overdue, owing {2} between them. "
		"The largest is {3} at {4}, {5} days past due."
	).format(
		len(rows), int(days), frappe.utils.fmt_money(total),
		rows[0].payer_name, frappe.utils.fmt_money(rows[0].outstanding),
		int(rows[0].days_overdue or 0),
	)
	return finding


@analyzer(
	code="collection_performance",
	question="How is collection performing by campus?",
	category="Collections",
	keywords=("collection", "performance", "rate", "percent", "campus", "how"),
	roles=COLLECTION_ROLES,
)
def collection_performance(scope, **_params) -> Finding:
	"""Collection percentage and ageing profile per campus."""
	clause, params = campus_clause(scope, "si", "Sales Invoice")
	params.update({"company": scope.company})

	rows = frappe.db.sql(
		f"""
		select
			coalesce(si.campus, '—') as campus,
			sum(si.grand_total) as billed,
			sum(si.grand_total - si.outstanding_amount) as collected,
			sum(si.outstanding_amount) as outstanding,
			sum(case when si.due_date < date_sub(curdate(), interval 90 day)
			         then si.outstanding_amount else 0 end) as over_90
		from `tabSales Invoice` si
		where si.docstatus = 1 and si.ags_fee_plan is not null
		  and si.company = %(company)s and {clause}
		group by coalesce(si.campus, '—')
		order by billed desc
		""",
		params,
		as_dict=True,
	)

	finding = Finding(
		code="collection_performance",
		title=_("Collection performance"),
		unit="Percent",
		notes=campus_note(scope, "Sales Invoice"),
	)

	rows = [r for r in rows if flt(r.billed)]
	if not rows:
		finding.summary = _("No fee invoices have been raised yet.")
		finding.insufficient_data = True
		return finding

	billed = sum(flt(r.billed) for r in rows)
	collected = sum(flt(r.collected) for r in rows)
	overall = flt(collected / billed * 100, 1) if billed else 0.0
	finding.headline = overall

	finding.rows = [
		{
			"campus": r.campus,
			"billed": flt(r.billed, 2),
			"collected": flt(r.collected, 2),
			"outstanding": flt(r.outstanding, 2),
			"over_90": flt(r.over_90, 2),
			"collection_percent": flt(flt(r.collected) / flt(r.billed) * 100, 1),
		}
		for r in rows
	]

	weakest = min(finding.rows, key=lambda r: r["collection_percent"])
	finding.summary = _(
		"Overall collection is {0}% of {1} billed. The weakest campus is {2} at "
		"{3}%, with {4} more than 90 days overdue."
	).format(
		overall, frappe.utils.fmt_money(billed), weakest["campus"],
		weakest["collection_percent"], frappe.utils.fmt_money(weakest["over_90"]),
	)
	return finding
