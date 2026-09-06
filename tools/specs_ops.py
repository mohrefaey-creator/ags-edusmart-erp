"""Operational modules: Collections, Procurement, Inventory, Assets.

These wrap native ERPNext transactions rather than replacing them - a Department
Issue posts a Stock Entry, a Handover posts an Asset Movement, and a commitment
is a side ledger that never touches the GL (SKILL sec. 29/39).
"""

from doctype_builder import SYS, column, doctype, f, perm, readonly_perm, section

FIN = "AGS Finance Manager"
ACC = "AGS Accountant"
PROC = "AGS Procurement Manager"
PROC_OFF = "AGS Procurement Officer"
STORE = "AGS Storekeeper"
ASSET = "AGS Asset Manager"
COLLECTOR = "AGS Collections Officer"


def specs() -> list[tuple[dict, str | None]]:
	return _collections() + _procurement() + _inventory() + _assets()


# ---------------------------------------------------------------- Collections
def _collections() -> list[tuple[dict, str | None]]:
	MODULE = "AGS Collections"
	out: list[tuple[dict, str | None]] = []

	out.append((doctype(
		"AGS Collection Action", MODULE,
		[
			f("action_date", "Datetime", "Date", reqd=1, in_list_view=1),
			f("action_type", "Select", "Action",
			  options="Call\nEmail\nSMS\nWhatsApp\nMeeting\nLetter\nSystem Reminder",
			  reqd=1, in_list_view=1),
			f("outcome", "Select", "Outcome",
			  options="No Answer\nPromise To Pay\nDisputed\nPartial Payment\nPaid\nRefused\nInformed",
			  in_list_view=1),
			f("promised_date", "Date", "Promised Date"),
			f("promised_amount", "Currency", "Promised Amount"),
			f("notes", "Small Text", "Notes"),
			f("action_by", "Link", "By", options="User", read_only=1),
		],
		is_child=True,
	), None))

	out.append((doctype(
		"AGS Collection Case", MODULE,
		[
			section("sb_case"),
			f("naming_series", "Select", "Series", options="AGS-COL-.YYYY.-.#####",
			  default="AGS-COL-.YYYY.-.#####", reqd=1, hidden=1),
			f("payer_account", "Link", "Payer Account", options="AGS Payer Account",
			  reqd=1, in_list_view=1, search_index=1),
			f("payer_name", "Data", "Payer", fetch_from="payer_account.payer_name",
			  read_only=1, in_list_view=1),
			f("customer", "Data", "Customer", fetch_from="payer_account.customer",
			  read_only=1),
			column("cb_case"),
			f("company", "Link", "Company", options="Company", reqd=1),
			f("campus", "Link", "Campus", options="AGS Campus", search_index=1),
			f("academic_year", "Link", "Academic Year", options="Academic Year"),
			f("status", "Select", "Status",
			  options="Open\nIn Progress\nPromise To Pay\nEscalated\nResolved\nWritten Off",
			  default="Open", in_list_view=1, search_index=1),

			section("sb_amounts", "Exposure"),
			f("total_billed", "Currency", "Total Billed", read_only=1),
			f("total_paid", "Currency", "Total Paid", read_only=1),
			f("outstanding", "Currency", "Outstanding", read_only=1, in_list_view=1, bold=1),
			column("cb_amounts"),
			f("overdue", "Currency", "Overdue", read_only=1, in_list_view=1),
			f("oldest_due_date", "Date", "Oldest Due Date", read_only=1),
			f("days_overdue", "Int", "Days Overdue", read_only=1, in_list_view=1),

			section("sb_ageing", "Ageing Buckets"),
			f("bucket_current", "Currency", "Current", read_only=1),
			f("bucket_1_30", "Currency", "1-30 Days", read_only=1),
			f("bucket_31_60", "Currency", "31-60 Days", read_only=1),
			column("cb_ageing"),
			f("bucket_61_90", "Currency", "61-90 Days", read_only=1),
			f("bucket_91_120", "Currency", "91-120 Days", read_only=1),
			f("bucket_120_plus", "Currency", "Over 120 Days", read_only=1),

			section("sb_owner", "Ownership"),
			f("assigned_to", "Link", "Collector", options="User", search_index=1),
			f("next_action_date", "Date", "Next Action Date"),
			column("cb_owner"),
			f("escalation_level", "Int", "Escalation Level", default="0", read_only=1),
			f("last_refreshed_on", "Datetime", "Last Refreshed", read_only=1),

			section("sb_actions", "Contact Log"),
			f("actions", "Table", "Actions", options="AGS Collection Action"),
		],
		autoname="naming_series:",
		title_field="payer_name",
		search_fields="payer_account,status,assigned_to",
		permissions=[
			perm(SYS), perm(FIN), perm(COLLECTOR, delete=False),
			perm(ACC, delete=False), readonly_perm("AGS Principal"),
			readonly_perm("AGS Group Executive"),
		],
		description="Live receivable case per payer, refreshed nightly from the AR ledger (SKILL sec. 20).",
	), None))

	out.append((doctype(
		"AGS Reminder Rule", MODULE,
		[
			section("sb_rule"),
			f("title", "Data", "Title", reqd=1, in_list_view=1),
			f("is_active", "Check", "Active", default="1", in_list_view=1),
			f("trigger", "Select", "Trigger",
			  options="Days Before Due\nOn Due Date\nDays After Due", reqd=1,
			  in_list_view=1),
			f("days", "Int", "Days", default="7", in_list_view=1,
			  description="Ignored when the trigger is On Due Date."),
			column("cb_rule"),
			f("company", "Link", "Company", options="Company"),
			f("campus", "Link", "Campus", options="AGS Campus"),
			f("minimum_amount", "Currency", "Minimum Outstanding", default="0"),

			section("sb_channels", "Delivery"),
			f("channels", "Small Text", "Channels", default="In-App, Email",
			  description="Comma separated: In-App, Email, SMS, WhatsApp."),
			f("subject", "Data", "Subject", reqd=1),
			f("message", "Text Editor", "Message", reqd=1,
			  description="Jinja context: payer, student, invoice, amount, due_date, days."),
			column("cb_channels"),
			f("escalate_to_role", "Link", "Also Notify Role", options="Role"),
			f("escalation_level", "Int", "Sets Escalation Level", default="0"),
			f("stop_if_promise_to_pay", "Check", "Skip If Promise To Pay Recorded",
			  default="1"),
		],
		autoname="field:title",
		title_field="title",
		permissions=[perm(SYS), perm(FIN), perm(COLLECTOR, delete=False)],
	), None))

	out.append((doctype(
		"AGS Reminder Log", MODULE,
		[
			f("payer_account", "Link", "Payer Account", options="AGS Payer Account",
			  in_list_view=1, search_index=1),
			f("sales_invoice", "Link", "Invoice", options="Sales Invoice", search_index=1),
			f("reminder_rule", "Link", "Rule", options="AGS Reminder Rule", in_list_view=1),
			f("channel", "Select", "Channel", options="In-App\nEmail\nSMS\nWhatsApp",
			  in_list_view=1),
			f("sent_on", "Datetime", "Sent On", read_only=1, in_list_view=1),
			f("status", "Select", "Status", options="Sent\nFailed\nSkipped",
			  in_list_view=1),
			f("recipient", "Data", "Recipient"),
			f("amount", "Currency", "Amount"),
			f("error", "Small Text", "Error"),
			f("dedupe_key", "Data", "Dedupe Key", read_only=1, unique=1,
			  description="rule + invoice + scheduled day. Guarantees one send per rule per day."),
		],
		autoname="hash",
		permissions=[perm(SYS), readonly_perm(FIN), readonly_perm(COLLECTOR)],
		sort_field="creation",
	), None))

	return out


