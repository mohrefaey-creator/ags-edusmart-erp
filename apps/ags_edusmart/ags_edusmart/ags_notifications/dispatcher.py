"""Notification engine (SKILL sec. 35).

Everything is queued into AGS Notification Outbox and drained by a background
worker. Sending inline would put a third-party SMS gateway on the critical path
of a fee payment, which is exactly the wrong trade at 07:00 on a school day.

The unique ``dedupe_key`` is the idempotency guarantee: re-running a rule, a
scheduler retry after a crash, or two workers racing all collapse to one row.
"""

from __future__ import annotations

import frappe
from frappe.utils import add_to_date, cint, now

MAX_ATTEMPTS = 5

# Documents that would otherwise make the "*" hook recurse or churn.
IGNORED_DOCTYPES = {
	"AGS Notification Outbox",
	"Notification Log",
	"Version",
	"Error Log",
	"Scheduled Job Log",
	"Activity Log",
	"Access Log",
	"Route History",
}


def queue_message(
	channel: str,
	recipient: str,
	subject: str,
	message: str,
	dedupe_key: str | None = None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
	priority: str = "Normal",
	recipient_user: str | None = None,
	scheduled_for=None,
) -> bool:
	"""Queue one message. True when a row was created, False when it existed."""
	if not recipient:
		return False

	if dedupe_key and frappe.db.exists("AGS Notification Outbox", {"dedupe_key": dedupe_key}):
		return False

	doc = frappe.get_doc({
		"doctype": "AGS Notification Outbox",
		"channel": channel,
		"recipient": recipient,
		"recipient_user": recipient_user,
		"subject": subject,
		"message": message,
		"status": "Queued",
		"priority": priority,
		"scheduled_for": scheduled_for or now(),
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
		"dedupe_key": dedupe_key,
	})
	try:
		doc.insert(ignore_permissions=True)
	except frappe.DuplicateEntryError:
		# Lost a race with a parallel worker; the message is queued either way.
		return False
	return True


def flush_outbox(limit: int = 500) -> dict:
	rows = frappe.get_all(
		"AGS Notification Outbox",
		filters={"status": "Queued", "scheduled_for": ("<=", now())},
		fields=[
			"name", "channel", "recipient", "recipient_user", "subject", "message",
			"attempts", "reference_doctype", "reference_name",
		],
		order_by="field(priority, 'Urgent', 'High', 'Normal', 'Low'), creation asc",
		limit=limit,
	)

	sent = failed = 0
	for row in rows:
		try:
			_deliver(row)
			frappe.db.set_value(
				"AGS Notification Outbox", row.name,
				{"status": "Sent", "sent_on": now(), "attempts": cint(row.attempts) + 1},
				update_modified=False,
			)
			sent += 1
		except Exception:
			attempts = cint(row.attempts) + 1
			# Back off, then park the row as Failed so a human can inspect it.
			status = "Failed" if attempts >= MAX_ATTEMPTS else "Queued"
			frappe.db.set_value(
				"AGS Notification Outbox", row.name,
				{
					"status": status,
					"attempts": attempts,
					"error": frappe.get_traceback()[-1000:],
					"scheduled_for": add_to_date(now(), minutes=5 * attempts),
				},
				update_modified=False,
			)
			failed += 1
		frappe.db.commit()

	return {"sent": sent, "failed": failed}


def _deliver(row) -> None:
	channel = row.channel
	if channel == "In-App":
		_deliver_in_app(row)
	elif channel == "Email":
		_deliver_email(row)
	elif channel == "SMS":
		_deliver_via_gateway(row, "sms_gateway_url")
	elif channel == "WhatsApp":
		_deliver_via_gateway(row, "whatsapp_gateway_url")
	else:
		raise ValueError(f"unknown channel {channel}")


def _deliver_in_app(row) -> None:
	user = row.recipient_user or row.recipient
	if not frappe.db.exists("User", user):
		raise ValueError(f"no such user for in-app notification: {user}")
	frappe.get_doc({
		"doctype": "Notification Log",
		"for_user": user,
		"type": "Alert",
		"subject": row.subject,
		"email_content": row.message,
		"document_type": row.reference_doctype,
		"document_name": row.reference_name,
	}).insert(ignore_permissions=True)


def _deliver_email(row) -> None:
	frappe.sendmail(
		recipients=[row.recipient],
		subject=row.subject,
		message=row.message,
		reference_doctype=row.reference_doctype,
		reference_name=row.reference_name,
		now=True,
	)


def _deliver_via_gateway(row, url_field: str) -> None:
	cfg = frappe.get_cached_doc("AGS Settings")
	url = cfg.get(url_field)
	if not url:
		raise ValueError(f"{url_field} is not configured in AGS Settings")

	import requests

	response = requests.post(
		url,
		json={
			"to": row.recipient,
			"subject": row.subject,
			"message": frappe.utils.strip_html(row.message or ""),
		},
		timeout=15,
	)
	if response.status_code >= 300:
		raise RuntimeError(f"gateway {response.status_code}: {response.text[:300]}")


