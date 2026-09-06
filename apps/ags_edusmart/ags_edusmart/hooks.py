app_name = "ags_edusmart"
app_title = "AGS EduSmart ERP"
app_publisher = "AGS Education Group"
app_description = "School-focused ERP layer over Frappe, ERPNext, HRMS and Education"
app_email = "erp@ags.edu.sa"
app_license = "mit"
required_apps = ["erpnext", "hrms", "education"]

# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------
app_include_css = "ags_edusmart.bundle.css"
app_include_js = "ags_edusmart.bundle.js"
web_include_css = "ags_portal.bundle.css"

# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------
before_install = "ags_edusmart.setup.install.before_install"
after_install = "ags_edusmart.setup.install.after_install"
after_migrate = "ags_edusmart.setup.install.after_migrate"
before_uninstall = "ags_edusmart.setup.install.before_uninstall"

# ---------------------------------------------------------------------------
# Fixtures - exported configuration that travels with the app
# ---------------------------------------------------------------------------
fixtures = [
	{"dt": "Custom Field", "filters": [["module", "=", "AGS Core"]]},
	{"dt": "Property Setter", "filters": [["module", "=", "AGS Core"]]},
	{"dt": "AGS KPI Definition"},
	{"dt": "AGS Reminder Rule"},
	{"dt": "AGS Notification Rule"},
]

# ---------------------------------------------------------------------------
# Portal - school-friendly routes that hide ERP vocabulary (SKILL sec. 21/33)
# ---------------------------------------------------------------------------
# No catch-all route rules: the pages under www/parent and www/staff are real
# routes, and a wildcard to_route would shadow every one of them.

portal_menu_items = [
	{"title": "My Children", "route": "/parent", "role": "AGS Parent"},
	{"title": "Fees & Payments", "route": "/parent/fees", "role": "AGS Parent"},
	{"title": "My Workspace", "route": "/staff", "role": "Employee"},
]

# ---------------------------------------------------------------------------
# Permission scoping - campus / guardian / teacher aware (SKILL sec. 34)
# ---------------------------------------------------------------------------
permission_query_conditions = {
	"Sales Invoice": "ags_edusmart.ags_core.permissions.sales_invoice_query",
	"Student": "ags_edusmart.ags_core.permissions.student_query",
	"AGS Fee Plan": "ags_edusmart.ags_core.permissions.campus_scoped_query",
	"AGS Collection Case": "ags_edusmart.ags_core.permissions.campus_scoped_query",
	"AGS Payer Account": "ags_edusmart.ags_core.permissions.payer_account_query",
	"Material Request": "ags_edusmart.ags_core.permissions.campus_scoped_query",
	"AGS Department Issue": "ags_edusmart.ags_core.permissions.campus_scoped_query",
	"AGS Asset Handover": "ags_edusmart.ags_core.permissions.campus_scoped_query",
}

has_permission = {
	"AGS Payer Account": "ags_edusmart.ags_core.permissions.payer_account_has_permission",
	"Student": "ags_edusmart.ags_core.permissions.student_has_permission",
}