# ---------------------------------------------------------------- Procurement
def _procurement() -> list[tuple[dict, str | None]]:
	MODULE = "AGS Procurement"
	out: list[tuple[dict, str | None]] = []

	out.append((doctype(
		"AGS Budget Commitment", MODULE,
		[
			section("sb_src"),
			f("source_doctype", "Select", "Source Document",
			  options="Material Request\nPurchase Order", reqd=1, in_list_view=1),
			f("source_name", "Dynamic Link", "Source", options="source_doctype", reqd=1,
			  in_list_view=1, search_index=1),
			f("posting_date", "Date", "Posting Date", reqd=1, default="Today"),
			column("cb_src"),
			f("company", "Link", "Company", options="Company", reqd=1, search_index=1),
			f("fiscal_year", "Link", "Fiscal Year", options="Fiscal Year", reqd=1,
			  search_index=1),
			f("status", "Select", "Status",
			  options="Open\nConverted\nSettled\nReleased", default="Open",
			  in_list_view=1, search_index=1),

			section("sb_dims", "Dimensions"),
			f("account", "Link", "Budget Account", options="Account", reqd=1,
			  search_index=1),
			f("cost_center", "Link", "Cost Center", options="Cost Center", search_index=1),
			column("cb_dims"),
			f("campus", "Link", "Campus", options="AGS Campus"),
			f("department", "Link", "Department", options="Department"),
			f("project", "Link", "Project", options="Project"),

			section("sb_amt", "Amounts"),
			f("amount", "Currency", "Committed", reqd=1, in_list_view=1),
			column("cb_amt"),
			f("consumed_amount", "Currency", "Consumed", read_only=1, default="0"),
			f("open_amount", "Currency", "Open", read_only=1),
		],
		autoname="hash",
		permissions=[
			perm(SYS), readonly_perm(FIN), readonly_perm(PROC), readonly_perm(ACC),
		],
		description="Side ledger of budget consumed by approved requests and open orders. Never posts to the GL.",
	), None))

	out.append((doctype(
		"AGS Quotation Comparison Supplier", MODULE,
		[
			f("supplier", "Link", "Supplier", options="Supplier", reqd=1, in_list_view=1),
			f("supplier_quotation", "Link", "Quotation", options="Supplier Quotation",
			  in_list_view=1),
			f("price", "Currency", "Price", in_list_view=1),
			f("delivery_days", "Int", "Delivery (days)", in_list_view=1),
			f("warranty_months", "Int", "Warranty (months)"),
			f("payment_terms", "Data", "Payment Terms"),
			f("historical_rating", "Percent", "Historical Rating"),
			f("score", "Float", "Weighted Score", read_only=1, in_list_view=1,
			  precision="2"),
			f("is_recommended", "Check", "Recommended", read_only=1, in_list_view=1),
			f("notes", "Small Text", "Notes"),
		],
		is_child=True,
	), None))

	out.append((doctype(
		"AGS Quotation Comparison", MODULE,
		[
			section("sb_head"),
			f("naming_series", "Select", "Series", options="AGS-QC-.YYYY.-.#####",
			  default="AGS-QC-.YYYY.-.#####", reqd=1, hidden=1),
			f("title", "Data", "Title", reqd=1, in_list_view=1),
			f("material_request", "Link", "Purchase Request", options="Material Request",
			  search_index=1),
			f("request_for_quotation", "Link", "RFQ", options="Request for Quotation"),
			column("cb_head"),
			f("company", "Link", "Company", options="Company", reqd=1),
			f("campus", "Link", "Campus", options="AGS Campus", search_index=1),
			f("department", "Link", "Department", options="Department"),
			f("comparison_date", "Date", "Date", default="Today", reqd=1),

			section("sb_weights", "Scoring Weights"),
			f("weight_price", "Percent", "Price", default="50"),
			f("weight_delivery", "Percent", "Delivery", default="20"),
			column("cb_weights"),
			f("weight_warranty", "Percent", "Warranty", default="15"),
			f("weight_rating", "Percent", "Supplier Rating", default="15"),

			section("sb_suppliers", "Suppliers"),
			f("suppliers", "Table", "Suppliers", options="AGS Quotation Comparison Supplier"),

			section("sb_award", "Award"),
			f("recommended_supplier", "Link", "System Recommendation", options="Supplier",
			  read_only=1,
			  description="Weighted score only. The award below stays a human decision (SKILL sec. 8.4)."),
			f("awarded_supplier", "Link", "Awarded Supplier", options="Supplier"),
			column("cb_award"),
			f("purchase_order", "Link", "Purchase Order", options="Purchase Order",
			  read_only=1),
			f("status", "Select", "Status",
			  options="Draft\nAwaiting Award\nAwarded\nCancelled", default="Draft",
			  read_only=1, in_list_view=1),
			f("justification", "Text", "Award Justification",
			  description="Required when the award differs from the recommendation."),
		],
		autoname="naming_series:",
		title_field="title",
		permissions=[
			perm(SYS), perm(PROC), perm(PROC_OFF, delete=False),
			readonly_perm(FIN), readonly_perm("AGS Principal"),
		],
	), None))

	out.append((doctype(
		"AGS Three Way Match Exception", MODULE,
		[
			section("sb_docs"),
			f("purchase_invoice", "Link", "Supplier Invoice", options="Purchase Invoice",
			  reqd=1, in_list_view=1, search_index=1),
			f("purchase_order", "Link", "Purchase Order", options="Purchase Order"),
			f("purchase_receipt", "Link", "Goods Receipt", options="Purchase Receipt"),
			column("cb_docs"),
			f("supplier", "Link", "Supplier", options="Supplier", in_list_view=1),
			f("company", "Link", "Company", options="Company"),
			f("campus", "Link", "Campus", options="AGS Campus"),

			section("sb_exc", "Exception"),
			f("exception_type", "Select", "Type",
			  options=("Price Variance\nQuantity Variance\nTax Variance\nUnreceived Item\n"
			           "Over Billing\nDuplicate Invoice\nSupplier Mismatch"),
			  reqd=1, in_list_view=1, search_index=1),
			f("severity", "Select", "Severity", options="Blocking\nWarning",
			  default="Blocking", in_list_view=1),
			f("item_code", "Link", "Item", options="Item"),
			column("cb_exc"),
			f("expected_value", "Data", "Expected"),
			f("actual_value", "Data", "Actual"),
			f("variance_amount", "Currency", "Variance"),

			section("sb_res", "Resolution"),
			f("status", "Select", "Status", options="Open\nResolved\nOverridden",
			  default="Open", in_list_view=1, search_index=1),
			f("resolved_by", "Link", "Resolved By", options="User", read_only=1),
			column("cb_res"),
			f("resolved_on", "Datetime", "Resolved On", read_only=1),
			f("resolution_notes", "Small Text", "Resolution Notes"),
		],
		autoname="hash",
		permissions=[
			perm(SYS), perm(FIN), perm(ACC, delete=False), perm(PROC, delete=False),
		],
		description="Raised automatically when PO / GRN / Invoice disagree (SKILL sec. 8.6).",
	), None))

	return out


