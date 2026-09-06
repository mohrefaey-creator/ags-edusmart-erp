# Collection cases and AR ageing (SKILL sec. 20).
#
# A case is a derived view of the ledger, refreshed nightly and on every payment.
# The buckets are computed from due_date so they match the AR Ageing report
# finance already trusts, rather than inventing a second definition of "overdue".
import frappe
from frappe.utils import flt, getdate, now, nowdate

BUCKETS = (
	("bucket_current", 0),
	("bucket_1_30", 1),
	("bucket_31_60", 31),
	("bucket_61_90", 61),
	("bucket_91_120", 91),
	("bucket_120_plus", 121),
)


def bucket_for(days_overdue):
	if days_overdue <= 0:
		return "bucket_current"
	if days_overdue <= 30:
		return "bucket_1_30"
	if days_overdue <= 60:
		return "bucket_31_60"
	if days_overdue <= 90:
		return "bucket_61_90"
	if days_overdue <= 120:
		return "bucket_91_120"
	return "bucket_120_plus"


def compute_ageing(customer, as_of=None):
	as_of = getdate(as_of or nowdate())
	rows = frappe.get_all(
		"Sales Invoice",
		filters={"customer": customer, "docstatus": 1, "outstanding_amount": (">", 0)},
		fields=["name", "due_date", "outstanding_amount", "grand_total"],
	)

	result = {name: 0.0 for name, _ in BUCKETS}
	overdue = 0.0
	oldest = None
	max_days = 0

	for row in rows:
		out = flt(row.outstanding_amount)
		due = getdate(row.due_date) if row.due_date else as_of
		days = (as_of - due).days
		result[bucket_for(days)] += out
		if days > 0:
			overdue += out
			max_days = max(max_days, days)
			if oldest is None or due < oldest:
				oldest = due

	return {
		"buckets": {k: flt(v, 2) for k, v in result.items()},
		"overdue": flt(overdue, 2),
		"oldest_due_date": oldest,
		"days_overdue": max_days,
	}


def refresh_case_for_payer(payer_account, create_if_missing=True):
	payer = frappe.db.get_value(
		"AGS Payer Account",
		payer_account,
		["name", "customer", "company", "campus"],
		as_dict=True,
	)
	if not payer or not payer.customer:
		return None

	from ags_edusmart.ags_fees.payer import compute_summary

	summary = compute_summary(payer.customer)
	ageing = compute_ageing(payer.customer)

	case_name = frappe.db.get_value(
		"AGS Collection Case",
		{"payer_account": payer_account, "status": ("not in", ("Resolved", "Written Off"))},
		"name",
	)

	if not case_name:
		if summary["overdue"] <= 0 or not create_if_missing:
			return None
		case = frappe.new_doc("AGS Collection Case")
		case.payer_account = payer_account
		case.company = payer.company
		case.campus = payer.campus
		case.status = "Open"
		case.flags.ignore_permissions = True
		case.insert()
		case_name = case.name

	values = {
		"total_billed": summary["total_billed"],
		"total_paid": summary["total_paid"],
		"outstanding": summary["outstanding"],
		"overdue": ageing["overdue"],
		"oldest_due_date": ageing["oldest_due_date"],
		"days_overdue": ageing["days_overdue"],
		"last_refreshed_on": now(),
	}
	values.update(ageing["buckets"])

	# A case closes itself once the money is in; it is never silently deleted,
	# so the contact history stays available.
	current_status = frappe.db.get_value("AGS Collection Case", case_name, "status")
	if ageing["overdue"] <= 0 and current_status not in ("Resolved", "Written Off"):
		values["status"] = "Resolved"

	frappe.db.set_value("AGS Collection Case", case_name, values, update_modified=False)
	return case_name


def refresh_collection_cases(limit=5000):
	# Nightly sweep. Only payers with any outstanding are touched.
	payers = frappe.db.sql(
		"""
		select p.name
		from `tabAGS Payer Account` p
		where p.is_active = 1
		  and exists (
		      select 1 from `tabSales Invoice` si
		      where si.customer = p.customer and si.docstatus = 1
		        and si.outstanding_amount > 0
		  )
		limit %(limit)s
		""",
		{"limit": limit},
		as_dict=True,
	)

	touched = 0
	for row in payers:
		try:
			if refresh_case_for_payer(row.name):
				touched += 1
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(
				title="AGS: collection case refresh failed",
				message=f"{row.name}\n{frappe.get_traceback()}",
			)
	return touched


@frappe.whitelist()
def collection_dashboard(company=None, campus=None, academic_year=None):
	# Powers the collections dashboard tiles (SKILL sec. 20).
	conditions = ["si.docstatus = 1", "si.ags_fee_plan is not null"]
	params = {}
	if company:
		conditions.append("si.company = %(company)s")
		params["company"] = company
	if campus:
		conditions.append("si.campus = %(campus)s")
		params["campus"] = campus

	where = " and ".join(conditions)
	row = frappe.db.sql(
		f"""
		select
			sum(si.grand_total) as billed,
			sum(si.grand_total - si.outstanding_amount) as collected,
			sum(si.outstanding_amount) as outstanding,
			sum(case when si.due_date < curdate() then si.outstanding_amount else 0 end) as overdue
		from `tabSales Invoice` si
		where {where}
		""",
		params,
		as_dict=True,
	)[0]

	billed = flt(row.billed)
	collected = flt(row.collected)
	return {
		"billed": flt(billed, 2),
		"collected": flt(collected, 2),
		"outstanding": flt(row.outstanding, 2),
		"overdue": flt(row.overdue, 2),
		"collection_percent": flt(collected / billed * 100, 2) if billed else 0.0,
	}