# ---------------------------------------------------------------------------
# Document events
# ---------------------------------------------------------------------------
doc_events = {
	"*": {
		"on_change": [
			"ags_edusmart.ags_approvals.engine.on_document_change",
			"ags_edusmart.ags_notifications.dispatcher.on_document_change",
		],
	},
	"Sales Invoice": {
		"validate": "ags_edusmart.ags_fees.invoicing.validate_school_invoice",
		"on_submit": [
			"ags_edusmart.ags_fees.invoicing.on_invoice_submit",
			"ags_edusmart.ags_localization.zatca.queue_invoice_for_clearance",
		],
		"on_cancel": "ags_edusmart.ags_fees.invoicing.on_invoice_cancel",
	},
	"Payment Entry": {
		"validate": "ags_edusmart.ags_fees.payments.validate_payment",
		"on_submit": "ags_edusmart.ags_fees.payments.on_payment_submit",
		"on_cancel": "ags_edusmart.ags_fees.payments.on_payment_cancel",
	},
	"Material Request": {
		"validate": "ags_edusmart.ags_procurement.commitments.validate_material_request",
		"on_submit": "ags_edusmart.ags_procurement.commitments.reserve_commitment",
		"on_cancel": "ags_edusmart.ags_procurement.commitments.release_commitment",
	},
	"Purchase Order": {
		"validate": "ags_edusmart.ags_procurement.commitments.validate_purchase_order",
		"on_submit": "ags_edusmart.ags_procurement.commitments.convert_commitment",
		"on_cancel": "ags_edusmart.ags_procurement.commitments.release_commitment",
	},
	"Purchase Invoice": {
		"validate": "ags_edusmart.ags_procurement.three_way_match.validate_three_way_match",
		"on_submit": "ags_edusmart.ags_procurement.commitments.settle_commitment",
	},
	"Program Enrollment": {
		"on_submit": "ags_edusmart.ags_fees.fee_plan.on_program_enrollment",
	},
	"Asset Movement": {
		"on_submit": "ags_edusmart.ags_assets.handover.sync_custodian",
	},
	"Employee Separation": {
		"validate": "ags_edusmart.ags_assets.handover.block_separation_with_open_assets",
	},
	"Employee": {
		"validate": "ags_edusmart.ags_hr.saudi.validate_saudi_employee",
	},
}

# ---------------------------------------------------------------------------
# Scheduled jobs
# ---------------------------------------------------------------------------
scheduler_events = {
	"cron": {
		# KPI refresh every 15 minutes keeps executive dashboards cheap to read
		"*/15 * * * *": ["ags_edusmart.ags_dashboards.kpi_engine.refresh_due_kpis"],
	},
	"hourly_long": [
		"ags_edusmart.ags_notifications.dispatcher.flush_outbox",
		"ags_edusmart.ags_approvals.engine.escalate_overdue",
		"ags_edusmart.ags_localization.zatca.submit_queued",
	],
	"daily_long": [
		"ags_edusmart.ags_collections.reminders.run_reminder_rules",
		"ags_edusmart.ags_collections.ageing.refresh_collection_cases",
		"ags_edusmart.ags_fees.payer.refresh_all",
		"ags_edusmart.ags_fees.invoicing.create_due_invoices",
		"ags_edusmart.ags_fees.late_fees.apply_late_fees",
		"ags_edusmart.ags_hr.expiry.notify_document_expiry",
		"ags_edusmart.ags_assets.maintenance.notify_due_maintenance",
		"ags_edusmart.ags_procurement.commitments.reconcile_commitments",
	],
	"monthly_long": [
		"ags_edusmart.ags_fees.deferred_revenue.ensure_deferred_configuration",
	],
}

# ---------------------------------------------------------------------------
# Jinja helpers used by portal + print formats
# ---------------------------------------------------------------------------
jinja = {
	"methods": [
		"ags_edusmart.utils.formatting.fmt_money",
		"ags_edusmart.utils.formatting.bidi_code",
	],
}

# ---------------------------------------------------------------------------
# Boot
# ---------------------------------------------------------------------------
extend_bootinfo = "ags_edusmart.ags_core.boot.boot_session"

# ---------------------------------------------------------------------------
# Audit - sensitive documents always keep a versioned trail (SKILL sec. 24)
# ---------------------------------------------------------------------------
AGS_AUDITED_DOCTYPES = [
	"AGS Fee Plan",
	"AGS Discount Application",
	"AGS Payer Account",
	"AGS Collection Case",
	"AGS Department Issue",
	"AGS Asset Handover",
	"Sales Invoice",
	"Payment Entry",
	"Purchase Order",
	"Purchase Invoice",
	"Journal Entry",
	"Assessment Result",
	"Student Attendance",
]