# ------------------------------------------------------------------ Inventory
def _inventory() -> list[tuple[dict, str | None]]:
	MODULE = "AGS Inventory"
	out: list[tuple[dict, str | None]] = []

	out.append((doctype(
		"AGS Department Issue Item", MODULE,
		[
			f("item_code", "Link", "Item", options="Item", reqd=1, in_list_view=1),
			f("item_name", "Data", "Name", fetch_from="item_code.item_name", read_only=1,
			  in_list_view=1),
			f("qty", "Float", "Quantity", reqd=1, default="1", in_list_view=1),
			f("uom", "Link", "UOM", options="UOM", reqd=1, in_list_view=1),
			f("available_qty", "Float", "Available", read_only=1),
			f("rate", "Currency", "Valuation Rate", read_only=1),
			f("amount", "Currency", "Amount", read_only=1, in_list_view=1),
			f("purpose", "Small Text", "Purpose"),
		],
		is_child=True,
	), None))

	out.append((doctype(
		"AGS Department Issue", MODULE,
		[
			section("sb_head"),
			f("naming_series", "Select", "Series", options="AGS-ISS-.YYYY.-.#####",
			  default="AGS-ISS-.YYYY.-.#####", reqd=1, hidden=1),
			f("posting_date", "Date", "Date", reqd=1, default="Today", in_list_view=1),
			f("company", "Link", "Company", options="Company", reqd=1),
			f("campus", "Link", "Campus", options="AGS Campus", reqd=1, in_list_view=1,
			  search_index=1),
			column("cb_head"),
			f("source_warehouse", "Link", "Issue From Store", options="Warehouse", reqd=1),
			f("department", "Link", "Issue To Department", options="Department", reqd=1,
			  in_list_view=1),
			f("cost_center", "Link", "Cost Center", options="Cost Center", reqd=1,
			  description="Carries the consumption cost. Defaults from the department."),

			section("sb_req", "Request"),
			f("requested_by", "Link", "Requested By", options="Employee", reqd=1),
			f("requested_by_name", "Data", "Name", fetch_from="requested_by.employee_name",
			  read_only=1),
			column("cb_req"),
			f("purpose", "Data", "Purpose", reqd=1,
			  description="e.g. Grade 9 Laboratory."),
			f("reference_note", "Small Text", "Notes"),

			section("sb_items", "Items"),
			f("items", "Table", "Items", options="AGS Department Issue Item", reqd=1),
			f("total_qty", "Float", "Total Quantity", read_only=1),
			f("total_amount", "Currency", "Total Value", read_only=1, bold=1),

			section("sb_result", "Result"),
			f("stock_entry", "Link", "Stock Entry", options="Stock Entry", read_only=1,
			  description="The native Material Issue this document posts."),
			column("cb_result"),
			f("status", "Select", "Status",
			  options="Draft\nIssued\nCancelled", default="Draft", read_only=1,
			  in_list_view=1),

			section("sb_amend"),
			f("amended_from", "Link", "Amended From", options="AGS Department Issue",
			  read_only=1, no_copy=1, print_hide=1),
		],
		autoname="naming_series:",
		is_submittable=True,
		permissions=[
			perm(SYS), perm(STORE, submit=True, cancel=True, amend=True),
			perm(PROC, submit=True), readonly_perm(FIN), readonly_perm("Employee"),
		],
		description="School-facing 'Issue Materials'. Posts a Stock Entry of type Material Issue (SKILL sec. 9.5).",
	), None))

	return out


