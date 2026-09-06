"""Default configuration shipped with the app.

Seeds are created only when absent, never updated, so a school that has tuned a
threshold does not have it silently reset on the next deploy.
"""

from __future__ import annotations

import frappe

# ---------------------------------------------------------------------------
# KPI definitions (SKILL sec. 27)
# ---------------------------------------------------------------------------
# ``method`` is resolved against ags_dashboards.kpi_library at refresh time.
KPIS: list[dict] = [
	{"code": "total_students", "kpi_name": "Students", "category": "Executive",
	 "unit": "Number", "method": "total_students"},
	{"code": "enrollment_growth", "kpi_name": "Enrollment Growth", "category": "Executive",
	 "unit": "Percent", "method": "enrollment_growth"},
	{"code": "total_revenue", "kpi_name": "Revenue", "category": "Finance",
	 "unit": "Currency", "method": "total_revenue"},
	{"code": "revenue_per_student", "kpi_name": "Revenue / Student", "category": "Executive",
	 "unit": "Currency", "method": "revenue_per_student"},
	{"code": "cost_per_student", "kpi_name": "Cost / Student", "category": "Executive",
	 "unit": "Currency", "method": "cost_per_student", "direction": "Lower Is Better"},
	{"code": "collection_percent", "kpi_name": "Collection %", "category": "Collections",
	 "unit": "Percent", "method": "collection_percent", "target_value": 95},
	{"code": "outstanding_fees", "kpi_name": "Outstanding Fees", "category": "Collections",
	 "unit": "Currency", "method": "outstanding_fees", "direction": "Lower Is Better"},
	{"code": "overdue_fees", "kpi_name": "Overdue Fees", "category": "Collections",
	 "unit": "Currency", "method": "overdue_fees", "direction": "Lower Is Better"},
	{"code": "outstanding_to_revenue", "kpi_name": "Outstanding / Revenue",
	 "category": "Collections", "unit": "Percent", "method": "outstanding_to_revenue",
	 "direction": "Lower Is Better"},
	{"code": "payroll_cost", "kpi_name": "Payroll Cost", "category": "HR",
	 "unit": "Currency", "method": "payroll_cost"},
	{"code": "payroll_to_revenue", "kpi_name": "Payroll / Revenue", "category": "Executive",
	 "unit": "Percent", "method": "payroll_to_revenue", "direction": "Lower Is Better",
	 "target_value": 55},
	{"code": "employee_cost_per_student", "kpi_name": "Employee Cost / Student",
	 "category": "HR", "unit": "Currency", "method": "employee_cost_per_student",
	 "direction": "Lower Is Better"},
	{"code": "students_per_teacher", "kpi_name": "Students / Teacher", "category": "Academic",
	 "unit": "Ratio", "method": "students_per_teacher"},
	{"code": "student_attendance_rate", "kpi_name": "Student Attendance Rate",
	 "category": "Academic", "unit": "Percent", "method": "student_attendance_rate",
	 "target_value": 95},
	{"code": "open_purchase_orders", "kpi_name": "Open Purchase Orders",
	 "category": "Procurement", "unit": "Currency", "method": "open_purchase_orders"},
	{"code": "invoice_mismatches", "kpi_name": "Invoice Mismatches", "category": "Procurement",
	 "unit": "Number", "method": "invoice_mismatches", "direction": "Lower Is Better"},
	{"code": "stock_value", "kpi_name": "Stock Value", "category": "Inventory",
	 "unit": "Currency", "method": "stock_value"},
	{"code": "items_below_reorder", "kpi_name": "Items Below Reorder", "category": "Inventory",
	 "unit": "Number", "method": "items_below_reorder", "direction": "Lower Is Better"},
	{"code": "budget_variance", "kpi_name": "Budget Variance", "category": "Finance",
	 "unit": "Percent", "method": "budget_variance", "direction": "Lower Is Better"},
	{"code": "cash_position", "kpi_name": "Cash Position", "category": "Finance",
	 "unit": "Currency", "method": "cash_position"},
]

