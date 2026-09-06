# Deferred tuition revenue (SKILL sec. 5.4).
#
# ERPNext already ships a deferred revenue engine: an Item flagged
# enable_deferred_revenue with service_start_date / service_end_date on the
# invoice line is amortised by the native scheduled job. Writing a second
# amortisation loop here would mean two engines posting to one ledger, which
# SKILL sec. 29 explicitly forbids - so this module only *configures* the native
# one and reports on it.
import frappe
from frappe import _
from frappe.utils import flt


def settings():
	return frappe.get_cached_doc("AGS Settings")


def is_enabled():
	cfg = settings()
	return bool(cfg.enable_deferred_revenue and cfg.deferred_revenue_account)


def service_period(academic_year):
	# The recognition window is the academic year, not the calendar year.
	if not academic_year:
		return None, None
	row = frappe.db.get_value(
		"Academic Year", academic_year, ["year_start_date", "year_end_date"], as_dict=True
	)
	if not row:
		return None, None
	return row.year_start_date, row.year_end_date


@frappe.whitelist()
def enable_on_fee_items(company=None):
	# Turns on native deferred revenue for every Item behind a Fee Category.
	cfg = settings()
	if not cfg.deferred_revenue_account:
		frappe.throw(_("Set the Deferred Tuition Revenue Account in AGS Settings first."))

	items = frappe.get_all("Fee Category", filters={"item": ("is", "set")}, pluck="item")
	updated = []
	for item in set(items):
		doc = frappe.get_doc("Item", item)
		if doc.enable_deferred_revenue and doc.deferred_revenue_account:
			continue
		doc.enable_deferred_revenue = 1
		doc.deferred_revenue_account = cfg.deferred_revenue_account
		doc.no_of_months = doc.no_of_months or 10
		doc.flags.ignore_permissions = True
		doc.save()
		updated.append(item)
	frappe.db.commit()
	return updated


def ensure_deferred_configuration():
	# Scheduled sanity check. Reports drift instead of silently mis-stating revenue.
	if not is_enabled():
		return {"enabled": False}

	cfg = settings()
	misconfigured = frappe.db.sql(
		"""
		select distinct fc.item
		from `tabFee Category` fc
		inner join `tabItem` i on i.name = fc.item
		where fc.item is not null
		  and (i.enable_deferred_revenue = 0 or i.deferred_revenue_account is null)
		""",
		as_dict=True,
	)
	if misconfigured:
		frappe.log_error(
			title="AGS: fee items missing deferred revenue configuration",
			message="\n".join(row.item for row in misconfigured),
		)
	return {
		"enabled": True,
		"account": cfg.deferred_revenue_account,
		"misconfigured_items": [row.item for row in misconfigured],
	}


@frappe.whitelist()
def deferred_balance(company):
	# Reads the liability straight off the GL so it always ties to the ledger.
	cfg = settings()
	if not cfg.deferred_revenue_account:
		return 0.0
	balance = frappe.db.sql(
		"""
		select sum(credit - debit) from `tabGL Entry`
		where account = %(account)s and company = %(company)s and is_cancelled = 0
		""",
		{"account": cfg.deferred_revenue_account, "company": company},
	)[0][0]
	return flt(balance, 2)
