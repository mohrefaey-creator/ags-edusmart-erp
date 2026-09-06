# Asset maintenance alerting (SKILL sec. 10.5).
#
# ERPNext already schedules and logs maintenance; this only surfaces what is due
# to the people who act on it, and rolls the dashboard numbers up per campus.
import frappe
from frappe import _
from frappe.utils import add_days, nowdate

from ags_edusmart.ags_notifications.dispatcher import queue_message


def notify_due_maintenance(horizon_days=7):
	horizon = add_days(nowdate(), horizon_days)

	tasks = frappe.db.sql(
		"""
		select amt.parent as asset_maintenance, amt.task, amt.next_due_date,
		       amt.assign_to, am.asset_name, am.asset_category, am.company
		from `tabAsset Maintenance Task` amt
		inner join `tabAsset Maintenance` am on am.name = amt.parent
		where amt.next_due_date <= %(horizon)s
		  and amt.maintenance_status in ('Planned', 'Overdue')
		limit 500
		""",
		{"horizon": horizon},
		as_dict=True,
	)

	queued = 0
	for row in tasks:
		user = row.assign_to
		if not user:
			continue
		overdue = row.next_due_date and str(row.next_due_date) < nowdate()
		if queue_message(
			channel="In-App",
			recipient=user,
			recipient_user=user,
			subject=_("Maintenance {0}: {1}").format(
				_("overdue") if overdue else _("due"), row.asset_name
			),
			message=_("Task '{0}' on {1} is due {2}.").format(
				row.task, row.asset_name, row.next_due_date
			),
			dedupe_key=f"maint|{row.asset_maintenance}|{row.task}|{user}|{nowdate()}",
			reference_doctype="Asset Maintenance",
			reference_name=row.asset_maintenance,
			priority="High" if overdue else "Normal",
		):
			queued += 1

	from ags_edusmart.ags_assets.handover import notify_overdue_returns

	queued += notify_overdue_returns()
	frappe.db.commit()
	return {"queued": queued}


@frappe.whitelist()
def maintenance_dashboard(company, campus=None):
	# Counts for the asset dashboard tiles.
	rows = frappe.db.sql(
		"""
		select
			sum(case when amt.next_due_date = curdate() then 1 else 0 end) as due_today,
			sum(case when amt.next_due_date between curdate() and date_add(curdate(), interval 7 day)
			         then 1 else 0 end) as due_this_week,
			sum(case when amt.next_due_date < curdate()
			          and amt.maintenance_status != 'Completed' then 1 else 0 end) as overdue,
			sum(case when amt.maintenance_status = 'Completed' then 1 else 0 end) as completed
		from `tabAsset Maintenance Task` amt
		inner join `tabAsset Maintenance` am on am.name = amt.parent
		where am.company = %(company)s
		""",
		{"company": company},
		as_dict=True,
	)
	return rows[0] if rows else {}