# ---------------------------------------------------------------------------
# Reminder ladder (SKILL sec. 20.1)
# ---------------------------------------------------------------------------
REMINDERS: list[dict] = [
	{"title": "Fee Due in 7 Days", "trigger": "Days Before Due", "days": 7,
	 "subject": "School fees due in 7 days", "escalation_level": 0},
	{"title": "Fee Due in 3 Days", "trigger": "Days Before Due", "days": 3,
	 "subject": "School fees due in 3 days", "escalation_level": 0},
	{"title": "Fee Due Today", "trigger": "On Due Date", "days": 0,
	 "subject": "School fees due today", "escalation_level": 0},
	{"title": "Overdue 7 Days", "trigger": "Days After Due", "days": 7,
	 "subject": "School fees overdue", "escalation_level": 1},
	{"title": "Overdue 15 Days", "trigger": "Days After Due", "days": 15,
	 "subject": "School fees 15 days overdue", "escalation_level": 2},
	{"title": "Overdue 30 Days", "trigger": "Days After Due", "days": 30,
	 "subject": "School fees 30 days overdue - please contact the school",
	 "escalation_level": 3, "escalate_to_role": "AGS Collections Officer"},
]

_REMINDER_BODY = """<p>Dear {{ payer.payer_name }},</p>
<p>This is a reminder regarding invoice <b>{{ invoice.name }}</b> for
{{ student_name }}, amount <b>{{ amount }}</b>, due on <b>{{ due_date }}</b>.</p>
<p>Outstanding balance on your account: <b>{{ outstanding }}</b>.</p>
<p>Thank you,<br>{{ company }}</p>"""

# ---------------------------------------------------------------------------
# Approval matrices (SKILL sec. 8.3 and 17.7)
# ---------------------------------------------------------------------------
# Semantics: a level applies when amount >= from_amount, and (to_amount is 0 or
# amount <= to_amount). Cumulative chains therefore leave to_amount at 0.
MATRICES: list[dict] = [
	{
		"title": "Purchase Request Thresholds",
		"document_type": "Material Request",
		"amount_field": "ags_estimated_total",
		"levels": [
			{"level": 1, "approver_role": "AGS Department Head", "from_amount": 0,
			 "sla_hours": 24},
			{"level": 2, "approver_role": "AGS Finance Manager", "from_amount": 5000,
			 "sla_hours": 24},
			{"level": 3, "approver_role": "AGS Principal", "from_amount": 25000,
			 "sla_hours": 48},
			{"level": 4, "approver_role": "AGS Group Executive", "from_amount": 100000,
			 "sla_hours": 72, "can_override_budget": 1},
		],
	},
	{
		"title": "Purchase Order Thresholds",
		"document_type": "Purchase Order",
		"amount_field": "grand_total",
		"levels": [
			{"level": 1, "approver_role": "AGS Procurement Manager", "from_amount": 0,
			 "sla_hours": 24},
			{"level": 2, "approver_role": "AGS Finance Manager", "from_amount": 25000,
			 "sla_hours": 24},
			{"level": 3, "approver_role": "AGS Group Executive", "from_amount": 100000,
			 "sla_hours": 72, "can_override_budget": 1},
		],
	},
	{
		"title": "Discount Approval Tiers",
		"document_type": "AGS Discount Application",
		"amount_field": "discount_percent",
		"levels": [
			{"level": 1, "approver_role": "AGS Accountant", "from_amount": 0,
			 "to_amount": 5, "sla_hours": 24},
			{"level": 2, "approver_role": "AGS Finance Manager", "from_amount": 5,
			 "sla_hours": 24},
			{"level": 3, "approver_role": "AGS Principal", "from_amount": 15,
			 "sla_hours": 48},
			{"level": 4, "approver_role": "AGS Group Executive", "from_amount": 25,
			 "sla_hours": 72},
		],
	},
	{
		"title": "Fee Waiver Approval",
		"document_type": "AGS Fee Waiver",
		"amount_field": "waiver_amount",
		"levels": [
			{"level": 1, "approver_role": "AGS Finance Manager", "from_amount": 0,
			 "sla_hours": 24},
			{"level": 2, "approver_role": "AGS Group Executive", "from_amount": 10000,
			 "sla_hours": 72},
		],
	},
]

