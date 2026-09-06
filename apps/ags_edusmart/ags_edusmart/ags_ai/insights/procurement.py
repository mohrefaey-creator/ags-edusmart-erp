"""Procurement analyses (SKILL sec. 28.2).

* Which supplier should we select?
* Which purchase orders are delayed?
* Which items can be consolidated into one purchase?
* Where are we paying above historical price?

The supplier question stops at a *ranking with its reasoning shown*. SKILL
sec. 8.4 is explicit that the final award stays a human decision, and an
analysis that reads as a recommendation-to-be-rubber-stamped would quietly
erode that.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from ags_edusmart.ags_ai.insights._base import campus_clause, campus_note
from ags_edusmart.ags_ai.registry import Finding, analyzer

PROCUREMENT_ROLES = (
	"AGS Procurement Manager", "AGS Procurement Officer", "AGS Finance Manager",
	"AGS Group Executive", "AGS Principal",
)


@analyzer(
	code="supplier_ranking",
	question="Which supplier performs best?",
	category="Procurement",
	keywords=("supplier", "vendor", "best", "select", "choose", "performance", "rank"),
	roles=PROCUREMENT_ROLES,
)
def supplier_ranking(scope, item_code: str | None = None, limit: int = 10,
                     **_params) -> Finding:
	"""Suppliers ranked on delivery reliability and billing accuracy."""
	params = {"company": scope.company, "from_date": scope.from_date,
	          "to_date": scope.to_date, "limit": int(limit)}
	item_join = ""
	if item_code:
		item_join = "and exists (select 1 from `tabPurchase Order Item` poi " \
		            "where poi.parent = po.name and poi.item_code = %(item_code)s)"
		params["item_code"] = item_code

	rows = frappe.db.sql(
		f"""
		select
			po.supplier,
			count(*) as orders,
			sum(po.grand_total) as value,
			avg(datediff(coalesce(pr.posting_date, curdate()), po.transaction_date))
				as avg_lead_days,
			sum(case when po.status in ('Completed', 'Closed') then 1 else 0 end)
				as completed
		from `tabPurchase Order` po
		left join `tabPurchase Receipt Item` pri on pri.purchase_order = po.name
		left join `tabPurchase Receipt` pr on pr.name = pri.parent and pr.docstatus = 1
		where po.docstatus = 1 and po.company = %(company)s
		  and po.transaction_date between %(from_date)s and %(to_date)s
		  {item_join}
		group by po.supplier
		order by value desc
		limit %(limit)s
		""",
		params,
		as_dict=True,
	)

	finding = Finding(
		code="supplier_ranking",
		title=_("Supplier performance"),
		unit="Number",
		notes=[_("Ranking is advisory. The award remains a human decision "
		         "(SKILL sec. 8.4).")],
	)

	if not rows:
		finding.summary = _("No purchase orders were placed in this period.")
		finding.insufficient_data = True
		return finding

	# Exceptions raised by three-way matching are the strongest available signal
	# of a supplier that bills differently from what it quoted.
	exceptions = dict(frappe.db.sql(
		"""
		select supplier, count(*) from `tabAGS Three Way Match Exception`
		where company = %(company)s and creation between %(from_date)s and %(to_date)s
		group by supplier
		""",
		params,
	) or [])

	enriched = []
	for row in rows:
		orders = int(row.orders or 0)
		completion = flt(int(row.completed or 0) / orders * 100, 1) if orders else 0.0
		mismatches = int(exceptions.get(row.supplier, 0))
		enriched.append({
			"supplier": row.supplier,
			"orders": orders,
			"value": flt(row.value, 2),
			"avg_lead_days": flt(row.avg_lead_days, 1),
			"completion_percent": completion,
			"invoice_mismatches": mismatches,
			"mismatch_rate": flt(mismatches / orders * 100, 1) if orders else 0.0,
		})

	# Deliberately simple and legible: completion is the reward, lateness and
	# billing mismatches are the penalties. A weighted black box would be harder
	# to argue with in a tender review, which is the wrong property here.
	for row in enriched:
		row["score"] = flt(
			row["completion_percent"]
			- min(row["avg_lead_days"], 60)
			- row["mismatch_rate"] * 2,
			1,
		)

	enriched.sort(key=lambda r: r["score"], reverse=True)
	best = enriched[0]

	finding.headline = float(len(enriched))
	finding.rows = enriched
	finding.summary = _(
		"{0} supplier(s) were used. {1} ranks highest: {2}% of orders completed, "
		"{3} days average lead time, {4} invoice mismatch(es) across {5} order(s)."
	).format(
		len(enriched), best["supplier"], best["completion_percent"],
		best["avg_lead_days"], best["invoice_mismatches"], best["orders"],
	)
	return finding


@analyzer(
	code="delayed_orders",
	question="Which purchase orders are delayed?",
	category="Procurement",
	keywords=("delayed", "late", "overdue", "purchase order", "pending", "outstanding"),
	roles=PROCUREMENT_ROLES,
)
def delayed_orders(scope, limit: int = 25, **_params) -> Finding:
	"""Submitted orders past their required-by date and not fully received."""
	clause, params = campus_clause(scope, "po", "Purchase Order")
	params.update({"company": scope.company, "limit": int(limit)})

	rows = frappe.db.sql(
		f"""
		select po.name, po.supplier, po.transaction_date, po.schedule_date,
		       po.grand_total, po.per_received, po.status,
		       datediff(curdate(), po.schedule_date) as days_late
		from `tabPurchase Order` po
		where po.docstatus = 1
		  and po.status not in ('Completed', 'Closed', 'Cancelled')
		  and po.per_received < 100
		  and po.schedule_date < curdate()
		  and po.company = %(company)s and {clause}
		order by days_late desc
		limit %(limit)s
		""",
		params,
		as_dict=True,
	)

	finding = Finding(
		code="delayed_orders",
		title=_("Delayed purchase orders"),
		unit="Number",
		notes=campus_note(scope, "Purchase Order"),
	)

	if not rows:
		finding.headline = 0.0
		finding.summary = _("No purchase order is past its required date.")
		finding.insufficient_data = True
		return finding

	value = flt(sum(flt(r.grand_total) * (100 - flt(r.per_received)) / 100 for r in rows), 2)
	finding.headline = float(len(rows))
	finding.rows = [
		{
			"purchase_order": r.name,
			"supplier": r.supplier,
			"required_by": str(r.schedule_date),
			"days_late": int(r.days_late or 0),
			"value": flt(r.grand_total, 2),
			"received_percent": flt(r.per_received, 1),
		}
		for r in rows
	]
	finding.summary = _(
		"{0} order(s) are late, with about {1} still undelivered. The worst is "
		"{2} from {3}, {4} days past its required date."
	).format(
		len(rows), frappe.utils.fmt_money(value), rows[0].name, rows[0].supplier,
		int(rows[0].days_late or 0),
	)
	return finding


@analyzer(
	code="price_drift",
	question="Where are we paying above historical price?",
	category="Procurement",
	keywords=("price", "expensive", "above", "historical", "increase", "paying", "cost"),
	roles=PROCUREMENT_ROLES,
)
def price_drift(scope, threshold_percent: float = 10.0, limit: int = 20,
                **_params) -> Finding:
	"""Items whose latest purchase price is materially above their own average."""
	rows = frappe.db.sql(
		"""
		select
			poi.item_code,
			poi.item_name,
			count(*) as purchases,
			avg(poi.base_rate) as avg_rate,
			max(po.transaction_date) as last_date
		from `tabPurchase Order Item` poi
		inner join `tabPurchase Order` po on po.name = poi.parent
		where po.docstatus = 1 and po.company = %(company)s
		  and po.transaction_date between %(from_date)s and %(to_date)s
		  and poi.base_rate > 0
		group by poi.item_code, poi.item_name
		having count(*) >= 2
		""",
		{"company": scope.company, "from_date": scope.from_date, "to_date": scope.to_date},
		as_dict=True,
	)

	finding = Finding(
		code="price_drift",
		title=_("Items purchased above their historical price"),
		unit="Percent",
	)
	if not rows:
		finding.summary = _(
			"Not enough repeat purchases in this period to compare prices. "
			"An item needs at least two orders."
		)
		finding.insufficient_data = True
		return finding

	drifted = []
	for row in rows:
		latest = frappe.db.sql(
			"""
			select poi.base_rate
			from `tabPurchase Order Item` poi
			inner join `tabPurchase Order` po on po.name = poi.parent
			where po.docstatus = 1 and poi.item_code = %(item)s
			  and po.company = %(company)s and poi.base_rate > 0
			order by po.transaction_date desc, po.creation desc
			limit 1
			""",
			{"item": row.item_code, "company": scope.company},
		)
		if not latest:
			continue
		latest_rate = flt(latest[0][0])
		avg_rate = flt(row.avg_rate)
		if avg_rate <= 0:
			continue
		drift = flt((latest_rate - avg_rate) / avg_rate * 100, 1)
		if drift >= flt(threshold_percent):
			drifted.append({
				"item_code": row.item_code,
				"item_name": row.item_name,
				"latest_rate": flt(latest_rate, 2),
				"average_rate": flt(avg_rate, 2),
				"drift_percent": drift,
				"purchases": int(row.purchases),
				"last_purchased": str(row.last_date),
			})

	drifted.sort(key=lambda r: r["drift_percent"], reverse=True)

	if not drifted:
		finding.headline = 0.0
		finding.summary = _(
			"No item's latest price is more than {0}% above its own average."
		).format(flt(threshold_percent, 1))
		return finding

	finding.headline = drifted[0]["drift_percent"]
	finding.rows = drifted[:limit]
	finding.summary = _(
		"{0} item(s) were last bought more than {1}% above their average price. "
		"The largest gap is {2}, last bought at {3} against an average of {4} "
		"({5}% higher)."
	).format(
		len(drifted), flt(threshold_percent, 1), drifted[0]["item_name"] or drifted[0]["item_code"],
		frappe.utils.fmt_money(drifted[0]["latest_rate"]),
		frappe.utils.fmt_money(drifted[0]["average_rate"]),
		drifted[0]["drift_percent"],
	)
	return finding


@analyzer(
	code="consolidation_opportunities",
	question="Which purchases can be consolidated?",
	category="Procurement",
	keywords=("consolidate", "combine", "merge", "together", "bulk", "same item"),
	roles=PROCUREMENT_ROLES,
)
def consolidation_opportunities(scope, window_days: int = 30, limit: int = 20,
                                **_params) -> Finding:
	"""Items requested repeatedly in a short window across separate requests.

	Repeated small requests for the same item are where a school loses its
	volume discount, and they are invisible on any single document.
	"""
	clause, params = campus_clause(scope, "mr", "Material Request")
	params.update({"company": scope.company, "days": int(window_days), "limit": int(limit)})

	rows = frappe.db.sql(
		f"""
		select
			mri.item_code,
			mri.item_name,
			count(distinct mr.name) as requests,
			sum(mri.qty) as total_qty,
			count(distinct mr.ags_campus) as campuses
		from `tabMaterial Request Item` mri
		inner join `tabMaterial Request` mr on mr.name = mri.parent
		where mr.docstatus = 1 and mr.company = %(company)s
		  and mr.transaction_date >= date_sub(curdate(), interval %(days)s day)
		  and {clause}
		group by mri.item_code, mri.item_name
		having count(distinct mr.name) > 1
		order by requests desc, total_qty desc
		limit %(limit)s
		""",
		params,
		as_dict=True,
	)

	finding = Finding(
		code="consolidation_opportunities",
		title=_("Consolidation opportunities"),
		unit="Number",
		notes=campus_note(scope, "Material Request"),
	)

	if not rows:
		finding.headline = 0.0
		finding.summary = _(
			"No item was requested more than once in the last {0} days."
		).format(int(window_days))
		finding.insufficient_data = True
		return finding

	finding.headline = float(len(rows))
	finding.rows = [
		{
			"item_code": r.item_code,
			"item_name": r.item_name,
			"requests": int(r.requests),
			"total_qty": flt(r.total_qty, 2),
			"campuses": int(r.campuses or 0),
		}
		for r in rows
	]
	top = rows[0]
	finding.summary = _(
		"{0} item(s) were requested on more than one separate request in the last "
		"{1} days. {2} leads with {3} requests totalling {4} units - buying those "
		"together would consolidate the order."
	).format(
		len(rows), int(window_days), top.item_name or top.item_code,
		int(top.requests), flt(top.total_qty, 2),
	)
	return finding
