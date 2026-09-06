# Document expiry reminders (SKILL sec. 35).
import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate

from ags_edusmart.ags_notifications.dispatcher import queue_message

STATUS_WINDOW_DAYS = 60


def refresh_statuses():
	today = getdate(nowdate())
	frappe.db.sql(
		"""
		update `tabAGS Document Expiry`
		set status = case
			when expiry_date < %(today)s then 'Expired'
			when expiry_date <= date_add(%(today)s, interval reminder_days day)
				then 'Expiring Soon'
			else 'Valid'
		end
		where status != 'Renewed'
		""",
		{"today": today},
	)


def notify_document_expiry():
	refresh_statuses()

	rows = frappe.get_all(
		"AGS Document Expiry",
		filters={"status": ("in", ("Expiring Soon", "Expired"))},
		fields=["name", "employee", "employee_name", "document_type", "expiry_date",
		        "status", "campus", "last_reminded_on"],
		limit=1000,
	)

	hr_users = frappe.get_all(
		"Has Role",
		filters={"role": "AGS HR Manager", "parenttype": "User"},
		pluck="parent",
	)

	queued = 0
	today = nowdate()
	for row in rows:
		# One reminder per document per day, whatever else runs.
		if row.last_reminded_on and str(row.last_reminded_on) == today:
			continue

		subject = _("{0} {1} for {2}").format(
			row.document_type,
			_("has expired") if row.status == "Expired" else _("expires soon"),
			row.employee_name or row.employee,
		)
		message = _("{0} for {1} expires on {2}.").format(
			row.document_type, row.employee_name or row.employee, row.expiry_date
		)

		targets = set(hr_users)
		employee_user = frappe.db.get_value("Employee", row.employee, "user_id")
		if employee_user:
			targets.add(employee_user)

		for user in targets:
			if queue_message(
				channel="In-App",
				recipient=user,
				recipient_user=user,
				subject=subject,
				message=message,
				dedupe_key=f"expiry|{row.name}|{user}|{today}",
				reference_doctype="AGS Document Expiry",
				reference_name=row.name,
				priority="Urgent" if row.status == "Expired" else "High",
			):
				queued += 1

		frappe.db.set_value(
			"AGS Document Expiry", row.name, "last_reminded_on", today,
			update_modified=False,
		)

	frappe.db.commit()
	return {"queued": queued}


@frappe.whitelist()
def expiring_within(days=60, company=None, campus=None):
	filters = {"expiry_date": ("<=", add_days(nowdate(), int(days)))}
	if company:
		filters["company"] = company
	if campus:
		filters["campus"] = campus
	return frappe.get_all(
		"AGS Document Expiry",
		filters=filters,
		fields=["employee", "employee_name", "document_type", "document_number",
		        "expiry_date", "status", "campus"],
		order_by="expiry_date asc",
	)
