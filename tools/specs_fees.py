"""AGS Fees - payer accounts, the fee plan and the discount engine (SKILL sec. 17-19).

Field names on the Frappe Education side were read off the installed app, not
assumed: Fee Structure carries ``components`` of Fee Component, and each row's
category field is ``fees_category`` (plural), which is easy to get wrong.

Controllers live beside the generated JSON as ordinary modules; this file only
describes the schema.
"""

from doctype_builder import SYS, column, doctype, f, perm, readonly_perm, section

MODULE = "AGS Fees"

FIN = "AGS Finance Manager"
ACC = "AGS Accountant"

FEE_PERMS = [
	perm(SYS),
	perm(FIN, submit=True, cancel=True, amend=True),
	perm(ACC, submit=True, delete=False),
	readonly_perm("AGS Principal"),
	readonly_perm("AGS Group Executive"),
]

MASTER_PERMS = [
	perm(SYS),
	perm(FIN),
	perm(ACC, delete=False),
	readonly_perm("AGS Group Executive"),
]


def specs() -> list[tuple[dict, str | None]]:
	out: list[tuple[dict, str | None]] = []

	# ------------------------------------------------------- Payer account
	out.append((doctype(
		"AGS Payer Student", MODULE,
		[
			f("student", "Link", "Student", options="Student", reqd=1, in_list_view=1),
			f("student_name", "Data", "Name", fetch_from="student.student_name",
			  read_only=1, in_list_view=1),
			f("program", "Link", "Grade", options="Program", in_list_view=1),
			f("academic_year", "Link", "Academic Year", options="Academic Year"),
			f("relationship", "Select", "Relationship",
			  options="Father\nMother\nGuardian\nSponsor\nSelf", default="Father",
			  in_list_view=1),
			f("share_percent", "Percent", "Share %", default="100",
			  description="Portion of this student's fees billed to this payer."),
			f("is_primary", "Check", "Primary Payer", default="1"),
			f("sibling_index", "Int", "Sibling Index", read_only=1,
			  description="1 = eldest enrolled. Drives sibling discount tiers."),
			f("is_active", "Check", "Active", default="1"),
		],
		is_child=True,
	), None))

	out.append((doctype(
		"AGS Payer Account", MODULE,
		[
			section("sb_identity"),
			f("naming_series", "Select", "Series", options="AGS-PAY-.#####",
			  default="AGS-PAY-.#####", reqd=1, hidden=1),
			f("payer_name", "Data", "Payer Name", reqd=1, in_list_view=1),
			f("payer_name_ar", "Data", "Payer Name (Arabic)"),
			f("guardian", "Link", "Guardian", options="Guardian", search_index=1),
			column("cb_identity"),
			f("customer", "Link", "Customer", options="Customer", reqd=1, unique=1,
			  search_index=1,
			  description="The receivable entity. One customer per payer keeps sibling invoices on a single statement."),
			f("company", "Link", "Company", options="Company", reqd=1),
			f("campus", "Link", "Campus", options="AGS Campus", search_index=1),
			f("is_active", "Check", "Active", default="1", in_list_view=1),

			section("sb_contact", "Contact"),
			f("national_id", "Data", "National ID / Iqama"),
			f("mobile", "Data", "Mobile", options="Phone", in_list_view=1),
			column("cb_contact"),
			f("email", "Data", "Email", options="Email"),
			f("preferred_channel", "Select", "Preferred Channel",
			  options="In-App\nEmail\nSMS\nWhatsApp", default="Email"),
			f("preferred_language", "Select", "Language", options="en\nar", default="en"),

			section("sb_students", "Children"),
			f("students", "Table", "Students", options="AGS Payer Student"),

			section("sb_summary", "Financial Summary"),
			f("total_billed", "Currency", "Total Billed", read_only=1, options="currency"),
			f("total_paid", "Currency", "Total Paid", read_only=1, options="currency"),
			f("outstanding", "Currency", "Outstanding", read_only=1, options="currency",
			  in_list_view=1, bold=1),
			column("cb_summary"),
			f("overdue", "Currency", "Overdue", read_only=1, options="currency"),
			f("credit_balance", "Currency", "Credit Balance", read_only=1, options="currency"),
			f("next_due_date", "Date", "Next Due Date", read_only=1),
			f("currency", "Link", "Currency", options="Currency", default="SAR", hidden=1),
			f("summary_updated_on", "Datetime", "Summary Updated", read_only=1),
		],
		autoname="naming_series:",
		title_field="payer_name",
		search_fields="customer,mobile,national_id",
		permissions=MASTER_PERMS,
		description="One payer, many children. Consolidates sibling receivables (SKILL sec. 18).",
	), None))

	# ------------------------------------------------------- Discount engine
	out.append((doctype(
		"AGS Discount Rule Component", MODULE,
		[
			f("fees_category", "Link", "Fee Category", options="Fee Category", reqd=1,
			  in_list_view=1),
		],
		is_child=True,
	), None))

	out.append((doctype(
		"AGS Discount Rule", MODULE,
		[
			section("sb_identity"),
			f("title", "Data", "Title", reqd=1, in_list_view=1),
			f("discount_type", "Select", "Discount Type",
			  options=("Sibling Discount\nStaff Child Discount\nEarly Payment Discount\n"
			           "Scholarship\nCorporate Agreement\nAcademic Discount\n"
			           "Promotional Discount\nPrincipal Exception\nFinancial Aid"),
			  reqd=1, in_list_view=1, search_index=1),
			f("is_active", "Check", "Active", default="1", in_list_view=1),
			column("cb_identity"),
			f("priority", "Int", "Priority", default="10",
			  description="Lower runs first. Order matters once discounts stack."),
			f("stackable", "Check", "Stackable With Other Discounts", default="1",
			  description="If unticked, this rule wins alone and suppresses the rest."),
			f("requires_approval", "Check", "Always Requires Approval", default="0"),

			section("sb_calc", "Calculation"),
			f("calculation", "Select", "Calculation", options="Percent\nFixed Amount",
			  default="Percent", reqd=1),
			f("value", "Float", "Value", reqd=1, in_list_view=1,
			  description="Percent of the eligible base, or a flat amount."),
			column("cb_calc"),
			f("max_amount", "Currency", "Maximum Amount",
			  description="Caps the computed discount. Zero means uncapped."),

			section("sb_eligibility", "Component Eligibility"),
			f("apply_to_all_components", "Check", "Apply To All Fee Components", default="0",
			  description="Otherwise only the categories listed below are discounted (SKILL sec. 17.6)."),
			f("components", "Table", "Eligible Fee Categories",
			  options="AGS Discount Rule Component",
			  depends_on="eval:!doc.apply_to_all_components"),

			section("sb_conditions", "Conditions"),
			f("company", "Link", "Company", options="Company"),
			f("campus", "Link", "Campus", options="AGS Campus"),
			f("academic_year", "Link", "Academic Year", options="Academic Year"),
			column("cb_conditions"),
			f("program", "Link", "Grade", options="Program"),
			f("student_category", "Link", "Student Category", options="Student Category"),
			f("division_type", "Select", "Division Type",
			  options="\nKindergarten\nPrimary\nMiddle\nSecondary\nSenior"),

			section("sb_sibling", "Sibling Tier",
			        depends_on="eval:doc.discount_type=='Sibling Discount'"),
			f("sibling_index_from", "Int", "Applies From Child #", default="2",
			  description="2 = second child. Matches the tier table in SKILL sec. 17.6."),
			column("cb_sibling"),
			f("sibling_index_to", "Int", "Applies To Child #", default="0",
			  description="Zero means no upper bound."),

			section("sb_validity", "Validity"),
			f("valid_from", "Date", "Valid From"),
			column("cb_validity"),
			f("valid_to", "Date", "Valid To"),
			f("pay_before_date", "Date", "Pay Before",
			  depends_on="eval:doc.discount_type=='Early Payment Discount'",
			  description="Early payment discount only holds if settled by this date."),

			section("sb_desc"),
			f("description", "Small Text", "Description"),
		],
		autoname="field:title",
		title_field="title",
		search_fields="discount_type,campus,academic_year",
		permissions=MASTER_PERMS,
	), None))

	out.append((doctype(
		"AGS Scholarship", MODULE,
		[
			section("sb_identity"),
			f("scholarship_name", "Data", "Scholarship Name", reqd=1, in_list_view=1),
			f("sponsor", "Data", "Sponsor"),
			f("scholarship_type", "Select", "Type",
			  options="Full\nPartial\nMerit\nNeed Based\nCorporate\nStaff",
			  default="Partial", in_list_view=1),
			column("cb_identity"),
			f("company", "Link", "Company", options="Company", reqd=1),
			f("campus", "Link", "Campus", options="AGS Campus"),
			f("academic_year", "Link", "Academic Year", options="Academic Year", reqd=1),
			f("is_active", "Check", "Active", default="1"),

			section("sb_coverage", "Coverage"),
			f("calculation", "Select", "Calculation", options="Percent\nFixed Amount",
			  default="Percent", reqd=1),
			f("value", "Float", "Value", reqd=1),
			column("cb_coverage"),
			f("max_amount_per_student", "Currency", "Maximum Per Student"),
			f("apply_to_all_components", "Check", "Apply To All Fee Components", default="0"),
			f("components", "Table", "Eligible Fee Categories",
			  options="AGS Discount Rule Component",
			  depends_on="eval:!doc.apply_to_all_components"),

			section("sb_budget", "Budget"),
			f("budget_amount", "Currency", "Budget Amount"),
			column("cb_budget"),
			f("allocated_amount", "Currency", "Allocated", read_only=1),
			f("remaining_amount", "Currency", "Remaining", read_only=1),

			section("sb_validity", "Validity"),
			f("valid_from", "Date", "Valid From"),
			column("cb_validity2"),
			f("valid_to", "Date", "Valid To"),
		],
		autoname="field:scholarship_name",
		title_field="scholarship_name",
		permissions=MASTER_PERMS,
	), None))

	# ------------------------------------------------------------- Fee plan
	out.append((doctype(
		"AGS Fee Plan Component", MODULE,
		[
			f("fees_category", "Link", "Fee Category", options="Fee Category", reqd=1,
			  in_list_view=1),
			f("item", "Link", "Item", options="Item",
			  description="Maps the fee to its revenue account (SKILL sec. 17.1)."),
			f("description", "Small Text", "Description"),
			f("gross_amount", "Currency", "Gross", reqd=1, in_list_view=1),
			f("discount_amount", "Currency", "Discount", read_only=1, in_list_view=1),
			f("net_amount", "Currency", "Net", read_only=1, in_list_view=1),
			f("is_discountable", "Check", "Discountable", default="1"),
			f("income_account", "Link", "Income Account", options="Account"),
		],
		is_child=True,
	), None))

	out.append((doctype(
		"AGS Fee Plan Discount", MODULE,
		[
			# An approved AGS Discount Application appends here after submit.
			f("discount_rule", "Link", "Discount Rule", options="AGS Discount Rule",
			  in_list_view=1, allow_on_submit=1),
			f("scholarship", "Link", "Scholarship", options="AGS Scholarship",
			  allow_on_submit=1),
			f("discount_type", "Data", "Type", read_only=1, in_list_view=1,
			  allow_on_submit=1),
			f("calculation", "Data", "Calculation", read_only=1, allow_on_submit=1),
			f("value", "Float", "Value", read_only=1, allow_on_submit=1),
			f("discount_amount", "Currency", "Amount", read_only=1, in_list_view=1,
			  allow_on_submit=1),
			f("status", "Select", "Status",
			  options="Applied\nPending Approval\nRejected", default="Applied",
			  in_list_view=1, allow_on_submit=1),
			f("approval_reference", "Link", "Approval",
			  options="AGS Discount Application", read_only=1, allow_on_submit=1),
			f("notes", "Small Text", "Notes", allow_on_submit=1),
		],
		is_child=True,
	), None))

	out.append((doctype(
		"AGS Fee Plan Installment", MODULE,
		[
			# Every field here is written after submit - by invoicing, by payment
			# reconciliation, or by an approved discount reshaping the schedule.
			f("installment_no", "Int", "#", reqd=1, in_list_view=1, columns=1),
			f("label", "Data", "Label", in_list_view=1, columns=2, allow_on_submit=1),
			f("due_date", "Date", "Due Date", reqd=1, in_list_view=1, columns=2,
			  allow_on_submit=1),
			f("amount", "Currency", "Amount", reqd=1, in_list_view=1, columns=2,
			  allow_on_submit=1),
			f("sales_invoice", "Link", "Invoice", options="Sales Invoice", read_only=1,
			  in_list_view=1, columns=2, allow_on_submit=1),
			f("paid_amount", "Currency", "Paid", read_only=1, allow_on_submit=1),
			f("outstanding_amount", "Currency", "Outstanding", read_only=1,
			  allow_on_submit=1),
			f("status", "Select", "Status",
			  options="Pending\nInvoiced\nPartially Paid\nPaid\nOverdue\nCancelled",
			  default="Pending", in_list_view=1, columns=2, allow_on_submit=1),
		],
		is_child=True,
	), None))

	out.append((doctype(
		"AGS Fee Plan", MODULE,
		[
			section("sb_student"),
			f("naming_series", "Select", "Series", options="AGS-FP-.YYYY.-.#####",
			  default="AGS-FP-.YYYY.-.#####", reqd=1, hidden=1),
			f("student", "Link", "Student", options="Student", reqd=1, in_list_view=1,
			  search_index=1),
			f("student_name", "Data", "Student Name", fetch_from="student.student_name",
			  read_only=1, in_list_view=1),
			f("payer_account", "Link", "Payer Account", options="AGS Payer Account",
			  reqd=1, search_index=1),
			f("customer", "Data", "Customer", fetch_from="payer_account.customer",
			  read_only=1),
			column("cb_student"),
			f("company", "Link", "Company", options="Company", reqd=1),
			f("campus", "Link", "Campus", options="AGS Campus", search_index=1),
			f("school_division", "Link", "School Division", options="AGS School Division"),
			f("status", "Select", "Status",
			  options="Draft\nActive\nCompleted\nOn Hold\nCancelled", default="Draft",
			  read_only=1, in_list_view=1, allow_on_submit=1),

			section("sb_academic", "Academic"),
			f("academic_year", "Link", "Academic Year", options="Academic Year", reqd=1,
			  in_list_view=1, search_index=1),
			f("academic_term", "Link", "Academic Term", options="Academic Term"),
			column("cb_academic"),
			f("program", "Link", "Grade", options="Program", reqd=1),
			f("student_category", "Link", "Student Category", options="Student Category"),
			f("program_enrollment", "Link", "Program Enrollment",
			  options="Program Enrollment", read_only=1),

			section("sb_structure", "Fee Structure"),
			f("fee_structure", "Link", "Fee Structure", options="Fee Structure",
			  description="Pulls the component lines. Amounts stay editable per student."),
			f("components", "Table", "Fee Components", options="AGS Fee Plan Component"),

			section("sb_discounts", "Discounts"),
			f("auto_apply_discounts", "Check", "Auto-Apply Matching Discount Rules",
			  default="1"),
			f("discounts", "Table", "Discounts", options="AGS Fee Plan Discount",
			  allow_on_submit=1),

			section("sb_schedule", "Payment Schedule"),
			f("schedule_type", "Select", "Schedule Type",
			  options="Annual\nBy Term\nQuarterly\nMonthly\nCustom", default="By Term",
			  reqd=1),
			f("number_of_installments", "Int", "Number of Installments", default="3",
			  depends_on="eval:doc.schedule_type=='Custom'"),
			column("cb_schedule"),
			f("first_due_date", "Date", "First Due Date", reqd=1),
			f("installment_gap_days", "Int", "Custom Gap (days)", default="30",
			  depends_on="eval:doc.schedule_type=='Custom'"),
			f("installments", "Table", "Installments", options="AGS Fee Plan Installment",
			  allow_on_submit=1),

			section("sb_totals", "Totals"),
			f("gross_total", "Currency", "Gross Total", read_only=1, options="currency",
			  allow_on_submit=1),
			f("discount_total", "Currency", "Discount Total", read_only=1,
			  options="currency", allow_on_submit=1),
			f("net_total", "Currency", "Net Payable", read_only=1, options="currency",
			  bold=1, in_list_view=1, allow_on_submit=1),
			column("cb_totals"),
			f("invoiced_total", "Currency", "Invoiced", read_only=1, options="currency",
			  allow_on_submit=1),
			f("paid_total", "Currency", "Paid", read_only=1, options="currency",
			  allow_on_submit=1),
			f("outstanding_total", "Currency", "Outstanding", read_only=1,
			  options="currency", allow_on_submit=1),
			f("currency", "Link", "Currency", options="Currency", default="SAR", hidden=1),

			section("sb_accounting", "Accounting"),
			f("cost_center", "Link", "Cost Center", options="Cost Center"),
			column("cb_accounting"),
			f("receivable_account", "Link", "Receivable Account", options="Account"),

			section("sb_amend"),
			f("amended_from", "Link", "Amended From", options="AGS Fee Plan",
			  read_only=1, no_copy=1, print_hide=1),
		],
		autoname="naming_series:",
		title_field="student_name",
		search_fields="student,payer_account,academic_year",
		is_submittable=True,
		permissions=FEE_PERMS,
		description="Student-specific priced plan: structure + discounts + installments (SKILL sec. 17.5).",
	), None))

	# --------------------------------------------------- Discount application
	out.append((doctype(
		"AGS Discount Application", MODULE,
		[
			section("sb_request"),
			f("naming_series", "Select", "Series", options="AGS-DISC-.YYYY.-.#####",
			  default="AGS-DISC-.YYYY.-.#####", reqd=1, hidden=1),
			f("fee_plan", "Link", "Fee Plan", options="AGS Fee Plan", reqd=1,
			  in_list_view=1, search_index=1),
			f("student", "Data", "Student", fetch_from="fee_plan.student", read_only=1,
			  in_list_view=1),
			f("student_name", "Data", "Student Name", fetch_from="fee_plan.student_name",
			  read_only=1),
			column("cb_request"),
			f("campus", "Data", "Campus", fetch_from="fee_plan.campus", read_only=1),
			f("academic_year", "Data", "Academic Year", fetch_from="fee_plan.academic_year",
			  read_only=1),
			f("company", "Data", "Company", fetch_from="fee_plan.company", read_only=1),

			section("sb_discount", "Requested Discount"),
			f("discount_rule", "Link", "Discount Rule", options="AGS Discount Rule",
			  description="Optional. Leave blank for a one-off exception."),
			f("discount_type", "Select", "Discount Type",
			  options=("Sibling Discount\nStaff Child Discount\nEarly Payment Discount\n"
			           "Scholarship\nCorporate Agreement\nAcademic Discount\n"
			           "Promotional Discount\nPrincipal Exception\nFinancial Aid"),
			  reqd=1),
			f("calculation", "Select", "Calculation", options="Percent\nFixed Amount",
			  default="Percent", reqd=1),
			f("value", "Float", "Value", reqd=1),
			column("cb_discount"),
			f("current_net", "Currency", "Current Net", read_only=1),
			f("discount_amount", "Currency", "Discount Amount", read_only=1, in_list_view=1),
			f("proposed_net", "Currency", "Proposed Net", read_only=1),
			f("discount_percent", "Percent", "Effective Discount %", read_only=1,
			  in_list_view=1,
			  description="Drives which approval tier applies (SKILL sec. 17.7)."),

			section("sb_justification", "Justification"),
			f("reason", "Text", "Reason", reqd=1),
			f("supporting_document", "Attach", "Supporting Document"),

			section("sb_approval", "Approval"),
			f("approval_status", "Select", "Approval Status",
			  options="Draft\nPending\nApproved\nRejected", default="Draft",
			  read_only=1, in_list_view=1),
			f("required_role", "Data", "Required Approver Role", read_only=1),
			column("cb_approval"),
			f("approved_by", "Link", "Approved By", options="User", read_only=1),
			f("approved_on", "Datetime", "Approved On", read_only=1),
			f("applied", "Check", "Applied To Fee Plan", read_only=1, default="0"),
			f("rejection_reason", "Small Text", "Rejection Reason", read_only=1),

			section("sb_amend2"),
			f("amended_from", "Link", "Amended From", options="AGS Discount Application",
			  read_only=1, no_copy=1, print_hide=1),
		],
		autoname="naming_series:",
		title_field="student_name",
		is_submittable=True,
		permissions=[
			perm(SYS),
			perm(FIN, submit=True, cancel=True, amend=True),
			perm(ACC, submit=True, delete=False),
			perm("AGS Principal", submit=True, create=False, delete=False),
			readonly_perm("AGS Group Executive"),
		],
		description="Audited discount request with before/after values (SKILL sec. 17.7).",
	), None))

	# ----------------------------------------------------------- Fee waiver
	out.append((doctype(
		"AGS Fee Waiver", MODULE,
		[
			section("sb_waiver"),
			f("naming_series", "Select", "Series", options="AGS-WVR-.YYYY.-.#####",
			  default="AGS-WVR-.YYYY.-.#####", reqd=1, hidden=1),
			f("payer_account", "Link", "Payer Account", options="AGS Payer Account",
			  reqd=1, in_list_view=1),
			f("student", "Link", "Student", options="Student", in_list_view=1),
			f("sales_invoice", "Link", "Invoice", options="Sales Invoice", reqd=1,
			  description="The waiver posts a credit note against this invoice."),
			column("cb_waiver"),
			f("company", "Link", "Company", options="Company", reqd=1),
			f("campus", "Link", "Campus", options="AGS Campus"),
			f("posting_date", "Date", "Posting Date", reqd=1, default="Today"),
			f("waiver_amount", "Currency", "Waiver Amount", reqd=1, in_list_view=1),

			section("sb_reason", "Justification"),
			f("reason", "Text", "Reason", reqd=1),
			f("supporting_document", "Attach", "Supporting Document"),

			section("sb_result", "Result"),
			f("credit_note", "Link", "Credit Note", options="Sales Invoice", read_only=1),
			column("cb_result"),
			f("approval_status", "Select", "Approval Status",
			  options="Draft\nPending\nApproved\nRejected", default="Draft", read_only=1),

			section("sb_amend3"),
			f("amended_from", "Link", "Amended From", options="AGS Fee Waiver",
			  read_only=1, no_copy=1, print_hide=1),
		],
		autoname="naming_series:",
		is_submittable=True,
		permissions=[
			perm(SYS),
			perm(FIN, submit=True, cancel=True, amend=True),
			readonly_perm("AGS Accountant"),
		],
	), None))

	return out
