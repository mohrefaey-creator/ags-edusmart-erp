# The reminder ladder (SKILL sec. 20.1).
#
# Reminders are queued into the notification outbox rather than sent inline, so a
# slow SMS gateway can never stall the nightly job. Every send carries a dedupe
# key of rule + invoice + target date, which makes the whole run idempotent: a
# retry after a partial failure re-queues nothing that already went out.
import frappe
from frappe.utils import add_days, flt, getdate, nowdate

from ags_edusmart.ags_notifications.dispatcher import queue_message


def run_reminder_rules(as_of=None):
	as_of = getdate(as_of or nowdate())
	cfg = frappe.get_cached_doc("AGS Settings")
	if not cfg.enable_notifications:
		return {"skipped": "notifications disabled"}

	rules = frappe.get_all(
		"AGS Reminder Rule",
		filters={"is_active": 1},
		fields=["name", "trigger", "days", "channels", "subject", "message",
		        "company", "campus", "minimum_amount", "escalation_level",
		        "escalate_to_role", "stop_if_promise_to_pay"],
	)

	queued = 0
	for rule in rules:
		try:
			queued += _run_rule(rule, as_of)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(
				title="AGS: reminder rule failed",
				message=f"{rule.name}\n{frappe.get_traceback()}",
			)
	return {"queued": queued}


def _target_due_date(rule, as_of):
	# Which due_date does this rule fire against today?
	if rule.trigger == "Days Before Due":
		return add_days(as_of, int(rule.days or 0))
	if rule.trigger == "On Due Date":
		return as_of
	return add_days(as_of, -int(rule.days or 0))


def _run_rule(rule, as_of):
	due_date = _target_due_date(rule, as_of)

	conditions = [
		"si.docstatus = 1",
		"si.outstanding_amount > 0",
		"si.ags_payer_account is not null",
		"si.due_date = %(due_date)s",
	]
	params = {"due_date": due_date, "minimum": flt(rule.minimum_amount or 0)}
	if rule.company:
		conditions.append("si.company = %(company)s")
		params["company"] = rule.company
	if rule.campus:
		conditions.append("si.campus = %(campus)s")
		params["campus"] = rule.campus
	conditions.append("si.outstanding_amount >= %(minimum)s")

	invoices = frappe.db.sql(
		f"""
		select si.name, si.customer, si.company, si.due_date, si.outstanding_amount,
		       si.ags_payer_account, si.ags_student
		from `tabSales Invoice` si
		where {" and ".join(conditions)}
		limit 2000
		""",
		params,
		as_dict=True,
	)

	queued = 0
	for invoice in invoices:
		if rule.stop_if_promise_to_pay and _has_open_promise(invoice.ags_payer_account, as_of):
			_log(rule, invoice, "Skipped", "promise to pay on file", as_of)
			continue
		queued += _queue_for_invoice(rule, invoice, as_of)
	return queued


def _has_open_promise(payer_account, as_of):
	case = frappe.db.get_value(
		"AGS Collection Case",
		{"payer_account": payer_account, "status": ("not in", ("Resolved", "Written Off"))},
		"name",
	)
	if not case:
		return False
	promised = frappe.get_all(
		"AGS Collection Action",
		filters={"parent": case, "parenttype": "AGS Collection Case",
		         "outcome": "Promise To Pay"},
		fields=["promised_date"],
		order_by="action_date desc",
		limit=1,
	)
	return bool(promised and promised[0].promised_date
	            and getdate(promised[0].promised_date) >= as_of)


def _queue_for_invoice(rule, invoice, as_of):
	payer = frappe.db.get_value(
		"AGS Payer Account", invoice.ags_payer_account,
		["name", "payer_name", "email", "mobile", "preferred_channel"],
		as_dict=True,
	)
	if not payer:
		return 0

	student_name = frappe.db.get_value("Student", invoice.ags_student, "student_name") \
		if invoice.ags_student else ""
	context = {
		"payer": payer,
		"invoice": invoice,
		"student_name": student_name,
		"amount": frappe.utils.fmt_money(invoice.outstanding_amount),
		"outstanding": frappe.utils.fmt_money(
			frappe.db.get_value("AGS Payer Account", payer.name, "outstanding") or 0
		),
		"due_date": frappe.utils.formatdate(invoice.due_date),
		"days": rule.days,
		"company": invoice.company,
	}
	subject = frappe.render_template(rule.subject, context)
	message = frappe.render_template(rule.message, context)

	channels = [c.strip() for c in (rule.channels or "In-App").split(",") if c.strip()]
	queued = 0
	for channel in channels:
		recipient = _recipient_for(channel, payer)
		if not recipient:
			continue
		key = f"{rule.name}|{invoice.name}|{channel}|{as_of}"
		if queue_message(
			channel=channel,
			recipient=recipient,
			subject=subject,
			message=message,
			dedupe_key=key,
			reference_doctype="Sales Invoice",
			reference_name=invoice.name,
			priority="High" if (rule.escalation_level or 0) >= 2 else "Normal",
		):
			queued += 1
			_log(rule, invoice, "Sent", "", as_of, channel=channel, recipient=recipient)

	if rule.escalation_level:
		_escalate(rule, invoice)
	return queued


def _recipient_for(channel, payer):
	if channel == "Email":
		return payer.email
	if channel in ("SMS", "WhatsApp"):
		return payer.mobile
	# In-App is addressed to the portal user behind the guardian record.
	guardian = frappe.db.get_value("AGS Payer Account", payer.name, "guardian")
	return frappe.db.get_value("Guardian", guardian, "user") if guardian else None


def _escalate(rule, invoice):
	case = frappe.db.get_value(
		"AGS Collection Case",
		{"payer_account": invoice.ags_payer_account,
		 "status": ("not in", ("Resolved", "Written Off"))},
		"name",
	)
	if not case:
		return
	current = frappe.db.get_value("AGS Collection Case", case, "escalation_level") or 0
	if int(rule.escalation_level) > int(current):
		frappe.db.set_value(
			"AGS Collection Case", case,
			{"escalation_level": rule.escalation_level, "status": "Escalated"},
			update_modified=False,
		)


def _log(rule, invoice, status, error, as_of, channel="In-App", recipient=None):
	key = f"{rule.name}|{invoice.name}|{channel}|{as_of}"
	if frappe.db.exists("AGS Reminder Log", {"dedupe_key": key}):
		return
	frappe.get_doc({
		"doctype": "AGS Reminder Log",
		"payer_account": invoice.ags_payer_account,
		"sales_invoice": invoice.name,
		"reminder_rule": rule.name,
		"channel": channel,
		"sent_on": frappe.utils.now(),
		"status": status,
		"recipient": recipient,
		"amount": invoice.outstanding_amount,
		"error": error,
		"dedupe_key": key,
	}).insert(ignore_permissions=True)
