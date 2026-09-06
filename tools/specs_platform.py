"""Platform modules: Approvals, Dashboards/KPI, Notifications, HR, Localization.

The approval matrix is deliberately one configurable engine rather than per-module
approval code (SKILL sec. 23), and the KPI snapshot table is what keeps executive
dashboards cheap to read under the 07:00-15:00 load peak.
"""

from doctype_builder import SYS, column, doctype, f, perm, readonly_perm, section

FIN = "AGS Finance Manager"
HR = "AGS HR Manager"


def specs() -> list[tuple[dict, str | None]]:
	return _approvals() + _dashboards() + _notifications() + _hr() + _localization()


# ------------------------------------------------------------------ Approvals
def _approvals() -> list[tuple[dict, str | None]]:
	MODULE = "AGS Approvals"
	out: list[tuple[dict, str | None]] = []

	out.append((doctype(
		"AGS Approval Level", MODULE,
		[
			f("level", "Int", "Level", reqd=1, default="1", in_list_view=1, columns=1),
			f("approver_role", "Link", "Approver Role", options="Role", reqd=1,
			  in_list_view=1, columns=3),
			f("specific_approver", "Link", "Specific Approver", options="User",
			  description="Optional. Pins the level to one person instead of the whole role."),
			f("from_amount", "Currency", "From Amount", default="0", in_list_view=1,
			  columns=2),
			f("to_amount", "Currency", "To Amount", default="0", in_list_view=1,
			  columns=2, description="Zero means no upper bound."),
			f("sla_hours", "Int", "SLA (hours)", default="24"),
			f("can_override_budget", "Check", "May Override Budget", default="0"),
		],
		is_child=True,
	), None))

	out.append((doctype(
		"AGS Approval Matrix", MODULE,
		[
			section("sb_head"),
			f("title", "Data", "Title", reqd=1, in_list_view=1),
			f("document_type", "Link", "Document Type", options="DocType", reqd=1,
			  in_list_view=1, search_index=1),
			f("is_active", "Check", "Active", default="1", in_list_view=1),
			column("cb_head"),
			f("company", "Link", "Company", options="Company"),
			f("campus", "Link", "Campus", options="AGS Campus",
			  description="Blank applies to every campus."),
			f("priority", "Int", "Priority", default="10",
			  description="Lower wins when several matrices match."),

			section("sb_basis", "Routing Basis"),
			f("amount_field", "Data", "Amount Field", default="grand_total",
			  description="Field read for threshold routing, e.g. grand_total or discount_percent."),
			f("condition", "Code", "Additional Condition", options="Python",
			  description="Optional Python expression over `doc`. Example: doc.campus == 'Jeddah'."),
			column("cb_basis"),
			f("escalate_after_hours", "Int", "Escalate After (hours)", default="48"),
			f("escalate_to_role", "Link", "Escalate To Role", options="Role"),

			section("sb_levels", "Approval Levels"),
			f("levels", "Table", "Levels", options="AGS Approval Level", reqd=1),
		],
		autoname="field:title",
		title_field="title",
		search_fields="document_type,campus",
		permissions=[perm(SYS), perm(FIN, delete=False)],
		description="One configurable engine for every approval in the system (SKILL sec. 23).",
	), None))

	out.append((doctype(
		"AGS Approval Log", MODULE,
		[
			f("level", "Int", "Level", in_list_view=1, columns=1),
			f("approver_role", "Data", "Role", in_list_view=1, columns=2),
			f("approver", "Link", "Approver", options="User", in_list_view=1, columns=2),
			f("action", "Select", "Action",
			  options="Pending\nApproved\nRejected\nDelegated\nEscalated",
			  default="Pending", in_list_view=1, columns=2),
			f("action_on", "Datetime", "On", in_list_view=1, columns=2),
			f("comments", "Small Text", "Comments"),
		],
		is_child=True,
	), None))

	out.append((doctype(
		"AGS Approval Request", MODULE,
		[
			section("sb_ref"),
			f("reference_doctype", "Link", "Document Type", options="DocType", reqd=1,
			  in_list_view=1, search_index=1),
			f("reference_name", "Dynamic Link", "Document", options="reference_doctype",
			  reqd=1, in_list_view=1, search_index=1),
			f("approval_matrix", "Link", "Matrix", options="AGS Approval Matrix",
			  read_only=1),
			column("cb_ref"),
			f("company", "Link", "Company", options="Company"),
			f("campus", "Link", "Campus", options="AGS Campus", search_index=1),
			f("amount", "Currency", "Amount", read_only=1, in_list_view=1),
			f("requested_by", "Link", "Requested By", options="User", read_only=1),

			section("sb_state", "State"),
			f("status", "Select", "Status",
			  options="Pending\nApproved\nRejected\nCancelled", default="Pending",
			  in_list_view=1, search_index=1),
			f("current_level", "Int", "Current Level", default="1", read_only=1,
			  in_list_view=1),
			column("cb_state"),
			f("current_role", "Data", "Awaiting Role", read_only=1, in_list_view=1),
			f("due_by", "Datetime", "SLA Due By", read_only=1),
			f("completed_on", "Datetime", "Completed On", read_only=1),

			section("sb_log", "Trail"),
			f("logs", "Table", "Approval Trail", options="AGS Approval Log", read_only=1),
		],
		autoname="hash",
		permissions=[
			perm(SYS), perm(FIN, delete=False), readonly_perm("Employee"),
		],
		sort_field="creation",
	), None))

	return out


