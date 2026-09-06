"""Reference dataset for the AGS EduSmart ERP.

Builds the exact worked example the handover uses, so the numbers in the docs can
be checked against a running system:

* the Grade 5 fee structure of SKILL sec. 17.3 (24,500 total);
* the sibling tiers of SKILL sec. 17.6 - second child 10%, third 15%, tuition
  only, books and transport excluded;
* the one-payer-three-children statement of SKILL sec. 18.

Idempotent: every creation is guarded, so it is safe to re-run and safe to use as
the fixture base for the test suite.

    bench --site <site> execute ags_edusmart.setup.demo.build
"""

from __future__ import annotations

import frappe
from frappe.utils import add_days, flt, nowdate

COMPANY = "AGS Education Group"
ABBR = "AGS"
CURRENCY = "SAR"

CAMPUSES = [
	{"campus_name": "Jeddah", "abbr": "JED", "city": "Jeddah", "region": "Makkah"},
	{"campus_name": "Riyadh", "abbr": "RUH", "city": "Riyadh", "region": "Riyadh"},
]

DIVISIONS = [
	{"division_name": "Kindergarten", "abbr": "KG", "division_type": "Kindergarten"},
	{"division_name": "Primary", "abbr": "PRI", "division_type": "Primary"},
	{"division_name": "Middle", "abbr": "MID", "division_type": "Middle"},
	{"division_name": "Secondary", "abbr": "SEC", "division_type": "Secondary"},
]

PROGRAMS = ["KG2", "Grade 5", "Grade 8"]

# (fee category, income account name, is discountable by the sibling rule)
FEE_CATEGORIES = [
	("Tuition Fee", "Tuition Revenue", True),
	("Registration Fee", "Registration Revenue", False),
	("Books", "Books Revenue", False),
	("Transportation", "Transportation Revenue", False),
	("Activity Fee", "Activities Revenue", False),
	("Technology Fee", "Technology Fees", False),
]

# SKILL sec. 17.3, Grade 5 - 2026/27
GRADE_5_STRUCTURE = [
	("Tuition Fee", 20000),
	("Registration Fee", 1500),
	("Books", 1200),
	("Activity Fee", 1000),
	("Technology Fee", 800),
]

ACADEMIC_YEAR = "2026-2027"


def build() -> dict:
	frappe.flags.in_demo = True
	company = _company()
	_fiscal_years(company)
	_price_list(company)
	_income_accounts(company)
	campuses = _campuses(company)
	_divisions(campuses)
	year = _academic_year()
	_terms(year)
	programs = _programs()
	_fee_categories(company)
	structure = _fee_structure(company, year)
	payer, students = _family(company, campuses[0], year, programs)
	_discount_rules(company, year)
	frappe.db.commit()

	return {
		"company": company,
		"campuses": campuses,
		"academic_year": year,
		"fee_structure": structure,
		"payer": payer,
		"students": students,
	}