# ---------------------------------------------------------------------------
# Notification rules (SKILL sec. 35)
# ---------------------------------------------------------------------------
NOTIFICATIONS: list[dict] = [
	{"title": "Purchase Request Awaiting Approval", "document_type": "Material Request",
	 "event": "On Submit", "recipient_type": "Approver", "channels": "In-App, Email",
	 "subject": "Purchase request {{ doc.name }} awaits your approval",
	 "message": "<p>{{ doc.ags_purpose or doc.name }} requires approval.</p>"},
	{"title": "Goods Received", "document_type": "Purchase Receipt", "event": "On Submit",
	 "recipient_type": "Role", "recipient_role": "AGS Procurement Officer",
	 "channels": "In-App",
	 "subject": "Goods received against {{ doc.name }}",
	 "message": "<p>Goods receipt {{ doc.name }} has been posted.</p>"},
	{"title": "Asset Handover Acknowledgement", "document_type": "AGS Asset Handover",
	 "event": "On Submit", "recipient_type": "Field Value", "recipient_field": "to_employee",
	 "channels": "In-App, Email",
	 "subject": "Please acknowledge assets issued to you",
	 "message": "<p>Assets have been issued to you on {{ doc.handover_date }}. "
	            "Please open the record and acknowledge receipt.</p>"},
	{"title": "Fee Plan Activated", "document_type": "AGS Fee Plan", "event": "On Submit",
	 "recipient_type": "Payer Account", "channels": "In-App, Email",
	 "subject": "Fee plan for {{ doc.student_name }} is ready",
	 "message": "<p>The fee plan for {{ doc.student_name }} totalling "
	            "{{ doc.net_total }} is now available in your portal.</p>"},
]


def seed_all() -> None:
	seed_kpis()
	seed_reminder_rules()
	seed_approval_matrices()
	seed_notification_rules()


def seed_kpis() -> None:
	for row in KPIS:
		if frappe.db.exists("AGS KPI Definition", row["code"]):
			continue
		frappe.get_doc({
			"doctype": "AGS KPI Definition",
			"code": row["code"],
			"kpi_name": row["kpi_name"],
			"category": row["category"],
			"unit": row["unit"],
			"source": "Method",
			"method_path": row["method"],
			"direction": row.get("direction", "Higher Is Better"),
			"target_value": row.get("target_value"),
			"refresh_interval_minutes": row.get("refresh_interval_minutes", 60),
			"is_active": 1,
		}).insert(ignore_permissions=True)


def seed_reminder_rules() -> None:
	for row in REMINDERS:
		if frappe.db.exists("AGS Reminder Rule", row["title"]):
			continue
		doc = frappe.get_doc({
			"doctype": "AGS Reminder Rule",
			"title": row["title"],
			"trigger": row["trigger"],
			"days": row["days"],
			"channels": "In-App, Email",
			"subject": row["subject"],
			"message": _REMINDER_BODY,
			"escalation_level": row.get("escalation_level", 0),
			"is_active": 1,
		})
		if row.get("escalate_to_role") and frappe.db.exists("Role", row["escalate_to_role"]):
			doc.escalate_to_role = row["escalate_to_role"]
		doc.insert(ignore_permissions=True)


def seed_approval_matrices() -> None:
	for row in MATRICES:
		if frappe.db.exists("AGS Approval Matrix", row["title"]):
			continue
		if not frappe.db.exists("DocType", row["document_type"]):
			continue
		doc = frappe.get_doc({
			"doctype": "AGS Approval Matrix",
			"title": row["title"],
			"document_type": row["document_type"],
			"amount_field": row["amount_field"],
			"is_active": 1,
		})
		for level in row["levels"]:
			if not frappe.db.exists("Role", level["approver_role"]):
				continue
			doc.append("levels", level)
		if not doc.levels:
			continue
		doc.insert(ignore_permissions=True)


def seed_notification_rules() -> None:
	for row in NOTIFICATIONS:
		if frappe.db.exists("AGS Notification Rule", row["title"]):
			continue
		if not frappe.db.exists("DocType", row["document_type"]):
			continue
		if row.get("recipient_role") and not frappe.db.exists("Role", row["recipient_role"]):
			continue
		frappe.get_doc({"doctype": "AGS Notification Rule", "is_active": 1, **row}).insert(
			ignore_permissions=True
		)