# ----------------------------------------------------------------- Dashboards
def _dashboards() -> list[tuple[dict, str | None]]:
	MODULE = "AGS Dashboards"
	out: list[tuple[dict, str | None]] = []

	out.append((doctype(
		"AGS KPI Role", MODULE,
		[f("role", "Link", "Role", options="Role", reqd=1, in_list_view=1)],
		is_child=True,
	), None))

	out.append((doctype(
		"AGS KPI Definition", MODULE,
		[
			section("sb_head"),
			f("kpi_name", "Data", "KPI Name", reqd=1, in_list_view=1),
			f("code", "Data", "Code", reqd=1, unique=1, in_list_view=1,
			  description="Stable machine key, e.g. revenue_per_student."),
			f("category", "Select", "Category",
			  options="Finance\nCollections\nProcurement\nInventory\nHR\nAcademic\nExecutive",
			  reqd=1, in_list_view=1, search_index=1),
			column("cb_head"),
			f("unit", "Select", "Unit",
			  options="Currency\nNumber\nPercent\nRatio\nDays", default="Number"),
			f("is_active", "Check", "Active", default="1"),
			f("direction", "Select", "Good Direction",
			  options="Higher Is Better\nLower Is Better", default="Higher Is Better"),

			section("sb_calc", "Calculation"),
			f("source", "Select", "Source", options="Method\nSQL", default="Method",
			  reqd=1),
			f("method_path", "Data", "Method Path", depends_on="eval:doc.source=='Method'",
			  description="Dotted path resolved against the ags_edusmart KPI registry."),
			f("sql_query", "Code", "SQL Query", options="SQL",
			  depends_on="eval:doc.source=='SQL'",
			  description="Read-only SELECT. Placeholders: %(company)s, %(campus)s, %(from_date)s, %(to_date)s."),
			column("cb_calc"),
			f("refresh_interval_minutes", "Int", "Refresh Every (minutes)", default="60",
			  description="The scheduler recomputes at most this often; dashboards read the snapshot."),
			f("target_value", "Float", "Target"),
			f("warning_threshold", "Float", "Warning Threshold"),

			section("sb_drill", "Drilldown"),
			f("drilldown_company", "Check", "By Company", default="1"),
			f("drilldown_campus", "Check", "By Campus", default="1"),
			f("drilldown_division", "Check", "By School Division", default="0"),
			column("cb_drill"),
			f("drilldown_program", "Check", "By Grade", default="0"),
			f("drilldown_department", "Check", "By Department", default="0"),
			f("drilldown_academic_year", "Check", "By Academic Year", default="1"),

			section("sb_roles", "Visibility"),
			f("roles", "Table", "Visible To Roles", options="AGS KPI Role",
			  description="Empty means every role that can read the dashboard."),
			f("description", "Small Text", "Description"),
		],
		autoname="field:code",
		title_field="kpi_name",
		search_fields="category,code",
		permissions=[perm(SYS), perm(FIN, delete=False), readonly_perm("AGS Group Executive")],
	), None))

	out.append((doctype(
		"AGS KPI Snapshot", MODULE,
		[
			f("kpi", "Link", "KPI", options="AGS KPI Definition", reqd=1, in_list_view=1,
			  search_index=1),
			f("code", "Data", "Code", read_only=1, search_index=1),
			f("value", "Float", "Value", in_list_view=1, precision="4"),
			f("computed_on", "Datetime", "Computed On", read_only=1, in_list_view=1),
			section("sb_scope", "Scope"),
			f("company", "Link", "Company", options="Company", search_index=1),
			f("campus", "Link", "Campus", options="AGS Campus", search_index=1),
			f("school_division", "Link", "School Division", options="AGS School Division"),
			column("cb_scope"),
			f("program", "Link", "Grade", options="Program"),
			f("department", "Link", "Department", options="Department"),
			f("academic_year", "Link", "Academic Year", options="Academic Year",
			  search_index=1),
			section("sb_period", "Period"),
			f("period_start", "Date", "Period Start"),
			column("cb_period"),
			f("period_end", "Date", "Period End"),
			f("scope_key", "Data", "Scope Key", read_only=1, unique=1,
			  description="code + every dimension. One row per scope, upserted on refresh."),
		],
		autoname="hash",
		permissions=[perm(SYS), readonly_perm(FIN), readonly_perm("AGS Group Executive")],
		sort_field="computed_on",
		track_changes=False,
	), None))

	return out


