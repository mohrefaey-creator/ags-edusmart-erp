"""Inventory analyses (SKILL sec. 28.3).

* What will run out next month?
* Which departments consume unusually high stationery?
* Which items have not moved in six months?

"Unusually high" is defined here as a **robust** outlier - distance from the
median, scaled by the median absolute deviation - rather than a mean and standard
deviation. With a dozen departments, one science lab stocking up for a term is
enough to drag a mean far enough that it hides the very outlier you are looking
for.
"""

from __future__ import annotations

import statistics

import frappe
from frappe import _
from frappe.utils import add_months, flt, getdate, nowdate

from ags_edusmart.ags_ai.insights._base import campus_clause, campus_note
from ags_edusmart.ags_ai.registry import Finding, analyzer

INVENTORY_ROLES = (
	"AGS Storekeeper", "AGS Procurement Manager", "AGS Procurement Officer",
	"AGS Finance Manager", "AGS Group Executive", "AGS Principal",
)


def _robust_outliers(values: dict[str, float], sensitivity: float = 3.5) -> dict[str, float]:
	"""Modified z-scores keyed by label.

	Uses median absolute deviation, so a single extreme value cannot mask the
	others. 3.5 is the conventional cut-off for this statistic.
	"""
	if len(values) < 3:
		return {}
	series = list(values.values())
	median = statistics.median(series)
	deviations = [abs(v - median) for v in series]
	mad = statistics.median(deviations)
	if not mad:
		return {}
	return {
		label: flt(0.6745 * (value - median) / mad, 2)
		for label, value in values.items()
		if 0.6745 * (value - median) / mad >= sensitivity
	}


@analyzer(
	code="stockout_forecast",
	question="What will run out next month?",
	category="Inventory",
	keywords=("run out", "stockout", "shortage", "reorder", "low stock", "next month"),
	roles=INVENTORY_ROLES,
)
def stockout_forecast(scope, horizon_days: int = 30, limit: int = 25,
                      **_params) -> Finding:
	"""Items whose consumption rate exhausts current stock within the horizon.

	The rate is measured over the last 90 days of actual issues, not over a
	planning assumption, so a term that has not started yet does not forecast a
	shortage that will not happen.
	"""
	since = str(add_months(getdate(nowdate()), -3))

	consumption = frappe.db.sql(
		"""
		select sle.item_code, sum(-sle.actual_qty) as issued
		from `tabStock Ledger Entry` sle
		inner join `tabWarehouse` w on w.name = sle.warehouse
		where sle.is_cancelled = 0 and sle.actual_qty < 0
		  and w.company = %(company)s
		  and sle.posting_date >= %(since)s
		group by sle.item_code
		having sum(-sle.actual_qty) > 0
		""",
		{"company": scope.company, "since": since},
		as_dict=True,
	)

	finding = Finding(
		code="stockout_forecast",
		title=_("Items forecast to run out"),
		unit="Number",
	)
	if not consumption:
		finding.headline = 0.0
		finding.summary = _(
			"No stock has been issued in the last 90 days, so no consumption rate "
			"can be measured yet."
		)
		finding.insufficient_data = True
		return finding

	on_hand = dict(frappe.db.sql(
		"""
		select b.item_code, sum(b.actual_qty)
		from `tabBin` b
		inner join `tabWarehouse` w on w.name = b.warehouse
		where w.company = %(company)s
		group by b.item_code
		""",
		{"company": scope.company},
	) or [])

	at_risk = []
	for row in consumption:
		daily = flt(row.issued) / 90.0
		if daily <= 0:
			continue
		stock = flt(on_hand.get(row.item_code, 0))
		days_left = stock / daily
		if days_left <= horizon_days:
			at_risk.append({
				"item_code": row.item_code,
				"item_name": frappe.db.get_value("Item", row.item_code, "item_name"),
				"on_hand": flt(stock, 2),
				"daily_usage": flt(daily, 3),
				"days_remaining": flt(days_left, 1),
				"suggested_order": flt(max(daily * horizon_days - stock, 0), 2),
			})

	at_risk.sort(key=lambda r: r["days_remaining"])

	if not at_risk:
		finding.headline = 0.0
		finding.summary = _(
			"No item is forecast to run out within {0} days at current usage."
		).format(int(horizon_days))
		return finding

	finding.headline = float(len(at_risk))
	finding.rows = at_risk[:limit]
	first = at_risk[0]
	finding.summary = _(
		"{0} item(s) are forecast to run out within {1} days at current usage. "
		"The most urgent is {2}, with {3} left and about {4} days of cover."
	).format(
		len(at_risk), int(horizon_days), first["item_name"] or first["item_code"],
		first["on_hand"], first["days_remaining"],
	)
	return finding


