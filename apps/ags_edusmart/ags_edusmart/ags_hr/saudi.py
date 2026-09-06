# Saudi HR localisation (SKILL sec. 11/25).
#
# Implemented as validation + configuration over Frappe HR rather than branching
# logic inside payroll: SKILL sec. 39.15 requires localisation to be a
# configuration layer, so the rules below are checks and defaults, never a
# parallel payroll calculation.
import re

import frappe
from frappe import _
from frappe.utils import getdate

# Saudi national IDs start with 1, resident Iqama numbers with 2; both are 10 digits.
_ID_RE = re.compile(r"^[12]\d{9}$")


def validate_saudi_employee(doc, method=None):
	if not doc.meta.has_field("ags_iqama_number"):
		return

	_validate_id(doc)
	_validate_expiries(doc)
	_sync_expiry_tracker(doc)


def _validate_id(doc):
	value = (doc.get("ags_iqama_number") or "").strip()
	if not value:
		return
	if not _ID_RE.match(value):
		frappe.throw(
			_("Iqama / National ID must be 10 digits starting with 1 (citizen) "
			  "or 2 (resident). Got {0}.").format(value),
			title=_("Invalid Identifier"),
		)
	duplicate = frappe.db.get_value(
		"Employee",
		{"ags_iqama_number": value, "name": ("!=", doc.name)},
		"name",
	)
	if duplicate:
		frappe.throw(
			_("Iqama / National ID {0} already belongs to employee {1}.").format(
				value, duplicate
			)
		)


def _validate_expiries(doc):
	joining = doc.get("date_of_joining")
	for field, label in (
		("ags_iqama_expiry", _("Iqama expiry")),
		("ags_passport_expiry", _("Passport expiry")),
		("ags_license_expiry", _("Professional license expiry")),
	):
		value = doc.get(field)
		if value and joining and getdate(value) < getdate(joining):
			frappe.throw(_("{0} cannot be before the joining date.").format(label))


# Employee fields that mirror into AGS Document Expiry so one scheduled job
# covers every tracked document.
_TRACKED = (
	("ags_iqama_expiry", "Iqama", "ags_iqama_number"),
	("ags_passport_expiry", "Passport", None),
	("ags_license_expiry", "Professional License", "ags_professional_license"),
	("contract_end_date", "Work Contract", None),
)


def _sync_expiry_tracker(doc):
	for field, document_type, number_field in _TRACKED:
		expiry = doc.get(field)
		existing = frappe.db.get_value(
			"AGS Document Expiry",
			{"employee": doc.name, "document_type": document_type},
			"name",
		)
		if not expiry:
			if existing:
				frappe.delete_doc(
					"AGS Document Expiry", existing, force=True, ignore_permissions=True
				)
			continue

		values = {
			"employee": doc.name,
			"document_type": document_type,
			"document_number": doc.get(number_field) if number_field else None,
			"expiry_date": expiry,
			"company": doc.get("company"),
			"campus": doc.get("ags_campus"),
		}
		if existing:
			frappe.db.set_value(
				"AGS Document Expiry", existing, values, update_modified=False
			)
		else:
			row = frappe.get_doc({"doctype": "AGS Document Expiry", **values})
			row.flags.ignore_permissions = True
			row.insert()


GOSI_COMPONENTS = (
	# (name, type, description). Rates stay on the Salary Structure, not here,
	# because they change by nationality and by regulation.
	("Employee GOSI", "Deduction", "Employee GOSI contribution"),
	("Employer GOSI", "Deduction", "Employer GOSI contribution (company cost)"),
)


@frappe.whitelist()
def ensure_gosi_components():
	created = []
	for name, component_type, description in GOSI_COMPONENTS:
		if frappe.db.exists("Salary Component", name):
			continue
		doc = frappe.get_doc({
			"doctype": "Salary Component",
			"salary_component": name,
			"type": component_type,
			"description": description,
			"is_tax_applicable": 0,
			"depends_on_payment_days": 0,
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		created.append(name)
	return created
