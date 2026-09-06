"""One approval engine for every module (SKILL sec. 23).

Design note - why this is not "block the submit":

A submitted document that is *awaiting approval* is exactly the state SKILL
sec. 8.5 asks for ("Draft / Awaiting Approval / Approved / ..."). So submitting
raises an AGS Approval Request and stamps the document as pending; what the
engine actually gates is the **downstream consequence** - a Purchase Order cannot
be raised from an unapproved request, a discount does not reduce a fee plan until
its tier signs off, a waiver posts no credit note until approved. That keeps the
audit trail on one immutable document instead of a mutable draft.

Level semantics: a level applies when ``amount >= from_amount`` and
(``to_amount`` is 0 or ``amount <= to_amount``). Cumulative chains therefore
leave ``to_amount`` at 0, which is how the SKILL sec. 8.3 ladder is expressed.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, flt, now

# Documents the engine will never consider, to keep the "*" hook cheap.
IGNORED_DOCTYPES = {
	"AGS Approval Request",
	"AGS Approval Matrix",
	"AGS Notification Outbox",
	"Notification Log",
	"Version",
	"Error Log",
	"Scheduled Job Log",
	"Activity Log",
	"Access Log",
	"Route History",
	"Comment",
}

# Where the engine writes the pending/approved state back onto the document.
STATUS_FIELD = {
	"AGS Discount Application": "approval_status",
	"AGS Fee Waiver": "approval_status",
	"Material Request": "ags_approval_status",
	"Purchase Order": "ags_approval_status",
}


# ---------------------------------------------------------------- discovery
def matrices_for(doctype: str):
	def loader():
		return frappe.get_all(
			"AGS Approval Matrix",
			filters={"is_active": 1, "document_type": doctype},
			fields=["name", "amount_field", "condition", "company", "campus", "priority",
			        "escalate_after_hours", "escalate_to_role"],
			order_by="priority asc, name asc",
		)

	return frappe.cache().hget("ags_approval_matrices", doctype, generator=loader)


def clear_matrix_cache() -> None:
	frappe.cache().delete_key("ags_approval_matrices")


def pick_matrix(doc):
	"""Most specific active matrix that matches the document."""
	for row in matrices_for(doc.doctype):
		if row.get("company") and row["company"] != doc.get("company"):
			continue
		campus = doc.get("campus") or doc.get("ags_campus")
		if row.get("campus") and row["campus"] != campus:
			continue
		if row.get("condition"):
			try:
				if not frappe.safe_eval(row["condition"], None, {"doc": doc}):
					continue
			except Exception:
				frappe.log_error(
					title="AGS: approval matrix condition failed",
					message=f"{row['name']}\n{frappe.get_traceback()}",
				)
				continue
		return row
	return None


def required_levels(matrix_name: str, amount: float) -> list[dict]:
	levels = frappe.get_all(
		"AGS Approval Level",
		filters={"parent": matrix_name, "parenttype": "AGS Approval Matrix"},
		fields=["level", "approver_role", "specific_approver", "from_amount", "to_amount",
		        "sla_hours", "can_override_budget"],
		order_by="level asc",
	)
	chosen = []
	for level in levels:
		low = flt(level.from_amount)
		high = flt(level.to_amount)
		if amount < low:
			continue
		if high and amount > high:
			continue
		chosen.append(level)
	return chosen


# ------------------------------------------------------------------- events
def on_document_change(doc, method=None) -> None:
	if doc.doctype in IGNORED_DOCTYPES:
		return
	if doc.docstatus != 1:
		return
	if getattr(doc, "flags", None) and doc.flags.get("ags_skip_approvals"):
		return
	if not matrices_for(doc.doctype):
		return
	if frappe.db.exists(
		"AGS Approval Request",
		{"reference_doctype": doc.doctype, "reference_name": doc.name,
		 "status": ("in", ("Pending", "Approved"))},
	):
		return
	create_request(doc)


def create_request(doc):
	matrix = pick_matrix(doc)
	if not matrix:
		return None

	amount = flt(doc.get(matrix["amount_field"]) or 0)
	levels = required_levels(matrix["name"], amount)
	if not levels:
		_stamp(doc, "Approved")
		return None

	request = frappe.new_doc("AGS Approval Request")
	request.reference_doctype = doc.doctype
	request.reference_name = doc.name
	request.approval_matrix = matrix["name"]
	request.company = doc.get("company")
	request.campus = doc.get("campus") or doc.get("ags_campus")
	request.amount = amount
	request.requested_by = frappe.session.user
	request.status = "Pending"
	request.current_level = levels[0].level
	request.current_role = levels[0].approver_role
	request.due_by = add_to_date(now(), hours=cint(levels[0].sla_hours) or 24)

	for level in levels:
		request.append("logs", {
			"level": level.level,
			"approver_role": level.approver_role,
			"approver": level.specific_approver,
			"action": "Pending",
		})

	request.flags.ignore_permissions = True
	request.insert()

	_stamp(doc, "Pending")
	return request.name


def _stamp(doc, status: str) -> None:
	field = STATUS_FIELD.get(doc.doctype)
	if not field or not doc.meta.has_field(field):
		return
	# db_set on a submitted doc: allow_on_submit is set for these fields.
	doc.db_set(field, status, update_modified=False)


# ------------------------------------------------------------------ actions
@frappe.whitelist()
def approve(request: str, comments: str | None = None) -> dict:
	return _act(request, "Approved", comments)


@frappe.whitelist()
def reject(request: str, comments: str | None = None) -> dict:
	if not comments:
		frappe.throw(_("A rejection reason is required."))
	return _act(request, "Rejected", comments)


def _act(request_name: str, action: str, comments: str | None) -> dict:
	req = frappe.get_doc("AGS Approval Request", request_name)
	if req.status != "Pending":
		frappe.throw(_("This request is already {0}.").format(req.status))

	row = next(
		(r for r in req.logs if r.level == req.current_level and r.action == "Pending"), None
	)
	if not row:
		frappe.throw(_("No pending level found on this request."))

	if not _may_act(row):
		frappe.throw(
			_("Only {0} may act on level {1}.").format(row.approver_role, row.level),
			frappe.PermissionError,
		)

	row.action = action
	row.approver = frappe.session.user
	row.action_on = now()
	row.comments = comments

	if action == "Rejected":
		req.status = "Rejected"
		req.completed_on = now()
		req.current_role = None
	else:
		remaining = [r for r in req.logs if r.action == "Pending"]
		if remaining:
			nxt = min(remaining, key=lambda r: r.level)
			req.current_level = nxt.level
			req.current_role = nxt.approver_role
			sla = frappe.db.get_value(
				"AGS Approval Level",
				{"parent": req.approval_matrix, "level": nxt.level},
				"sla_hours",
			)
			req.due_by = add_to_date(now(), hours=cint(sla) or 24)
		else:
			req.status = "Approved"
			req.completed_on = now()
			req.current_role = None

	req.flags.ignore_permissions = True
	req.save()

	if req.status in ("Approved", "Rejected"):
		_finalise(req)

	frappe.db.commit()
	return {"status": req.status, "current_level": req.current_level}


def _may_act(row) -> bool:
	user = frappe.session.user
	if user == "Administrator":
		return True
	if row.approver and row.approver != user:
		return False
	return row.approver_role in set(frappe.get_roles(user))


def _finalise(req) -> None:
	"""Apply the approved consequence for this document type."""
	try:
		doc = frappe.get_doc(req.reference_doctype, req.reference_name)
	except frappe.DoesNotExistError:
		return

	_stamp(doc, req.status)

	if req.status != "Approved":
		if req.reference_doctype == "AGS Discount Application":
			doc.db_set("rejection_reason", _last_comment(req), update_modified=False)
		return

	if req.reference_doctype == "AGS Discount Application":
		from ags_edusmart.ags_fees.discount_application import apply_to_fee_plan

		apply_to_fee_plan(doc)
	elif req.reference_doctype == "AGS Fee Waiver":
		from ags_edusmart.ags_fees.waiver import post_credit_note

		post_credit_note(doc)


def _last_comment(req) -> str:
	rows = [r for r in req.logs if r.comments]
	return rows[-1].comments if rows else ""


# ---------------------------------------------------------------- guardrails
def assert_approved(doctype: str, name: str) -> None:
	"""Raise unless the document has cleared approval (or needs none)."""
	pending = frappe.db.exists(
		"AGS Approval Request",
		{"reference_doctype": doctype, "reference_name": name, "status": "Pending"},
	)
	if pending:
		frappe.throw(
			_("{0} {1} is still awaiting approval.").format(_(doctype), name),
			title=_("Approval Pending"),
		)
	rejected = frappe.db.exists(
		"AGS Approval Request",
		{"reference_doctype": doctype, "reference_name": name, "status": "Rejected"},
	)
	if rejected:
		frappe.throw(
			_("{0} {1} was rejected in approval.").format(_(doctype), name),
			title=_("Approval Rejected"),
		)


def current_approvers(doc) -> list[tuple]:
	"""(user, email) pairs who can act on this document right now."""
	req = frappe.db.get_value(
		"AGS Approval Request",
		{"reference_doctype": doc.doctype, "reference_name": doc.name, "status": "Pending"},
		["name", "current_role", "current_level"],
		as_dict=True,
	)
	if not req:
		return []

	pinned = frappe.db.get_value(
		"AGS Approval Log",
		{"parent": req.name, "level": req.current_level},
		"approver",
	)
	if pinned:
		return [(pinned, frappe.db.get_value("User", pinned, "email"))]

	users = frappe.get_all(
		"Has Role",
		filters={"role": req.current_role, "parenttype": "User"},
		pluck="parent",
	)
	rows = frappe.get_all(
		"User",
		filters={"name": ("in", users or [""]), "enabled": 1},
		fields=["name", "email"],
	)
	return [(r.name, r.email) for r in rows]


def escalate_overdue() -> int:
	"""Move breached SLAs up to the matrix's escalation role."""
	overdue = frappe.get_all(
		"AGS Approval Request",
		filters={"status": "Pending", "due_by": ("<", now())},
		fields=["name", "approval_matrix", "current_level", "current_role"],
		limit=500,
	)
	escalated = 0
	for req in overdue:
		role = frappe.db.get_value(
			"AGS Approval Matrix", req.approval_matrix, "escalate_to_role"
		)
		if not role or role == req.current_role:
			continue
		# Reassign the role on the still-pending level. The log row stays
		# "Pending" - marking it Escalated would drop the level out of the
		# remaining-levels check in _act and skip the approval entirely.
		frappe.db.set_value(
			"AGS Approval Request", req.name, "current_role", role, update_modified=False
		)
		frappe.db.sql(
			"""
			update `tabAGS Approval Log` set approver_role = %(role)s, approver = null
			where parent = %(parent)s and level = %(level)s and action = 'Pending'
			""",
			{"parent": req.name, "level": req.current_level, "role": role},
		)
		escalated += 1
	frappe.db.commit()
	return escalated
