"""Custom fields that extend native masters instead of replacing them.

Deliberately narrow. Campus / division / academic year reach the accounting
documents through the Accounting Dimension mechanism (which creates its own
custom fields), so re-declaring them here would collide. What is left is the
school and Saudi payload that no dimension provides: Arabic names, Iqama data,
medical flags, custody location, and the procurement justification trail.

``create_custom_fields`` skips a field that already exists, so this is safe to
re-run on every migrate.
"""

from __future__ import annotations

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

MODULE = "AGS Core"


def _fields() -> dict[str, list[dict]]:
	return {
		# ------------------------------------------------------------ Student
		"Student": [
			{"fieldname": "ags_sb", "fieldtype": "Section Break", "label": "AGS School Details",
			 "insert_after": "student_name"},
			{"fieldname": "ags_student_name_ar", "fieldtype": "Data", "label": "Name (Arabic)",
			 "insert_after": "ags_sb"},
			{"fieldname": "ags_national_id", "fieldtype": "Data", "label": "National ID / Iqama",
			 "insert_after": "ags_student_name_ar"},
			{"fieldname": "ags_campus", "fieldtype": "Link", "options": "AGS Campus",
			 "label": "Campus", "insert_after": "ags_national_id", "search_index": 1},
			{"fieldname": "ags_school_division", "fieldtype": "Link",
			 "options": "AGS School Division", "label": "School Division",
			 "insert_after": "ags_campus"},
			{"fieldname": "ags_cb", "fieldtype": "Column Break", "insert_after": "ags_school_division"},
			{"fieldname": "ags_payer_account", "fieldtype": "Link", "options": "AGS Payer Account",
			 "label": "Payer Account", "insert_after": "ags_cb", "search_index": 1,
			 "description": "Financial payer. Kept separate from the student identity (SKILL sec. 13.4)."},
			{"fieldname": "ags_transportation_status", "fieldtype": "Select",
			 "label": "Transportation", "options": "\nNot Applicable\nOne Way\nTwo Way",
			 "insert_after": "ags_payer_account"},
			{"fieldname": "ags_previous_school", "fieldtype": "Data", "label": "Previous School",
			 "insert_after": "ags_transportation_status"},

			{"fieldname": "ags_health_sb", "fieldtype": "Section Break", "label": "Health & Support",
			 "insert_after": "ags_previous_school", "collapsible": 1},
			{"fieldname": "ags_medical_alert", "fieldtype": "Small Text", "label": "Medical Alert",
			 "insert_after": "ags_health_sb"},
			{"fieldname": "ags_allergy", "fieldtype": "Small Text", "label": "Allergies",
			 "insert_after": "ags_medical_alert"},
			{"fieldname": "ags_health_cb", "fieldtype": "Column Break", "insert_after": "ags_allergy"},
			{"fieldname": "ags_special_needs", "fieldtype": "Check", "label": "Special Needs",
			 "insert_after": "ags_health_cb"},
			{"fieldname": "ags_special_needs_note", "fieldtype": "Small Text",
			 "label": "Support Notes", "depends_on": "ags_special_needs",
			 "insert_after": "ags_special_needs"},
		],

		# ----------------------------------------------------------- Guardian
		"Guardian": [
			{"fieldname": "ags_payer_account", "fieldtype": "Link",
			 "options": "AGS Payer Account", "label": "Payer Account",
			 "insert_after": "guardian_name", "search_index": 1},
			{"fieldname": "ags_national_id", "fieldtype": "Data", "label": "National ID / Iqama",
			 "insert_after": "ags_payer_account"},
			{"fieldname": "ags_preferred_language", "fieldtype": "Select", "label": "Language",
			 "options": "en\nar", "default": "en", "insert_after": "ags_national_id"},
		],

		# ----------------------------------------------------------- Employee
		"Employee": [
			{"fieldname": "ags_saudi_sb", "fieldtype": "Section Break",
			 "label": "AGS / Saudi Details", "insert_after": "company", "collapsible": 1},
			{"fieldname": "ags_employee_name_ar", "fieldtype": "Data", "label": "Name (Arabic)",
			 "insert_after": "ags_saudi_sb"},
			{"fieldname": "ags_campus", "fieldtype": "Link", "options": "AGS Campus",
			 "label": "Campus", "insert_after": "ags_employee_name_ar", "search_index": 1},
			{"fieldname": "ags_school_division", "fieldtype": "Link",
			 "options": "AGS School Division", "label": "School Division",
			 "insert_after": "ags_campus"},
			{"fieldname": "ags_iqama_number", "fieldtype": "Data", "label": "Iqama / National ID",
			 "insert_after": "ags_school_division"},
			{"fieldname": "ags_saudi_cb", "fieldtype": "Column Break",
			 "insert_after": "ags_iqama_number"},
			{"fieldname": "ags_iqama_expiry", "fieldtype": "Date", "label": "Iqama Expiry",
			 "insert_after": "ags_saudi_cb"},
			{"fieldname": "ags_passport_expiry", "fieldtype": "Date", "label": "Passport Expiry",
			 "insert_after": "ags_iqama_expiry"},
			{"fieldname": "ags_gosi_number", "fieldtype": "Data", "label": "GOSI Number",
			 "insert_after": "ags_passport_expiry"},
			{"fieldname": "ags_professional_license", "fieldtype": "Data",
			 "label": "Professional License", "insert_after": "ags_gosi_number"},
			{"fieldname": "ags_license_expiry", "fieldtype": "Date", "label": "License Expiry",
			 "insert_after": "ags_professional_license"},
		],

		# --------------------------------------------------------------- Item
		"Item": [
			{"fieldname": "ags_sb", "fieldtype": "Section Break", "label": "AGS School Item",
			 "insert_after": "item_group", "collapsible": 1},
			{"fieldname": "ags_school_category", "fieldtype": "Select",
			 "label": "School Item Category",
			 "options": ("\nStationery\nTextbooks\nWorkbooks\nUniform\nIT Equipment\n"
			             "Cleaning\nMaintenance Parts\nScience Supplies\nSports\n"
			             "Furniture\nService\nFee Component"),
			 "insert_after": "ags_sb"},
			{"fieldname": "ags_issue_unit", "fieldtype": "Link", "options": "UOM",
			 "label": "Issue Unit", "insert_after": "ags_school_category"},
			{"fieldname": "ags_pack_size", "fieldtype": "Float", "label": "Pack Size",
			 "insert_after": "ags_issue_unit"},
			{"fieldname": "ags_item_cb", "fieldtype": "Column Break", "insert_after": "ags_pack_size"},
			{"fieldname": "ags_is_returnable", "fieldtype": "Check", "label": "Returnable",
			 "insert_after": "ags_item_cb"},
			{"fieldname": "ags_student_issued", "fieldtype": "Check", "label": "Issued To Students",
			 "insert_after": "ags_is_returnable"},
			{"fieldname": "ags_employee_issued", "fieldtype": "Check", "label": "Issued To Employees",
			 "insert_after": "ags_student_issued"},
		],

		# -------------------------------------------------------------- Asset
		"Asset": [
			{"fieldname": "ags_sb", "fieldtype": "Section Break", "label": "AGS Location & Custody",
			 "insert_after": "location", "collapsible": 1},
			{"fieldname": "ags_campus", "fieldtype": "Link", "options": "AGS Campus",
			 "label": "Campus", "insert_after": "ags_sb", "search_index": 1},
			{"fieldname": "ags_building", "fieldtype": "Data", "label": "Building",
			 "insert_after": "ags_campus"},
			{"fieldname": "ags_asset_cb", "fieldtype": "Column Break", "insert_after": "ags_building"},
			{"fieldname": "ags_floor", "fieldtype": "Data", "label": "Floor",
			 "insert_after": "ags_asset_cb"},
			{"fieldname": "ags_room", "fieldtype": "Data", "label": "Room",
			 "insert_after": "ags_floor"},
			{"fieldname": "ags_condition", "fieldtype": "Select", "label": "Condition",
			 "options": "\nNew\nGood\nFair\nNeeds Repair\nOut Of Service",
			 "insert_after": "ags_room"},
		],

		# --------------------------------------------- Purchase request (MR)
		# Material Request is not on ERPNext's accounting-dimension list, so no
		# `campus` field reaches it - it needs its own.
		"Material Request": [
			{"fieldname": "ags_sb", "fieldtype": "Section Break", "label": "AGS Justification",
			 "insert_after": "schedule_date"},
			{"fieldname": "ags_campus", "fieldtype": "Link", "options": "AGS Campus",
			 "label": "Campus", "insert_after": "ags_sb", "search_index": 1},
			{"fieldname": "ags_purpose", "fieldtype": "Data", "label": "Purpose",
			 "insert_after": "ags_sb"},
			{"fieldname": "ags_justification", "fieldtype": "Small Text", "label": "Justification",
			 "insert_after": "ags_purpose"},
			{"fieldname": "ags_mr_cb", "fieldtype": "Column Break",
			 "insert_after": "ags_justification"},
			{"fieldname": "ags_budget_account", "fieldtype": "Link", "options": "Account",
			 "label": "Budget Account", "insert_after": "ags_mr_cb"},
			{"fieldname": "ags_budget_available", "fieldtype": "Currency",
			 "label": "Budget Available", "read_only": 1, "insert_after": "ags_budget_account",
			 "description": "Original budget less actuals, open orders and approved requests."},
			{"fieldname": "ags_estimated_total", "fieldtype": "Currency",
			 "label": "Estimated Total", "read_only": 1,
			 "insert_after": "ags_budget_available"},
			{"fieldname": "ags_approval_status", "fieldtype": "Select",
			 "label": "AGS Approval", "options": "\nPending\nApproved\nRejected",
			 "read_only": 1, "allow_on_submit": 1, "in_standard_filter": 1,
			 "insert_after": "ags_estimated_total",
			 "description": "Set by the AGS approval matrix. A Purchase Order cannot be raised until this reads Approved."},
		],

		# ----------------------------------------------------- Purchase Order
		"Purchase Order": [
			{"fieldname": "ags_approval_status", "fieldtype": "Select",
			 "label": "AGS Approval", "options": "\nPending\nApproved\nRejected",
			 "read_only": 1, "allow_on_submit": 1, "in_standard_filter": 1,
			 "insert_after": "status"},
		],

		# ------------------------------------------------- Program enrollment
		"Program Enrollment": [
			{"fieldname": "ags_campus", "fieldtype": "Link", "options": "AGS Campus",
			 "label": "Campus", "insert_after": "academic_term", "search_index": 1},
			{"fieldname": "ags_school_division", "fieldtype": "Link",
			 "options": "AGS School Division", "label": "School Division",
			 "insert_after": "ags_campus"},
			{"fieldname": "ags_payer_account", "fieldtype": "Link",
			 "options": "AGS Payer Account", "label": "Payer Account",
			 "insert_after": "ags_school_division",
			 "description": "Used to build the fee plan on enrollment."},
			{"fieldname": "ags_create_fee_plan", "fieldtype": "Check",
			 "label": "Create Fee Plan On Submit", "default": "1",
			 "insert_after": "ags_payer_account"},
		],

		# Budget deliberately has no AGS fields here: registering AGS Campus and
		# AGS School Division as Accounting Dimensions already creates `campus`
		# and `school_division` on it, and ERPNext's budget validation selects
		# those columns by name. A parallel ags_campus would be a second, unread
		# copy of the same fact.

		# ---------------------------------------------------- Fee integration
		"Sales Invoice": [
			{"fieldname": "ags_fee_sb", "fieldtype": "Section Break", "label": "AGS School Fees",
			 "insert_after": "customer_name", "collapsible": 1},
			{"fieldname": "ags_student", "fieldtype": "Link", "options": "Student",
			 "label": "Student", "insert_after": "ags_fee_sb", "search_index": 1},
			{"fieldname": "ags_fee_plan", "fieldtype": "Link", "options": "AGS Fee Plan",
			 "label": "Fee Plan", "insert_after": "ags_student", "search_index": 1},
			{"fieldname": "ags_fee_cb", "fieldtype": "Column Break", "insert_after": "ags_fee_plan"},
			{"fieldname": "ags_payer_account", "fieldtype": "Link",
			 "options": "AGS Payer Account", "label": "Payer Account",
			 "insert_after": "ags_fee_cb", "search_index": 1},
			{"fieldname": "ags_installment_no", "fieldtype": "Int", "label": "Installment #",
			 "insert_after": "ags_payer_account"},
			{"fieldname": "ags_late_fee_against", "fieldtype": "Link", "options": "Sales Invoice",
			 "label": "Late Fee Against", "insert_after": "ags_installment_no", "read_only": 1,
			 "search_index": 1,
			 "description": "Set on a generated late-fee invoice. Guarantees one late fee per overdue invoice."},
		],
	}


def create_ags_custom_fields() -> None:
	fields = _fields()
	for rows in fields.values():
		for row in rows:
			row.setdefault("module", MODULE)
	create_custom_fields(fields, ignore_validate=True)


def execute() -> None:
	create_ags_custom_fields()