# --------------------------------------------------------------- rule engine
def on_document_change(doc, method=None) -> None:
	"""Bound to doc_events "*", so it stays cheap when a doctype has no rules."""
	if doc.doctype in IGNORED_DOCTYPES:
		return
	if getattr(doc, "flags", None) and doc.flags.get("ags_skip_notifications"):
		return

	rules = _rules_for(doc.doctype)
	if not rules:
		return

	event = _event_name(doc, method)
	for rule in rules:
		if rule["event"] != event:
			continue
		if not _condition_passes(rule, doc):
			continue
		_queue_rule(rule, doc)


def _rules_for(doctype: str):
	def loader():
		return frappe.get_all(
			"AGS Notification Rule",
			filters={"is_active": 1, "document_type": doctype},
			fields=[
				"name", "event", "condition", "recipient_type", "recipient_role",
				"recipient_field", "channels", "subject", "message", "priority",
				"value_changed_field",
			],
		)

	return frappe.cache().hget("ags_notification_rules", doctype, generator=loader)


def clear_rule_cache() -> None:
	frappe.cache().delete_key("ags_notification_rules")


def _event_name(doc, method: str | None) -> str:
	mapping = {
		"on_submit": "On Submit",
		"on_cancel": "On Cancel",
		"on_update": "On Update",
		"after_insert": "On Create",
	}
	if method in mapping:
		return mapping[method]
	if doc.docstatus == 1:
		return "On Submit"
	if doc.docstatus == 2:
		return "On Cancel"
	return "On Update"


def _condition_passes(rule, doc) -> bool:
	if not rule.get("condition"):
		return True
	try:
		return bool(frappe.safe_eval(rule["condition"], None, {"doc": doc}))
	except Exception:
		frappe.log_error(
			title="AGS: notification condition failed",
			message=f"{rule['name']}\n{frappe.get_traceback()}",
		)
		return False


def _queue_rule(rule, doc) -> None:
	context = {"doc": doc}
	try:
		subject = frappe.render_template(rule["subject"], context)
		message = frappe.render_template(rule["message"], context)
	except Exception:
		frappe.log_error(
			title="AGS: notification template failed",
			message=f"{rule['name']}\n{frappe.get_traceback()}",
		)
		return

	channels = [c.strip() for c in (rule["channels"] or "In-App").split(",") if c.strip()]
	for user, address in _recipients(rule, doc):
		for channel in channels:
			target = address if channel in ("Email", "SMS", "WhatsApp") else user
			if not target:
				continue
			queue_message(
				channel=channel,
				recipient=target,
				recipient_user=user,
				subject=subject,
				message=message,
				dedupe_key=f"{rule['name']}|{doc.doctype}|{doc.name}|{channel}|{target}",
				reference_doctype=doc.doctype,
				reference_name=doc.name,
				priority=rule.get("priority") or "Normal",
			)


def _recipients(rule, doc) -> list[tuple]:
	"""Yield (user, contact_address) pairs for the rule's recipient type."""
	kind = rule["recipient_type"]

	if kind == "Role" and rule.get("recipient_role"):
		users = frappe.get_all(
			"Has Role",
			filters={"role": rule["recipient_role"], "parenttype": "User"},
			pluck="parent",
		)
		enabled = frappe.get_all(
			"User",
			filters={"name": ("in", users or [""]), "enabled": 1},
			fields=["name", "email"],
		)
		return [(u.name, u.email) for u in enabled]

	if kind == "Document Owner":
		return [(doc.owner, frappe.db.get_value("User", doc.owner, "email"))]

	if kind == "Field Value" and rule.get("recipient_field"):
		return _resolve_field_recipient(doc.get(rule["recipient_field"]))

	if kind == "Payer Account":
		payer = doc.get("payer_account") or doc.get("ags_payer_account")
		if not payer:
			return []
		row = frappe.db.get_value(
			"AGS Payer Account", payer, ["guardian", "email"], as_dict=True
		)
		if not row:
			return []
		user = frappe.db.get_value("Guardian", row.guardian, "user") if row.guardian else None
		return [(user, row.email)]

	if kind == "Employee":
		employee = doc.get("employee") or doc.get("to_employee")
		if not employee:
			return []
		user = frappe.db.get_value("Employee", employee, "user_id")
		return [(user, frappe.db.get_value("User", user, "email") if user else None)]

	if kind == "Approver":
		from ags_edusmart.ags_approvals.engine import current_approvers

		return current_approvers(doc)

	return []


def _resolve_field_recipient(value) -> list[tuple]:
	if not value:
		return []
	if frappe.db.exists("User", value):
		return [(value, frappe.db.get_value("User", value, "email"))]
	if frappe.db.exists("Employee", value):
		user = frappe.db.get_value("Employee", value, "user_id")
		return [(user, frappe.db.get_value("User", user, "email") if user else None)]
	if frappe.db.exists("AGS Payer Account", value):
		row = frappe.db.get_value(
			"AGS Payer Account", value, ["guardian", "email"], as_dict=True
		)
		user = frappe.db.get_value("Guardian", row.guardian, "user") if row.guardian else None
		return [(user, row.email)]
	return []
