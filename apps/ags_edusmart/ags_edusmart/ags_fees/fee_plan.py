# Bridges Program Enrollment (Frappe Education) to the AGS fee plan so enrolling
# a student is the single action that prices their year (SKILL sec. 14.1).
import frappe
from frappe import _
from frappe.utils import nowdate


def on_program_enrollment(doc, method=None):
	if not doc.get("ags_create_fee_plan"):
		return
	if frappe.db.exists(
		"AGS Fee Plan",
		{"student": doc.student, "academic_year": doc.academic_year, "docstatus": ("<", 2)},
	):
		return

	payer = doc.get("ags_payer_account") or frappe.db.get_value(
		"Student", doc.student, "ags_payer_account"
	)
	if not payer:
		frappe.msgprint(
			_("No payer account on student {0}; fee plan not created.").format(doc.student),
			indicator="orange",
			alert=True,
		)
		return

	structure = _find_fee_structure(doc)
	if not structure:
		frappe.msgprint(
			_("No Fee Structure matches {0} / {1}; fee plan not created.").format(
				doc.program, doc.academic_year
			),
			indicator="orange",
			alert=True,
		)
		return

	campus = doc.get("ags_campus") or frappe.db.get_value("Student", doc.student, "ags_campus")
	plan = frappe.new_doc("AGS Fee Plan")
	plan.update({
		"student": doc.student,
		"payer_account": payer,
		"academic_year": doc.academic_year,
		"academic_term": doc.academic_term,
		"program": doc.program,
		"student_category": doc.student_category,
		"campus": campus,
		"school_division": doc.get("ags_school_division"),
		"program_enrollment": doc.name,
		"fee_structure": structure,
		"company": frappe.db.get_value("Fee Structure", structure, "company"),
		"schedule_type": "By Term",
		"first_due_date": doc.enrollment_date or nowdate(),
		"auto_apply_discounts": 1,
	})
	plan.flags.ignore_permissions = True
	plan.insert()
	frappe.msgprint(
		_("Fee plan {0} created as draft.").format(plan.name), indicator="green", alert=True
	)


def _find_fee_structure(doc):
	# Most specific match first: category + term, then category, then program only.
	attempts = [
		{"program": doc.program, "academic_year": doc.academic_year,
		 "student_category": doc.student_category, "academic_term": doc.academic_term},
		{"program": doc.program, "academic_year": doc.academic_year,
		 "student_category": doc.student_category},
		{"program": doc.program, "academic_year": doc.academic_year},
	]
	for filters in attempts:
		clean = {k: v for k, v in filters.items() if v}
		clean["docstatus"] = 1
		found = frappe.get_all("Fee Structure", filters=clean, pluck="name", limit=1)
		if found:
			return found[0]
	return None
