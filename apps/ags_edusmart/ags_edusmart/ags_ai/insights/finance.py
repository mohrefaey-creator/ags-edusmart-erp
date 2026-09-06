"""Finance analyses (SKILL sec. 28.1).

The questions the handover names, each answered from the ledger:

* What is outstanding tuition?
* Which campus has the highest overdue balance?
* Why did expenses exceed budget?
* What is expected cash collection next month?
* Why did operating margin decrease?
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_months, flt, getdate, nowdate

from ags_edusmart.ags_ai.insights._base import (
	account_totals,
	campus_clause,
	campus_note,
	prior_period,
	root_total,
)
from ags_edusmart.ags_ai.registry import Finding, analyzer, rank_drivers

FINANCE_ROLES = (
	"AGS Finance Manager", "AGS Accountant", "AGS Group Executive",
	"AGS Principal", "AGS Auditor",
)


@analyzer(
	code="outstanding_tuition",
	question="What is outstanding tuition?",
	category="Finance",
	keywords=("outstanding", "tuition", "unpaid", "receivable", "owed", "balance"),
	roles=FINANCE_ROLES,
)
def outstanding_tuition(scope, **_params) -> Finding:
	"""Total unpaid school fees, split by ageing."""
	clause, params = campus_clause(scope, "si", "Sales Invoice")
	params.update({"company": scope.company})

	row = frappe.db.sql(
		f"""
		select
			sum(si.outstanding_amount) as outstanding,
			sum(case when si.due_date < curdate() then si.outstanding_amount else 0 end) as overdue,
			sum(si.grand_total) as billed,
			count(distinct si.ags_payer_account) as payers
		from `tabSales Invoice` si
		where si.docstatus = 1 and si.outstanding_amount > 0
		  and si.ags_fee_plan is not null
		  and si.company = %(company)s
		  and {clause}
		""",
		params,
		as_dict=True,
	)[0]

	outstanding = flt(row.outstanding, 2)
	overdue = flt(row.overdue, 2)

	finding = Finding(
		code="outstanding_tuition",
		title=_("Outstanding school fees"),
		headline=outstanding,
		unit="Currency",
		notes=campus_note(scope, "Sales Invoice"),
	)

	if not outstanding:
		finding.summary = _("Nothing is currently outstanding.")
		finding.insufficient_data = True
		return finding

	finding.summary = _(
		"{0} is outstanding across {1} payer account(s); {2} of that is already overdue."
	).format(
		frappe.utils.fmt_money(outstanding),
		int(row.payers or 0),
		frappe.utils.fmt_money(overdue),
	)
	finding.rows = [
		{"label": _("Outstanding"), "value": outstanding},
		{"label": _("Of which overdue"), "value": overdue},
		{"label": _("Overdue share"),
		 "value": flt(overdue / outstanding * 100, 1) if outstanding else 0},
	]
	return finding


@analyzer(
	code="overdue_by_campus",
	question="Which campus has the highest overdue balance?",
	category="Finance",
	keywords=("campus", "overdue", "worst", "highest", "compare", "which"),
	roles=FINANCE_ROLES,
)
def overdue_by_campus(scope, **_params) -> Finding:
	"""Overdue receivables ranked by campus."""
	clause, params = campus_clause(scope, "si", "Sales Invoice")
	params.update({"company": scope.company})

	rows = frappe.db.sql(
		f"""
		select coalesce(si.campus, '—') as campus,
		       sum(case when si.due_date < curdate() then si.outstanding_amount else 0 end) as overdue,
		       sum(si.outstanding_amount) as outstanding,
		       sum(si.grand_total) as billed
		from `tabSales Invoice` si
		where si.docstatus = 1 and si.ags_fee_plan is not null
		  and si.company = %(company)s
		  and {clause}
		group by coalesce(si.campus, '—')
		order by overdue desc
		""",
		params,
		as_dict=True,
	)

	finding = Finding(
		code="overdue_by_campus",
		title=_("Overdue by campus"),
		unit="Currency",
		notes=campus_note(scope, "Sales Invoice"),
	)

	rows = [r for r in rows if flt(r.overdue) > 0]
	if not rows:
		finding.summary = _("No campus currently carries an overdue balance.")
		finding.insufficient_data = True
		return finding

	worst = rows[0]
	finding.headline = flt(worst.overdue, 2)
	finding.summary = _(
		"{0} carries the highest overdue balance at {1}, which is {2}% of what "
		"has been billed there."
	).format(
		worst.campus,
		frappe.utils.fmt_money(worst.overdue),
		flt(flt(worst.overdue) / flt(worst.billed) * 100, 1) if flt(worst.billed) else 0,
	)
	finding.rows = [
		{
			"campus": r.campus,
			"overdue": flt(r.overdue, 2),
			"outstanding": flt(r.outstanding, 2),
			"billed": flt(r.billed, 2),
			"overdue_percent": flt(flt(r.overdue) / flt(r.billed) * 100, 1)
			if flt(r.billed) else 0,
		}
		for r in rows
	]
	return finding


@analyzer(
	code="margin_drivers",
	question="Why did operating margin change?",
	category="Finance",
	keywords=("margin", "why", "profit", "explain", "driver", "changed", "decrease"),
	roles=FINANCE_ROLES,
	description="Decomposes the movement in operating margin into ranked drivers.",
)
def margin_drivers(scope, **_params) -> Finding:
	"""Year-on-year margin bridge, ranked by contribution.

	This is the analysis behind the worked output in SKILL sec. 28.1 - revenue
	down, payroll up, maintenance up - and it is arithmetic, not a language
	model guessing at causes.
	"""
	prior_from, prior_to = prior_period(scope.from_date, scope.to_date)

	income_now = account_totals(scope, "Income", scope.from_date, scope.to_date)
	income_then = account_totals(scope, "Income", prior_from, prior_to)
	expense_now = account_totals(scope, "Expense", scope.from_date, scope.to_date)
	expense_then = account_totals(scope, "Expense", prior_from, prior_to)

	revenue_now, revenue_then = sum(income_now.values()), sum(income_then.values())
	cost_now, cost_then = sum(expense_now.values()), sum(expense_then.values())

	finding = Finding(
		code="margin_drivers",
		title=_("Operating margin drivers"),
		unit="Percent",
		notes=campus_note(scope, "GL Entry"),
	)

	if not revenue_then and not revenue_now:
		finding.summary = _("There is no posted revenue in either period to compare.")
		finding.insufficient_data = True
		return finding

	margin_now = flt((revenue_now - cost_now) / revenue_now * 100, 2) if revenue_now else 0.0
	margin_then = flt((revenue_then - cost_then) / revenue_then * 100, 2) if revenue_then else 0.0
	movement = flt(margin_now - margin_then, 2)

	finding.headline = movement

	if not revenue_then:
		finding.summary = _(
			"Operating margin is {0}% for {1} → {2}. There is no comparable prior "
			"year, so no driver analysis is possible yet."
		).format(margin_now, scope.from_date, scope.to_date)
		finding.insufficient_data = True
		return finding

	# Expenses are signed negative so a cost increase reads as a drag on margin,
	# which is how a CFO reads a bridge.
	combined_now = {**income_now, **{k: -v for k, v in expense_now.items()}}
	combined_then = {**income_then, **{k: -v for k, v in expense_then.items()}}
	finding.drivers = rank_drivers(combined_now, combined_then, limit=6)

	direction = _("fell") if movement < 0 else (_("rose") if movement > 0 else _("held"))
	finding.summary = _(
		"Operating margin {0} from {1}% to {2}% year on year "
		"({3} percentage points). Revenue {4}, costs {5}."
	).format(
		direction, margin_then, margin_now, movement,
		_change_phrase(revenue_then, revenue_now),
		_change_phrase(cost_then, cost_now),
	)

	finding.rows = [
		{"label": _("Revenue"), "current": flt(revenue_now, 2), "previous": flt(revenue_then, 2)},
		{"label": _("Costs"), "current": flt(cost_now, 2), "previous": flt(cost_then, 2)},
		{"label": _("Margin %"), "current": margin_now, "previous": margin_then},
	]
	return finding


def _change_phrase(previous: float, current: float) -> str:
	if not previous:
		return _("has no prior-year comparison")
	pct = flt((current - previous) / abs(previous) * 100, 1)
	if pct > 0:
		return _("up {0}%").format(pct)
	if pct < 0:
		return _("down {0}%").format(abs(pct))
	return _("flat")


@analyzer(
	code="budget_overrun",
	question="Why did expenses exceed budget?",
	category="Finance",
	keywords=("budget", "overrun", "exceed", "over", "variance", "why"),
	roles=FINANCE_ROLES,
)
def budget_overrun(scope, **_params) -> Finding:
	"""Accounts spending above budget, ranked by the size of the overrun."""
	fiscal_year = frappe.db.get_value(
		"Fiscal Year",
		{"year_start_date": ("<=", nowdate()), "year_end_date": (">=", nowdate())},
		["name", "year_start_date", "year_end_date"],
		as_dict=True,
	)

	finding = Finding(
		code="budget_overrun",
		title=_("Budget overruns"),
		unit="Currency",
	)
	if not fiscal_year:
		finding.summary = _("No fiscal year covers today, so budgets cannot be evaluated.")
		finding.insufficient_data = True
		return finding

	# Budget shape differs across ERPNext versions; commitments.py already knows
	# how to read either, so the budgeted figure is sourced through it rather
	# than duplicating the version check here.
	from ags_edusmart.ags_procurement.commitments import available_budget

	budgets = _budget_lines(scope, fiscal_year)
	if not budgets:
		finding.summary = _("No budgets are set for {0}.").format(fiscal_year.name)
		finding.insufficient_data = True
		return finding

	rows = []
	for line in budgets:
		status = available_budget(
			scope.company, line["account"], line["cost_center"], fiscal_year.name
		)
		spent = flt(status["actual"], 2)
		budget = flt(status["budget"], 2)
		if budget <= 0:
			continue
		variance = flt(spent - budget, 2)
		rows.append({
			"account": line["account"],
			"cost_center": line["cost_center"],
			"budget": budget,
			"actual": spent,
			"committed": flt(status["committed"], 2),
			"variance": variance,
			"variance_percent": flt(variance / budget * 100, 1),
		})

	overruns = sorted(
		[r for r in rows if r["variance"] > 0], key=lambda r: r["variance"], reverse=True
	)

	if not overruns:
		at_risk = sorted(
			[r for r in rows if r["actual"] + r["committed"] > r["budget"]],
			key=lambda r: r["actual"] + r["committed"] - r["budget"], reverse=True,
		)
		finding.headline = 0.0
		finding.rows = at_risk[:10]
		finding.summary = (
			_("No account is over budget on actuals. {0} line(s) would exceed budget "
			  "once open commitments are included.").format(len(at_risk))
			if at_risk else _("No account is over budget.")
		)
		return finding

	total = flt(sum(r["variance"] for r in overruns), 2)
	finding.headline = total
	finding.rows = overruns[:10]
	finding.drivers = rank_drivers(
		{r["account"]: r["actual"] for r in overruns},
		{r["account"]: r["budget"] for r in overruns},
		limit=5,
	)
	finding.summary = _(
		"{0} account(s) are over budget for {1}, by {2} in total. The largest is "
		"{3} at {4} over ({5}%)."
	).format(
		len(overruns), fiscal_year.name, frappe.utils.fmt_money(total),
		overruns[0]["account"], frappe.utils.fmt_money(overruns[0]["variance"]),
		overruns[0]["variance_percent"],
	)
	return finding


def _budget_lines(scope, fiscal_year) -> list[dict]:
	"""Budget (account, cost_center) pairs, across both ERPNext shapes."""
	if frappe.get_meta("Budget").has_field("accounts"):
		return frappe.db.sql(
			"""
			select ba.account as account, b.cost_center as cost_center
			from `tabBudget Account` ba
			inner join `tabBudget` b on b.name = ba.parent
			where b.docstatus = 1 and b.company = %(company)s
			  and b.fiscal_year = %(fy)s and b.cost_center is not null
			""",
			{"company": scope.company, "fy": fiscal_year.name},
			as_dict=True,
		)
	return frappe.db.sql(
		"""
		select b.account as account, b.cost_center as cost_center
		from `tabBudget` b
		where b.docstatus = 1 and b.company = %(company)s
		  and b.cost_center is not null
		  and b.budget_start_date <= %(end)s and b.budget_end_date >= %(start)s
		""",
		{
			"company": scope.company,
			"start": fiscal_year.year_start_date,
			"end": fiscal_year.year_end_date,
		},
		as_dict=True,
	)


@analyzer(
	code="expected_collection",
	question="What is expected cash collection next month?",
	category="Finance",
	keywords=("expect", "forecast", "collection", "next month", "cash", "projection"),
	roles=FINANCE_ROLES,
)
def expected_collection(scope, months: int = 1, **_params) -> Finding:
	"""Forecast collections from scheduled installments and historical behaviour.

	Two components, kept visibly separate because they carry very different
	confidence:

    * **Scheduled** - installments falling due in the window. Known amounts.
    * **Recovery** - a share of the existing overdue book, estimated from how
      much of what fell due in the last six months has actually been collected.

	Presenting them as one number would imply a precision the second half does
	not have.
	"""
	start = getdate(nowdate())
	end = getdate(add_months(start, int(months)))

	clause, params = campus_clause(scope, "p", "AGS Fee Plan")
	params.update({"start": str(start), "end": str(end)})

	scheduled = flt(frappe.db.sql(
		f"""
		select sum(i.amount)
		from `tabAGS Fee Plan Installment` i
		inner join `tabAGS Fee Plan` p on p.name = i.parent
		where p.docstatus = 1 and p.status = 'Active'
		  and i.status in ('Pending', 'Invoiced', 'Partially Paid')
		  and i.due_date between %(start)s and %(end)s
		  and {clause}
		""",
		params,
	)[0][0], 2)

	rate = _collection_rate(scope)
	overdue = _overdue_total(scope)
	# Recovery on the overdue book is assumed to run at half the on-time rate.
	# It is a deliberately conservative placeholder, stated in the notes rather
	# than buried, so finance can replace it with their own experience.
	recovery = flt(overdue * rate * 0.5, 2)

	finding = Finding(
		code="expected_collection",
		title=_("Expected collection"),
		headline=flt(scheduled * rate + recovery, 2),
		unit="Currency",
		notes=[
			_("Recovery on the overdue book is estimated at half the observed "
			  "collection rate. Adjust once the school has its own history."),
		] + campus_note(scope, "AGS Fee Plan"),
	)

	if not scheduled and not overdue:
		finding.summary = _("Nothing is scheduled or outstanding in this window.")
		finding.insufficient_data = True
		return finding

	finding.rows = [
		{"label": _("Falling due in window"), "value": scheduled},
		{"label": _("Observed collection rate"), "value": flt(rate * 100, 1)},
		{"label": _("Expected from scheduled"), "value": flt(scheduled * rate, 2)},
		{"label": _("Overdue book"), "value": overdue},
		{"label": _("Expected recovery"), "value": recovery},
	]
	finding.summary = _(
		"About {0} is expected over the next {1} month(s): {2} from the {3} "
		"falling due at the observed {4}% collection rate, plus an estimated {5} "
		"recovered from the {6} already overdue."
	).format(
		frappe.utils.fmt_money(finding.headline), int(months),
		frappe.utils.fmt_money(flt(scheduled * rate, 2)),
		frappe.utils.fmt_money(scheduled), flt(rate * 100, 1),
		frappe.utils.fmt_money(recovery), frappe.utils.fmt_money(overdue),
	)
	return finding


def _collection_rate(scope) -> float:
	"""Share of recently-due billing that has actually been collected."""
	clause, params = campus_clause(scope, "si", "Sales Invoice")
	params.update({
		"company": scope.company,
		"since": str(add_months(getdate(nowdate()), -6)),
	})
	row = frappe.db.sql(
		f"""
		select sum(si.grand_total) as billed,
		       sum(si.grand_total - si.outstanding_amount) as collected
		from `tabSales Invoice` si
		where si.docstatus = 1 and si.ags_fee_plan is not null
		  and si.company = %(company)s and si.due_date >= %(since)s
		  and si.due_date <= curdate()
		  and {clause}
		""",
		params,
		as_dict=True,
	)[0]
	billed = flt(row.billed)
	if not billed:
		# No history: assume full collection rather than inventing a shortfall.
		return 1.0
	return max(0.0, min(1.0, flt(row.collected) / billed))


def _overdue_total(scope) -> float:
	clause, params = campus_clause(scope, "si", "Sales Invoice")
	params.update({"company": scope.company})
	return flt(frappe.db.sql(
		f"""
		select sum(si.outstanding_amount) from `tabSales Invoice` si
		where si.docstatus = 1 and si.outstanding_amount > 0
		  and si.ags_fee_plan is not null and si.due_date < curdate()
		  and si.company = %(company)s and {clause}
		""",
		params,
	)[0][0], 2)


@analyzer(
	code="revenue_trend",
	question="How is revenue trending?",
	category="Finance",
	keywords=("revenue", "trend", "growth", "income", "compare", "year"),
	roles=FINANCE_ROLES,
)
def revenue_trend(scope, **_params) -> Finding:
	"""Revenue this window against the same window a year earlier."""
	prior_from, prior_to = prior_period(scope.from_date, scope.to_date)
	now_value = flt(root_total(scope, "Income", scope.from_date, scope.to_date), 2)
	then_value = flt(root_total(scope, "Income", prior_from, prior_to), 2)

	finding = Finding(
		code="revenue_trend",
		title=_("Revenue trend"),
		headline=now_value,
		unit="Currency",
		notes=campus_note(scope, "GL Entry"),
	)

	if not now_value and not then_value:
		finding.summary = _("No revenue is posted in either period.")
		finding.insufficient_data = True
		return finding

	finding.drivers = rank_drivers(
		account_totals(scope, "Income", scope.from_date, scope.to_date),
		account_totals(scope, "Income", prior_from, prior_to),
		limit=5,
	)
	finding.summary = _("Revenue is {0} for {1} → {2}, {3} year on year.").format(
		frappe.utils.fmt_money(now_value), scope.from_date, scope.to_date,
		_change_phrase(then_value, now_value),
	)
	finding.rows = [
		{"label": _("This period"), "value": now_value},
		{"label": _("Same period last year"), "value": then_value},
	]
	return finding
