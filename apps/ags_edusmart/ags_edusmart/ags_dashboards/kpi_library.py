"""KPI implementations (SKILL sec. 27).

Each function takes a scope dict and returns a single float. They read from the
ledger and the operational tables directly rather than from each other, so one
broken KPI cannot corrupt the rest of the dashboard.

Scope keys: company, campus, school_division, program, department,
academic_year, from_date, to_date.
"""

from __future__ import annotations

import frappe
from frappe.utils import add_months, flt, getdate, nowdate

REGISTRY: dict = {}


def kpi(code: str):
	def wrap(fn):
		REGISTRY[code] = fn
		return fn

	return wrap


def resolve(method_path: str):
	return REGISTRY.get(method_path)


# ----------------------------------------------------------------- helpers
def _period(scope) -> tuple:
	to_date = getdate(scope.get("to_date") or nowdate())
	from_date = getdate(scope.get("from_date") or add_months(to_date, -12))
	return from_date, to_date


def _invoice_filter(scope, alias="si") -> tuple[str, dict]:
	conditions = [f"{alias}.docstatus = 1"]
	params: dict = {}
	if scope.get("company"):
		conditions.append(f"{alias}.company = %(company)s")
		params["company"] = scope["company"]
	if scope.get("campus"):
		conditions.append(f"{alias}.ags_campus = %(campus)s")
		params["campus"] = scope["campus"]
	return " and ".join(conditions), params


def _student_filter(scope) -> tuple[str, dict]:
	conditions = ["s.enabled = 1"]
	params: dict = {}
	if scope.get("campus"):
		conditions.append("s.ags_campus = %(campus)s")
		params["campus"] = scope["campus"]
	return " and ".join(conditions), params


def _scalar(query: str, params: dict) -> float:
	rows = frappe.db.sql(query, params)
	return flt(rows[0][0]) if rows and rows[0] and rows[0][0] is not None else 0.0


# -------------------------------------------------------------- population
@kpi("total_students")
def total_students(scope) -> float:
	where, params = _student_filter(scope)
	return _scalar(f"select count(*) from `tabStudent` s where {where}", params)


@kpi("enrollment_growth")
def enrollment_growth(scope) -> float:
	"""Percentage change in enrollments against the prior academic year."""
	year = scope.get("academic_year")
	if not year:
		return 0.0
	current = _scalar(
		"""select count(*) from `tabProgram Enrollment` where docstatus = 1
		   and academic_year = %(year)s""",
		{"year": year},
	)
	previous_year = frappe.db.get_value(
		"Academic Year",
		{"year_start_date": ("<", frappe.db.get_value("Academic Year", year, "year_start_date"))},
		"name",
		order_by="year_start_date desc",
	)
	if not previous_year:
		return 0.0
	previous = _scalar(
		"""select count(*) from `tabProgram Enrollment` where docstatus = 1
		   and academic_year = %(year)s""",
		{"year": previous_year},
	)
	return flt((current - previous) / previous * 100, 2) if previous else 0.0


@kpi("students_per_teacher")
def students_per_teacher(scope) -> float:
	students = total_students(scope)
	teachers = _scalar(
		"""
		select count(*) from `tabEmployee` e
		where e.status = 'Active'
		  and exists (select 1 from `tabInstructor` i where i.employee = e.name)
		""",
		{},
	)
	return flt(students / teachers, 2) if teachers else 0.0


# ------------------------------------------------------------------ revenue
@kpi("total_revenue")
def total_revenue(scope) -> float:
	from_date, to_date = _period(scope)
	where, params = _invoice_filter(scope)
	params.update({"from_date": from_date, "to_date": to_date})
	return _scalar(
		f"""
		select sum(si.base_net_total) from `tabSales Invoice` si
		where {where} and si.is_return = 0
		  and si.posting_date between %(from_date)s and %(to_date)s
		""",
		params,
	)


@kpi("revenue_per_student")
def revenue_per_student(scope) -> float:
	students = total_students(scope)
	return flt(total_revenue(scope) / students, 2) if students else 0.0


@kpi("cost_per_student")
def cost_per_student(scope) -> float:
	students = total_students(scope)
	if not students:
		return 0.0
	from_date, to_date = _period(scope)
	expense = _scalar(
		"""
		select sum(gle.debit - gle.credit)
		from `tabGL Entry` gle
		inner join `tabAccount` a on a.name = gle.account
		where gle.is_cancelled = 0 and a.root_type = 'Expense'
		  and gle.company = %(company)s
		  and gle.posting_date between %(from_date)s and %(to_date)s
		""",
		{"company": scope.get("company"), "from_date": from_date, "to_date": to_date},
	)
	return flt(expense / students, 2)


# -------------------------------------------------------------- collections
@kpi("outstanding_fees")
def outstanding_fees(scope) -> float:
	where, params = _invoice_filter(scope)
	return _scalar(
		f"""select sum(si.outstanding_amount) from `tabSales Invoice` si
		    where {where} and si.ags_fee_plan is not null""",
		params,
	)


@kpi("overdue_fees")
def overdue_fees(scope) -> float:
	where, params = _invoice_filter(scope)
	return _scalar(
		f"""select sum(si.outstanding_amount) from `tabSales Invoice` si
		    where {where} and si.ags_fee_plan is not null and si.due_date < curdate()""",
		params,
	)