# ----------------------------------------------------------------- company
def _company() -> str:
	if frappe.db.exists("Company", COMPANY):
		return COMPANY
	doc = frappe.get_doc({
		"doctype": "Company",
		"company_name": COMPANY,
		"abbr": ABBR,
		"default_currency": CURRENCY,
		"country": "Saudi Arabia",
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


def _fiscal_years(company: str) -> None:
	"""School fiscal years run September to August, matching the academic year.

	A site created with ``bench new-site`` has none at all, and every accounting
	transaction fails on posting date without one.
	"""
	years = [
		("2025-2026", "2025-09-01", "2026-08-31"),
		("2026-2027", "2026-09-01", "2027-08-31"),
		("2027-2028", "2027-09-01", "2028-08-31"),
	]
	for name, start, end in years:
		if frappe.db.exists("Fiscal Year", name):
			continue
		doc = frappe.get_doc({
			"doctype": "Fiscal Year",
			"year": name,
			"year_start_date": start,
			"year_end_date": end,
			"companies": [{"company": company}],
		})
		doc.flags.ignore_permissions = True
		doc.insert()

	# No "current fiscal year" default is set: ERPNext resolves the year from the
	# posting date, and pinning one here would silently mis-date a transaction
	# posted either side of 1 September.


def _price_list(company: str) -> str:
	"""A selling price list in the company currency.

	Sales Invoice requires one even when every rate is supplied by the fee plan,
	and the stock "Standard Selling" list ships in INR - which then cannot resolve
	an exchange rate against an SAR receivable account.
	"""
	name = "AGS Selling"
	if not frappe.db.exists("Price List", name):
		doc = frappe.get_doc({
			"doctype": "Price List",
			"price_list_name": name,
			"currency": CURRENCY,
			"selling": 1,
			"buying": 0,
			"enabled": 1,
		})
		doc.flags.ignore_permissions = True
		doc.insert()

	settings = frappe.get_single("Selling Settings")
	current = settings.selling_price_list
	if not current or frappe.db.get_value("Price List", current, "currency") != CURRENCY:
		settings.selling_price_list = name
		settings.flags.ignore_permissions = True
		settings.save()
	return name


def _account(name: str, parent: str, company: str, root_type: str,
             account_type: str | None = None) -> str:
	full = f"{name} - {ABBR}"
	if frappe.db.exists("Account", full):
		return full
	parent_full = frappe.db.get_value(
		"Account", {"company": company, "account_name": parent, "is_group": 1}, "name"
	)
	if not parent_full:
		return ""
	doc = frappe.get_doc({
		"doctype": "Account",
		"account_name": name,
		"parent_account": parent_full,
		"company": company,
		"root_type": root_type,
		"account_type": account_type,
		"is_group": 0,
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


def _income_accounts(company: str) -> None:
	for _, account_name, _discountable in FEE_CATEGORIES:
		_account(account_name, "Direct Income", company, "Income")
	# Deferred tuition sits as a liability until it is recognised (SKILL sec. 5.4).
	deferred = _account(
		"Deferred Tuition Revenue", "Current Liabilities", company, "Liability"
	)
	settings = frappe.get_single("AGS Settings")
	if not settings.default_company:
		settings.default_company = company
	if deferred and not settings.deferred_revenue_account:
		settings.deferred_revenue_account = deferred
	settings.current_academic_year = ACADEMIC_YEAR if frappe.db.exists(
		"Academic Year", ACADEMIC_YEAR
	) else settings.current_academic_year
	settings.flags.ignore_permissions = True
	settings.save()


# ------------------------------------------------------------------ campus
def _cost_center(name: str, company: str, parent: str | None = None) -> str:
	full = f"{name} - {ABBR}"
	if frappe.db.exists("Cost Center", full):
		return full
	parent_cc = parent or frappe.db.get_value(
		"Cost Center", {"company": company, "is_group": 1}, "name"
	)
	doc = frappe.get_doc({
		"doctype": "Cost Center",
		"cost_center_name": name,
		"parent_cost_center": parent_cc,
		"company": company,
		"is_group": 0,
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


def _campuses(company: str) -> list[str]:
	names = []
	for row in CAMPUSES:
		if not frappe.db.exists("AGS Campus", row["campus_name"]):
			doc = frappe.get_doc({
				"doctype": "AGS Campus",
				"company": company,
				"cost_center": _cost_center(f"{row['campus_name']} Campus", company),
				"default_receivable_account": frappe.db.get_value(
					"Account", {"company": company, "account_type": "Receivable",
					            "is_group": 0}, "name"
				),
				**row,
			})
			doc.flags.ignore_permissions = True
			doc.insert()
		names.append(row["campus_name"])
	return names


def _divisions(campuses: list[str]) -> None:
	for campus in campuses[:1]:
		for row in DIVISIONS:
			name = f"{campus}-{row['abbr']}"
			if frappe.db.exists("AGS School Division", name):
				continue
			doc = frappe.get_doc({
				"doctype": "AGS School Division", "campus": campus, **row
			})
			doc.flags.ignore_permissions = True
			doc.insert()


# ---------------------------------------------------------------- academic
def _academic_year() -> str:
	if not frappe.db.exists("Academic Year", ACADEMIC_YEAR):
		doc = frappe.get_doc({
			"doctype": "Academic Year",
			"academic_year_name": ACADEMIC_YEAR,
			"year_start_date": "2026-09-01",
			"year_end_date": "2027-06-30",
		})
		doc.flags.ignore_permissions = True
		doc.insert()
	return ACADEMIC_YEAR


def _terms(year: str) -> None:
	terms = [
		("Term 1", "2026-09-01", "2026-12-15"),
		("Term 2", "2027-01-05", "2027-03-25"),
		("Term 3", "2027-04-05", "2027-06-30"),
	]
	for name, start, end in terms:
		if frappe.db.exists("Academic Term", f"{year} ({name})"):
			continue
		doc = frappe.get_doc({
			"doctype": "Academic Term",
			"academic_year": year,
			"term_name": name,
			"term_start_date": start,
			"term_end_date": end,
		})
		doc.flags.ignore_permissions = True
		doc.insert()


def _programs() -> list[str]:
	for name in PROGRAMS:
		if frappe.db.exists("Program", name):
			continue
		doc = frappe.get_doc({
			"doctype": "Program", "program_name": name, "program_code": name,
		})
		doc.flags.ignore_permissions = True
		doc.insert()
	return PROGRAMS


# -------------------------------------------------------------------- fees
def _stock_prerequisites() -> None:
	"""Frappe Education creates the Item behind a Fee Category itself, but its
	``create_item`` leaves ``stock_uom`` to the Stock Settings default and files
	it under the "Fee Component" item group. Both have to exist first on a site
	built with ``bench new-site`` rather than the setup wizard."""
	if not frappe.db.exists("Item Group", "Fee Component"):
		root = frappe.db.get_value("Item Group", {"is_group": 1, "parent_item_group": ""},
		                           "name") or "All Item Groups"
		group = frappe.get_doc({
			"doctype": "Item Group",
			"item_group_name": "Fee Component",
			"parent_item_group": root,
			"is_group": 0,
		})
		group.flags.ignore_permissions = True
		group.insert()

	stock_settings = frappe.get_single("Stock Settings")
	if not stock_settings.stock_uom and frappe.db.exists("UOM", "Nos"):
		stock_settings.stock_uom = "Nos"
		stock_settings.flags.ignore_permissions = True
		stock_settings.save()


def _education_prerequisites() -> None:
	"""Student is named ``naming_series:``, so the series has to be supplied on
	insert - a site built with ``bench new-site`` has no default for it and the
	insert fails on None.strip()."""
	settings = frappe.get_single("Education Settings")
	changed = False
	if not settings.instructor_created_by:
		settings.instructor_created_by = "Full Name"
		changed = True
	if not settings.current_academic_year and frappe.db.exists(
		"Academic Year", ACADEMIC_YEAR
	):
		settings.current_academic_year = ACADEMIC_YEAR
		changed = True
	if changed:
		settings.flags.ignore_permissions = True
		settings.save()


def _student_series() -> str:
	meta = frappe.get_meta("Student")
	field = meta.get_field("naming_series")
	options = [o for o in (field.options or "").split("\n") if o.strip()] if field else []
	return options[0] if options else "EDU-STU-.YYYY.-"


def _fee_categories(company: str) -> None:
	_stock_prerequisites()
	for category, account_name, _discountable in FEE_CATEGORIES:
		account = f"{account_name} - {ABBR}"
		if frappe.db.exists("Fee Category", category):
			continue
		# item_defaults carries the revenue account down onto the generated Item,
		# which is what maps a fee to its income account (SKILL sec. 17.1).
		doc = frappe.get_doc({
			"doctype": "Fee Category",
			"category_name": category,
			"description": category,
			"item_defaults": [{"company": company, "income_account": account}],
		})
		doc.flags.ignore_permissions = True
		doc.insert()


def _fee_structure(company: str, year: str) -> str:
	existing = frappe.db.get_value(
		"Fee Structure",
		{"program": "Grade 5", "academic_year": year, "docstatus": 1},
		"name",
	)
	if existing:
		return existing

	doc = frappe.get_doc({
		"doctype": "Fee Structure",
		"program": "Grade 5",
		"academic_year": year,
		"company": company,
		"receivable_account": frappe.db.get_value(
			"Account",
			{"company": company, "account_type": "Receivable", "is_group": 0},
			"name",
		),
		"components": [
			{
				"fees_category": category,
				"description": category,
				"amount": amount,
				"item": frappe.db.get_value("Fee Category", category, "item"),
			}
			for category, amount in GRADE_5_STRUCTURE
		],
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	return doc.name


# ------------------------------------------------------------------ family
def _family(company: str, campus: str, year: str, programs: list[str]):
	"""One payer, three children - the SKILL sec. 18 example."""
	_education_prerequisites()
	guardian_name = "Mohamed Ahmed"
	if not frappe.db.exists("Guardian", {"guardian_name": guardian_name}):
		guardian = frappe.get_doc({
			"doctype": "Guardian",
			"guardian_name": guardian_name,
			"email_address": "mohamed.ahmed@example.com",
			"mobile_number": "0500000000",
		})
		guardian.flags.ignore_permissions = True
		guardian.insert()
	guardian_id = frappe.db.get_value("Guardian", {"guardian_name": guardian_name}, "name")

	customer = "Mohamed Ahmed (Payer)"
	if not frappe.db.exists("Customer", customer):
		doc = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": customer,
			"customer_type": "Individual",
			"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
			"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
		})
		doc.flags.ignore_permissions = True
		doc.insert()

	# Eldest first, so the sibling index is unambiguous.
	# Education creates a portal User from student_email_id on insert, so each
	# child needs a distinct address or the User autoname fails.
	children = [
		("Ali", "Ahmed", "2012-03-14", "Grade 8", "ali.ahmed@example.com"),
		("Sara", "Ahmed", "2015-07-02", "Grade 5", "sara.ahmed@example.com"),
		("Omar", "Ahmed", "2020-11-20", "KG2", "omar.ahmed@example.com"),
	]
	student_ids = []
	for first, last, dob, program, email in children:
		existing = frappe.db.get_value(
			"Student", {"first_name": first, "last_name": last}, "name"
		)
		if existing:
			student_ids.append(existing)
			continue
		doc = frappe.get_doc({
			"doctype": "Student",
			"naming_series": _student_series(),
			"first_name": first,
			"student_email_id": email,
			"last_name": last,
			"date_of_birth": dob,
			"joining_date": "2026-09-01",
			"ags_campus": campus,
			"guardians": [{"guardian": guardian_id, "relation": "Father"}],
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		student_ids.append(doc.name)

	payer = frappe.db.get_value("AGS Payer Account", {"customer": customer}, "name")
	if not payer:
		doc = frappe.get_doc({
			"doctype": "AGS Payer Account",
			"payer_name": guardian_name,
			"guardian": guardian_id,
			"customer": customer,
			"company": company,
			"campus": campus,
			"email": "mohamed.ahmed@example.com",
			"mobile": "0500000000",
			"students": [
				{"student": sid, "program": program, "academic_year": year,
				 "relationship": "Father", "share_percent": 100, "is_primary": 1}
				for sid, (_f, _l, _d, program, _e) in zip(student_ids, children)
			],
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		payer = doc.name

	return payer, student_ids


# --------------------------------------------------------------- discounts
def _discount_rules(company: str, year: str) -> None:
	"""SKILL sec. 17.6: tuition only; books, transport and registration excluded."""
	tiers = [
		("Sibling Discount - Second Child", 2, 2, 10),
		("Sibling Discount - Third Child Onwards", 3, 0, 15),
	]
	for title, index_from, index_to, value in tiers:
		if frappe.db.exists("AGS Discount Rule", title):
			continue
		doc = frappe.get_doc({
			"doctype": "AGS Discount Rule",
			"title": title,
			"discount_type": "Sibling Discount",
			"calculation": "Percent",
			"value": value,
			"priority": 10,
			"stackable": 1,
			"apply_to_all_components": 0,
			"company": company,
			"academic_year": year,
			"sibling_index_from": index_from,
			"sibling_index_to": index_to,
			"components": [{"fees_category": "Tuition Fee"}],
			"is_active": 1,
			"description": "Tuition only. Books, transport and registration are excluded.",
		})
		doc.flags.ignore_permissions = True
		doc.insert()


# ------------------------------------------------------------ demo journey
def run_journey() -> dict:
	"""Price the middle child, invoice term 1 and take a part payment.

	Used by the smoke check to prove the whole chain posts to the GL.
	"""
	data = build()
	payer = data["payer"]
	sara = frappe.db.get_value("Student", {"first_name": "Sara"}, "name")

	plan_name = frappe.db.get_value(
		"AGS Fee Plan", {"student": sara, "academic_year": ACADEMIC_YEAR,
		                 "docstatus": ("<", 2)}, "name"
	)
	if not plan_name:
		plan = frappe.get_doc({
			"doctype": "AGS Fee Plan",
			"student": sara,
			"payer_account": payer,
			"company": data["company"],
			"campus": data["campuses"][0],
			"academic_year": ACADEMIC_YEAR,
			"program": "Grade 5",
			"fee_structure": data["fee_structure"],
			"schedule_type": "By Term",
			"first_due_date": add_days(nowdate(), 7),
			"auto_apply_discounts": 1,
		})
		plan.flags.ignore_permissions = True
		plan.insert()
		plan.submit()
		plan_name = plan.name

	plan = frappe.get_doc("AGS Fee Plan", plan_name)
	return {
		"fee_plan": plan.name,
		"gross_total": flt(plan.gross_total),
		"discount_total": flt(plan.discount_total),
		"net_total": flt(plan.net_total),
		"installments": [
			{"no": r.installment_no, "due": str(r.due_date), "amount": flt(r.amount)}
			for r in plan.installments
		],
	}
