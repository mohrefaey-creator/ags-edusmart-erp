# Late fee application (SKILL sec. 17.5).
#
# A late fee is a real revenue transaction, so it is raised as its own Sales
# Invoice against the payer rather than by editing the original invoice, which
# would break the audit trail on an already-submitted document.
import frappe
from frappe.utils import add_days, flt, getdate, nowdate


def apply_late_fees():
	cfg = frappe.get_cached_doc("AGS Settings")
	if not cfg.enable_late_fees or not cfg.late_fee_item:
		return {"skipped": "disabled"}

	grace = int(cfg.late_fee_grace_days or 0)
	cutoff = add_days(getdate(nowdate()), -grace)

	overdue = frappe.db.sql(
		"""
		select si.name, si.customer, si.company, si.outstanding_amount, si.due_date,
		       si.ags_payer_account, si.ags_student, si.campus
		from `tabSales Invoice` si
		where si.docstatus = 1 and si.outstanding_amount > 0
		  and si.due_date < %(cutoff)s
		  and si.ags_fee_plan is not null
		  and not exists (
		        select 1 from `tabSales Invoice` lf
		        where lf.docstatus = 1
		          and lf.ags_late_fee_against = si.name
		  )
		limit 500
		""",
		{"cutoff": cutoff},
		as_dict=True,
	)

	created = []
	for row in overdue:
		amount = _late_fee_amount(cfg, row.outstanding_amount)
		if amount <= 0:
			continue
		try:
			created.append(_raise_late_fee(cfg, row, amount))
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(
				title="AGS: late fee failed",
				message=f"{row.name}\n{frappe.get_traceback()}",
			)
	return {"created": created}


def _late_fee_amount(cfg, outstanding):
	if cfg.late_fee_type == "Percent of Overdue":
		return flt(flt(outstanding) * flt(cfg.late_fee_value) / 100.0, 2)
	return flt(cfg.late_fee_value, 2)


def _raise_late_fee(cfg, row, amount):
	invoice = frappe.new_doc("Sales Invoice")
	invoice.customer = row.customer
	invoice.company = row.company
	invoice.posting_date = nowdate()
	invoice.due_date = nowdate()
	if invoice.meta.has_field("ags_late_fee_against"):
		invoice.ags_late_fee_against = row.name
	invoice.ags_payer_account = row.ags_payer_account
	invoice.ags_student = row.ags_student
	if invoice.meta.has_field("campus"):
		invoice.campus = row.campus
	invoice.append("items", {
		"item_code": cfg.late_fee_item,
		"qty": 1,
		"rate": amount,
		"description": f"Late fee against invoice {row.name} (due {row.due_date})",
	})
	invoice.flags.ignore_permissions = True
	invoice.insert()
	invoice.submit()
	return invoice.name