@kpi("collection_percent")
def collection_percent(scope) -> float:
	where, params = _invoice_filter(scope)
	billed = _scalar(
		f"""select sum(si.grand_total) from `tabSales Invoice` si
		    where {where} and si.ags_fee_plan is not null""",
		params,
	)
	if not billed:
		return 0.0
	collected = billed - outstanding_fees(scope)
	return flt(collected / billed * 100, 2)


@kpi("outstanding_to_revenue")
def outstanding_to_revenue(scope) -> float:
	revenue = total_revenue(scope)
	return flt(outstanding_fees(scope) / revenue * 100, 2) if revenue else 0.0


# ------------------------------------------------------------------- payroll
@kpi("payroll_cost")
def payroll_cost(scope) -> float:
	from_date, to_date = _period(scope)
	return _scalar(
		"""
		select sum(ss.base_gross_pay) from `tabSalary Slip` ss
		where ss.docstatus = 1 and ss.company = %(company)s
		  and ss.start_date between %(from_date)s and %(to_date)s
		""",
		{"company": scope.get("company"), "from_date": from_date, "to_date": to_date},
	)


@kpi("payroll_to_revenue")
def payroll_to_revenue(scope) -> float:
	revenue = total_revenue(scope)
	return flt(payroll_cost(scope) / revenue * 100, 2) if revenue else 0.0


@kpi("employee_cost_per_student")
def employee_cost_per_student(scope) -> float:
	students = total_students(scope)
	return flt(payroll_cost(scope) / students, 2) if students else 0.0


# ------------------------------------------------------------------ academic
@kpi("student_attendance_rate")
def student_attendance_rate(scope) -> float:
	from_date, to_date = _period(scope)
	rows = frappe.db.sql(
		"""
		select
			sum(case when status = 'Present' then 1 else 0 end) as present,
			count(*) as total
		from `tabStudent Attendance`
		where docstatus = 1 and date between %(from_date)s and %(to_date)s
		""",
		{"from_date": from_date, "to_date": to_date},
		as_dict=True,
	)
	if not rows or not rows[0].total:
		return 0.0
	return flt(rows[0].present / rows[0].total * 100, 2)


# --------------------------------------------------------------- procurement
@kpi("open_purchase_orders")
def open_purchase_orders(scope) -> float:
	return _scalar(
		"""
		select sum(po.grand_total - po.per_billed * po.grand_total / 100)
		from `tabPurchase Order` po
		where po.docstatus = 1 and po.status not in ('Closed', 'Completed')
		  and po.company = %(company)s
		""",
		{"company": scope.get("company")},
	)


@kpi("invoice_mismatches")
def invoice_mismatches(scope) -> float:
	filters = {"status": "Open"}
	if scope.get("company"):
		filters["company"] = scope["company"]
	if scope.get("campus"):
		filters["campus"] = scope["campus"]
	return flt(frappe.db.count("AGS Three Way Match Exception", filters))


# ----------------------------------------------------------------- inventory
@kpi("stock_value")
def stock_value(scope) -> float:
	return _scalar(
		"""
		select sum(b.stock_value) from `tabBin` b
		inner join `tabWarehouse` w on w.name = b.warehouse
		where w.company = %(company)s
		""",
		{"company": scope.get("company")},
	)


@kpi("items_below_reorder")
def items_below_reorder(scope) -> float:
	return _scalar(
		"""
		select count(distinct b.item_code)
		from `tabBin` b
		inner join `tabWarehouse` w on w.name = b.warehouse
		inner join `tabItem Reorder` ir
		        on ir.parent = b.item_code and ir.warehouse = b.warehouse
		where w.company = %(company)s and b.actual_qty < ir.warehouse_reorder_level
		""",
		{"company": scope.get("company")},
	)


# ------------------------------------------------------------------- finance
@kpi("budget_variance")
def budget_variance(scope) -> float:
	"""Actual expense against budget, as a percentage over (positive = overspend)."""
	fiscal_year = frappe.db.get_value(
		"Fiscal Year",
		{"year_start_date": ("<=", nowdate()), "year_end_date": (">=", nowdate())},
		"name",
	)
	if not fiscal_year:
		return 0.0
	budget = _scalar(
		"""
		select sum(ba.budget_amount) from `tabBudget Account` ba
		inner join `tabBudget` b on b.name = ba.parent
		where b.docstatus = 1 and b.company = %(company)s and b.fiscal_year = %(fy)s
		""",
		{"company": scope.get("company"), "fy": fiscal_year},
	)
	if not budget:
		return 0.0
	dates = frappe.db.get_value(
		"Fiscal Year", fiscal_year, ["year_start_date", "year_end_date"], as_dict=True
	)
	actual = _scalar(
		"""
		select sum(gle.debit - gle.credit)
		from `tabGL Entry` gle
		inner join `tabAccount` a on a.name = gle.account
		where gle.is_cancelled = 0 and a.root_type = 'Expense'
		  and gle.company = %(company)s
		  and gle.posting_date between %(start)s and %(end)s
		""",
		{
			"company": scope.get("company"),
			"start": dates.year_start_date,
			"end": dates.year_end_date,
		},
	)
	return flt((actual - budget) / budget * 100, 2)


@kpi("cash_position")
def cash_position(scope) -> float:
	return _scalar(
		"""
		select sum(gle.debit - gle.credit)
		from `tabGL Entry` gle
		inner join `tabAccount` a on a.name = gle.account
		where gle.is_cancelled = 0 and gle.company = %(company)s
		  and a.account_type in ('Cash', 'Bank')
		""",
		{"company": scope.get("company")},
	)