# -------------------------------------------------------------- Notifications
def _notifications() -> list[tuple[dict, str | None]]:
	MODULE = "AGS Notifications"
	out: list[tuple[dict, str | None]] = []

	out.append((doctype(
		"AGS Notification Rule", MODULE,
		[
			section("sb_head"),
			f("title", "Data", "Title", reqd=1, in_list_view=1),
			f("is_active", "Check", "Active", default="1", in_list_view=1),
			f("document_type", "Link", "Document Type", options="DocType", reqd=1,
			  in_list_view=1, search_index=1),
			column("cb_head"),
			f("event", "Select", "Event",
			  options="On Submit\nOn Cancel\nOn Update\nOn Create\nValue Change",
			  reqd=1, default="On Submit", in_list_view=1),
			f("value_changed_field", "Data", "Value Changed Field",
			  depends_on="eval:doc.event=='Value Change'"),
			f("condition", "Code", "Condition", options="Python",
			  description="Optional Python expression over `doc`."),

			section("sb_to", "Recipients"),
			f("recipient_type", "Select", "Recipient Type",
			  options="Role\nDocument Owner\nField Value\nPayer Account\nEmployee\nApprover",
			  default="Role", reqd=1),
			f("recipient_role", "Link", "Role", options="Role",
			  depends_on="eval:doc.recipient_type=='Role'"),
			f("recipient_field", "Data", "Field",
			  depends_on="eval:doc.recipient_type=='Field Value'",
			  description="Fieldname holding a User, Employee or Payer Account."),
			column("cb_to"),
			f("channels", "Small Text", "Channels", default="In-App",
			  description="Comma separated: In-App, Email, SMS, WhatsApp."),
			f("priority", "Select", "Priority", options="Low\nNormal\nHigh\nUrgent",
			  default="Normal"),

			section("sb_msg", "Message"),
			f("subject", "Data", "Subject", reqd=1,
			  description="Jinja over `doc`. Example: PO {{ doc.name }} awaiting approval."),
			f("message", "Text Editor", "Message", reqd=1),
		],
		autoname="field:title",
		title_field="title",
		permissions=[perm(SYS), perm(FIN, delete=False)],
	), None))

	out.append((doctype(
		"AGS Notification Outbox", MODULE,
		[
			f("channel", "Select", "Channel", options="In-App\nEmail\nSMS\nWhatsApp",
			  reqd=1, in_list_view=1, search_index=1),
			f("recipient", "Data", "Recipient", reqd=1, in_list_view=1),
			f("recipient_user", "Link", "User", options="User"),
			f("subject", "Data", "Subject", in_list_view=1),
			f("message", "Text Editor", "Message"),
			section("sb_state"),
			f("status", "Select", "Status",
			  options="Queued\nSent\nFailed\nCancelled", default="Queued",
			  in_list_view=1, search_index=1),
			f("attempts", "Int", "Attempts", default="0"),
			f("scheduled_for", "Datetime", "Scheduled For", search_index=1),
			column("cb_state"),
			f("sent_on", "Datetime", "Sent On", read_only=1),
			f("error", "Small Text", "Error"),
			f("priority", "Select", "Priority", options="Low\nNormal\nHigh\nUrgent",
			  default="Normal"),
			section("sb_ref2"),
			f("reference_doctype", "Link", "Reference Type", options="DocType"),
			f("reference_name", "Dynamic Link", "Reference", options="reference_doctype"),
			column("cb_ref2"),
			f("notification_rule", "Link", "Rule", options="AGS Notification Rule"),
			f("dedupe_key", "Data", "Dedupe Key", unique=1, read_only=1),
		],
		autoname="hash",
		permissions=[perm(SYS), readonly_perm(FIN)],
		sort_field="creation",
		track_changes=False,
		description="Durable queue. The dispatcher drains it so a failing gateway never blocks a transaction.",
	), None))

	return out