@analyzer(
	code="consumption_outliers",
	question="Which departments consume unusually high supplies?",
	category="Inventory",
	keywords=("department", "consume", "unusual", "high", "stationery", "outlier"),
	roles=INVENTORY_ROLES,
)
def consumption_outliers(scope, **_params) -> Finding:
	"""Departments whose issue value stands out against the others."""
	clause, params = campus_clause(scope, "di", "AGS Department Issue")
	params.update({
		"company": scope.company,
		"from_date": scope.from_date,
		"to_date": scope.to_date,
	})

	rows = frappe.db.sql(
		f"""
		select di.department, sum(di.total_amount) as value, count(*) as issues
		from `tabAGS Department Issue` di
		where di.docstatus = 1 and di.company = %(company)s
		  and di.posting_date between %(from_date)s and %(to_date)s
		  and {clause}
		group by di.department
		""",
		params,
		as_dict=True,
	)

	finding = Finding(
		code="consumption_outliers",
		title=_("Department consumption outliers"),
		unit="Currency",
		notes=campus_note(scope, "AGS Department Issue"),
	)

	if len(rows) < 3:
		finding.summary = _(
			"Only {0} department(s) have issued stock in this period. At least "
			"three are needed before one can be called unusual."
		).format(len(rows))
		finding.insufficient_data = True
		return finding

	values = {r.department: flt(r.value) for r in rows if r.department}
	outliers = _robust_outliers(values)

	finding.rows = sorted(
		[
			{
				"department": r.department,
				"value": flt(r.value, 2),
				"issues": int(r.issues),
				"outlier_score": outliers.get(r.department),
				"is_outlier": r.department in outliers,
			}
			for r in rows if r.department
		],
		key=lambda r: r["value"], reverse=True,
	)
	finding.headline = float(len(outliers))

	if not outliers:
		finding.summary = _(
			"No department stands out: consumption is evenly spread across {0} "
			"departments."
		).format(len(values))
		return finding

	worst = max(outliers, key=lambda k: outliers[k])
	finding.summary = _(
		"{0} department(s) consume unusually more than the rest. {1} is the "
		"clearest, at {2} against a median of {3}."
	).format(
		len(outliers), worst, frappe.utils.fmt_money(values[worst]),
		frappe.utils.fmt_money(statistics.median(values.values())),
	)
	return finding


@analyzer(
	code="non_moving_items",
	question="Which items have not moved in six months?",
	category="Inventory",
	keywords=("non moving", "slow", "dead stock", "unused", "six months", "stale"),
	roles=INVENTORY_ROLES,
)
def non_moving_items(scope, months: int = 6, limit: int = 25, **_params) -> Finding:
	"""Stock holding value with no movement in the given window."""
	cutoff = str(add_months(getdate(nowdate()), -int(months)))

	rows = frappe.db.sql(
		"""
		select b.item_code, i.item_name, sum(b.actual_qty) as qty,
		       sum(b.stock_value) as value,
		       (select max(sle.posting_date) from `tabStock Ledger Entry` sle
		        where sle.item_code = b.item_code and sle.is_cancelled = 0) as last_movement
		from `tabBin` b
		inner join `tabWarehouse` w on w.name = b.warehouse
		inner join `tabItem` i on i.name = b.item_code
		where w.company = %(company)s and b.actual_qty > 0
		group by b.item_code, i.item_name
		having last_movement is null or last_movement < %(cutoff)s
		order by value desc
		limit %(limit)s
		""",
		{"company": scope.company, "cutoff": cutoff, "limit": int(limit)},
		as_dict=True,
	)

	finding = Finding(
		code="non_moving_items",
		title=_("Non-moving stock"),
		unit="Currency",
	)

	if not rows:
		finding.headline = 0.0
		finding.summary = _("Every item in stock has moved in the last {0} months.").format(
			int(months)
		)
		return finding

	total = flt(sum(flt(r.value) for r in rows), 2)
	finding.headline = total
	finding.rows = [
		{
			"item_code": r.item_code,
			"item_name": r.item_name,
			"qty": flt(r.qty, 2),
			"value": flt(r.value, 2),
			"last_movement": str(r.last_movement) if r.last_movement else None,
		}
		for r in rows
	]
	finding.summary = _(
		"{0} item(s) worth {1} have not moved in {2} months. The largest holding "
		"is {3} at {4}."
	).format(
		len(rows), frappe.utils.fmt_money(total), int(months),
		rows[0].item_name or rows[0].item_code, frappe.utils.fmt_money(rows[0].value),
	)
	return finding