# --------------------------------------------------------------------- Assets
def _assets() -> list[tuple[dict, str | None]]:
	MODULE = "AGS Assets"
	out: list[tuple[dict, str | None]] = []

	out.append((doctype(
		"AGS Asset Handover Item", MODULE,
		[
			f("asset", "Link", "Asset", options="Asset", reqd=1, in_list_view=1),
			f("asset_name", "Data", "Description", fetch_from="asset.asset_name",
			  read_only=1, in_list_view=1),
			f("serial_no", "Data", "Serial No"),
			f("condition", "Select", "Condition",
			  options="New\nGood\nFair\nNeeds Repair", default="Good", in_list_view=1),
			f("accessories", "Small Text", "Accessories"),
		],
		is_child=True,
	), None))

	out.append((doctype(
		"AGS Asset Handover", MODULE,
		[
			section("sb_head"),
			f("naming_series", "Select", "Series", options="AGS-AHO-.YYYY.-.#####",
			  default="AGS-AHO-.YYYY.-.#####", reqd=1, hidden=1),
			f("handover_date", "Date", "Date", reqd=1, default="Today", in_list_view=1),
			f("handover_type", "Select", "Type",
			  options="Issue To Employee\nReturn To Store\nTransfer Between Employees",
			  default="Issue To Employee", reqd=1, in_list_view=1),
			f("company", "Link", "Company", options="Company", reqd=1),
			column("cb_head"),
			f("campus", "Link", "Campus", options="AGS Campus", reqd=1, search_index=1),
			f("department", "Link", "Department", options="Department"),
			f("room", "Data", "Room / Location"),

			section("sb_parties", "Parties"),
			f("from_employee", "Link", "From Employee", options="Employee",
			  depends_on="eval:doc.handover_type!='Issue To Employee'"),
			f("from_location", "Link", "From Location", options="Location"),
			column("cb_parties"),
			f("to_employee", "Link", "To Employee", options="Employee",
			  depends_on="eval:doc.handover_type!='Return To Store'",
			  in_list_view=1, search_index=1),
			f("to_employee_name", "Data", "Name", fetch_from="to_employee.employee_name",
			  read_only=1),
			f("to_location", "Link", "To Location", options="Location",
			  depends_on="eval:doc.handover_type=='Return To Store'"),

			section("sb_assets", "Assets"),
			f("assets", "Table", "Assets", options="AGS Asset Handover Item", reqd=1),

			section("sb_ack", "Acknowledgement"),
			f("requires_acknowledgement", "Check", "Requires Employee Acknowledgement",
			  default="1"),
			f("acknowledged", "Check", "Acknowledged", read_only=1, default="0",
			  in_list_view=1),
			f("acknowledged_by", "Link", "Acknowledged By", options="User", read_only=1),
			column("cb_ack"),
			f("acknowledged_on", "Datetime", "Acknowledged On", read_only=1),
			f("return_due_date", "Date", "Return Due Date"),
			f("terms", "Text", "Terms Of Custody"),

			section("sb_result", "Result"),
			f("asset_movement", "Link", "Asset Movement", options="Asset Movement",
			  read_only=1),
			column("cb_result"),
			f("status", "Select", "Status",
			  options="Draft\nPending Acknowledgement\nActive\nReturned\nCancelled",
			  default="Draft", read_only=1, in_list_view=1, search_index=1),

			section("sb_amend"),
			f("amended_from", "Link", "Amended From", options="AGS Asset Handover",
			  read_only=1, no_copy=1, print_hide=1),
		],
		autoname="naming_series:",
		is_submittable=True,
		permissions=[
			perm(SYS), perm(ASSET, submit=True, cancel=True, amend=True),
			perm(STORE, submit=True, delete=False),
			readonly_perm("AGS HR Manager"), readonly_perm("Employee"),
		],
		description="Custody transfer with digital acknowledgement. Blocks separation while open (SKILL sec. 10.4).",
	), None))

	return out