# ------------------------------------------------------------------------- HR
def _hr() -> list[tuple[dict, str | None]]:
	MODULE = "AGS HR"
	return [(doctype(
		"AGS Document Expiry", MODULE,
		[
			section("sb_head"),
			f("employee", "Link", "Employee", options="Employee", reqd=1, in_list_view=1,
			  search_index=1),
			f("employee_name", "Data", "Name", fetch_from="employee.employee_name",
			  read_only=1, in_list_view=1),
			f("document_type", "Select", "Document Type",
			  options=("Iqama\nPassport\nNational ID\nWork Contract\nProfessional License\n"
			           "Medical Insurance\nDriving License\nOther"),
			  reqd=1, in_list_view=1, search_index=1),
			column("cb_head"),
			f("company", "Link", "Company", options="Company"),
			f("campus", "Link", "Campus", options="AGS Campus", search_index=1),
			f("document_number", "Data", "Document Number"),

			section("sb_dates", "Validity"),
			f("issue_date", "Date", "Issue Date"),
			f("expiry_date", "Date", "Expiry Date", reqd=1, in_list_view=1,
			  search_index=1),
			column("cb_dates"),
			f("reminder_days", "Int", "Remind Before (days)", default="60"),
			f("status", "Select", "Status",
			  options="Valid\nExpiring Soon\nExpired\nRenewed", default="Valid",
			  read_only=1, in_list_view=1),
			f("attachment", "Attach", "Scanned Copy"),
			f("last_reminded_on", "Date", "Last Reminded", read_only=1),
		],
		autoname="hash",
		title_field="employee_name",
		permissions=[
			perm(SYS), perm(HR), readonly_perm("Employee"),
		],
		description="Iqama and contract expiry tracking with scheduled reminders (SKILL sec. 11.2/35).",
	), None)]


# ----------------------------------------------------------------- Saudi/ZATCA
def _localization() -> list[tuple[dict, str | None]]:
	MODULE = "AGS Localization"
	out: list[tuple[dict, str | None]] = []

	out.append((doctype(
		"AGS ZATCA Settings", MODULE,
		[
			section("sb_env", "Environment"),
			f("enabled", "Check", "Enabled", default="0"),
			f("environment", "Select", "Environment",
			  options="Sandbox\nSimulation\nProduction", default="Sandbox", reqd=1),
			column("cb_env"),
			f("api_base_url", "Data", "API Base URL",
			  description="Set from the current ZATCA technical spec at deploy time; never hardcoded in code (SKILL sec. 25.1)."),

			section("sb_seller", "Seller Identity"),
			f("company", "Link", "Company", options="Company"),
			f("vat_registration_number", "Data", "VAT Registration Number"),
			f("commercial_registration", "Data", "Commercial Registration"),
			column("cb_seller"),
			f("egs_serial_number", "Data", "EGS Unit Serial Number"),
			f("invoice_type", "Data", "Invoice Type Code", default="1100"),

			section("sb_crypto", "Credentials"),
			f("csr_config", "Code", "CSR Configuration"),
			f("certificate", "Password", "Compliance Certificate"),
			column("cb_crypto"),
			f("secret", "Password", "Secret"),
			f("production_certificate", "Password", "Production Certificate"),
			f("production_secret", "Password", "Production Secret"),

			section("sb_behaviour", "Behaviour"),
			f("clear_on_submit", "Check", "Queue For Clearance On Submit", default="1"),
			f("block_on_failure", "Check", "Block Invoice If Clearance Fails", default="0",
			  description="Off by default: a gateway outage should not stop the cashier."),
			column("cb_behaviour"),
			f("max_retries", "Int", "Max Retries", default="5"),
		],
		is_single=True,
		permissions=[perm(SYS), perm(FIN)],
	), None))

	out.append((doctype(
		"AGS ZATCA Invoice Log", MODULE,
		[
			f("sales_invoice", "Link", "Sales Invoice", options="Sales Invoice", reqd=1,
			  unique=1, in_list_view=1, search_index=1),
			f("company", "Link", "Company", options="Company"),
			f("status", "Select", "Status",
			  options="Queued\nGenerated\nCleared\nReported\nFailed\nCancelled",
			  default="Queued", in_list_view=1, search_index=1),
			f("attempts", "Int", "Attempts", default="0", in_list_view=1),
			section("sb_crypto2", "Cryptographic Chain"),
			f("invoice_uuid", "Data", "UUID", read_only=1),
			f("invoice_hash", "Data", "Invoice Hash", read_only=1),
			column("cb_crypto2"),
			f("previous_hash", "Data", "Previous Invoice Hash", read_only=1,
			  description="PIH. Chains invoices so tampering is detectable."),
			f("counter_value", "Int", "Invoice Counter", read_only=1),
			section("sb_payload", "Payload"),
			f("qr_code", "Small Text", "QR (Base64 TLV)", read_only=1),
			f("signed_xml", "Code", "Signed UBL XML", read_only=1),
			column("cb_payload"),
			f("cleared_on", "Datetime", "Cleared On", read_only=1),
			f("response", "Code", "Gateway Response", read_only=1),
			f("error", "Small Text", "Error"),
		],
		autoname="hash",
		permissions=[perm(SYS), readonly_perm(FIN)],
		sort_field="creation",
		description="Immutable clearance archive, one row per invoice (SKILL sec. 25.1).",
	), None))

	return out
