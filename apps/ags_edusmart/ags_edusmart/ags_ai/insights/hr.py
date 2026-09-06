"""HR analyses (SKILL sec. 28.4).

* Which departments have unusually high absenteeism?
* What is projected payroll next year?
* Which contracts expire in 60 days?

Absence and payroll are personal data, so these are restricted to HR and
executive roles. A department head who is not in those roles sees nothing here,
which is deliberate: "absenteeism by department" is one join away from
"absenteeism by person".
"""

from __future__ import annotations

import statistics

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, getdate, nowdate

from ags_edusmart.ags_ai.insights._base import campus_clause, campus_note
from ags_edusmart.ags_ai.insights.inventory import _robust_outliers
from ags_edusmart.ags_ai.registry import Finding, analyzer

HR_ROLES = (
	"AGS HR Manager", "AGS HR Officer", "AGS Payroll Officer",
	"AGS Group Executive", "AGS Finance Manager", "AGS Principal",
)


@analyzer(
	code="absenteeism_outliers",
	question="Which departments have unusually high absenteeism?",
	category="HR",
	keywords=("absence", "absent", "absenteeism", "department", "unusual", "leave"),
	roles=HR_ROLES,
)
def absenteeism_outliers(scope, **_params) -> Finding:
	"""Absence rate per department, with robust outliers flagged."""
	rows = frappe.db.sql(
		"""
		select
			coalesce(e.department, '—') as department,
			sum(case when a.status = 'Absent' then 1 else 0 end) as absent,
			count(*) as records
		from `tabAttendance` a
		inner join `tabEmployee` e on e.name = a.employee
		where a.docstatus = 1 and a.company = %(company)s
		  and a.attendance_date between %(from_date)s and %(to_date)s
		group by coalesce(e.department, '—')
		having count(*) > 0
		""",
		{"company": scope.company, "from_date": scope.from_date, "to_date": scope.to_date},
		as_dict=True,
	)

	finding = Finding(
		code="absenteeism_outliers",
		title=_("Absenteeism by department"),
		unit="Percent",
	)

	if len(rows) < 3:
		finding.summary = _(
			"Attendance is recorded for only {0} department(s) in this period - "
			"too few to identify an outlier."
		).format(len(rows))
		finding.insufficient_data = True
		return finding

	rates = {
		r.department: flt(int(r.absent) / int(r.records) * 100, 2)
		for r in rows if int(r.records)
	}
	outliers = _robust_outliers(rates)

	finding.rows = sorted(
		[
			{
				"department": r.department,
				"absence_rate": rates[r.department],
				"absent_days": int(r.absent),
				"records": int(r.records),
				"is_outlier": r.department in outliers,
			}
			for r in rows if r.department in rates
		],
		key=lambda r: r["absence_rate"], reverse=True,
	)

	overall = flt(
		sum(int(r.absent) for r in rows) / sum(int(r.records) for r in rows) * 100, 2
	)
	finding.headline = overall

	if not outliers:
		finding.summary = _(
			"Absence runs at {0}% overall and no department stands out against "
			"the others."
		).format(overall)
		return finding

	worst = max(outliers, key=lambda k: rates[k])
	finding.summary = _(
		"Absence runs at {0}% overall. {1} department(s) are unusually high; {2} "
		"is the clearest at {3}% against a median of {4}%."
	).format(
		overall, len(outliers), worst, rates[worst],
		flt(statistics.median(rates.values()), 2),
	)
	return finding


@analyzer(
	code="payroll_projection",
	question="What is projected payroll next year?",
	category="HR",
	keywords=("payroll", "projected", "project", "next year", "forecast", "salary", "cost"),
	roles=HR_ROLES,
)
def payroll_projection(scope, growth_percent: float = 0.0, **_params) -> Finding:
	"""Annualised payroll from current salary structures, not last year's slips.

	Structures reflect who is on the payroll *now*, including people who joined
	mid-year and excluding leavers. Extrapolating from historical slips carries
	last year's headcount forward, which is the usual way these projections come
	out wrong.
	"""
	rows = frappe.db.sql(
		"""
		select ssa.employee, ssa.base, ssa.variable, e.department, e.designation
		from `tabSalary Structure Assignment` ssa
		inner join `tabEmployee` e on e.name = ssa.employee
		where ssa.docstatus = 1 and e.status = 'Active'
		  and ssa.company = %(company)s
		  and ssa.from_date = (
		      select max(x.from_date) from `tabSalary Structure Assignment` x
		      where x.employee = ssa.employee and x.docstatus = 1
		        and x.from_date <= curdate()
		  )
		""",
		{"company": scope.company},
		as_dict=True,
	)

	finding = Finding(
		code="payroll_projection",
		title=_("Projected annual payroll"),
		unit="Currency",
	)

	if not rows:
		# Fall back to posted slips so the answer is not simply "unknown".
		actual = flt(frappe.db.sql(
			"""
			select sum(ss.base_gross_pay) from `tabSalary Slip` ss
			where ss.docstatus = 1 and ss.company = %(company)s
			  and ss.start_date >= %(since)s
			""",
			{"company": scope.company, "since": str(add_months(getdate(nowdate()), -12))},
		)[0][0], 2)
		if not actual:
			finding.summary = _(
				"No salary structures are assigned and no payslips have been "
				"posted, so payroll cannot be projected."
			)
			finding.insufficient_data = True
			return finding
		finding.headline = actual
		finding.summary = _(
			"No current salary structure assignments exist. Based on the last 12 "
			"months of posted payslips, payroll is running at {0} a year."
		).format(frappe.utils.fmt_money(actual))
		finding.notes.append(
			_("Projected from historical payslips, so it carries last year's "
			  "headcount rather than today's.")
		)
		return finding

	monthly = sum(flt(r.base) + flt(r.variable) for r in rows)
	annual = flt(monthly * 12, 2)
	projected = flt(annual * (1 + flt(growth_percent) / 100.0), 2)

	by_department: dict[str, float] = {}
	for row in rows:
		key = row.department or "—"
		by_department[key] = by_department.get(key, 0.0) + (flt(row.base) + flt(row.variable)) * 12

	finding.headline = projected
	finding.rows = sorted(
		[{"department": k, "annual": flt(v, 2)} for k, v in by_department.items()],
		key=lambda r: r["annual"], reverse=True,
	)
	finding.summary = _(
		"{0} active employee(s) on current structures annualise to {1}."
	).format(len(rows), frappe.utils.fmt_money(annual)) + (
		_(" With {0}% growth applied, next year projects to {1}.").format(
			flt(growth_percent, 1), frappe.utils.fmt_money(projected)
		) if growth_percent else ""
	)
	finding.notes.append(
		_("Based on current salary structure assignments. Does not include "
		  "planned hires, promotions or end-of-service provisions.")
	)
	return finding


@analyzer(
	code="expiring_documents",
	question="Which contracts and Iqamas expire soon?",
	category="HR",
	keywords=("expire", "expiry", "contract", "iqama", "passport", "renew", "60 days"),
	roles=HR_ROLES,
)
def expiring_documents(scope, days: int = 60, **_params) -> Finding:
	"""Employee documents expiring inside the window, soonest first."""
	clause, params = campus_clause(scope, "de", "AGS Document Expiry")
	params.update({"cutoff": str(add_days(nowdate(), int(days)))})

	rows = frappe.db.sql(
		f"""
		select de.employee, de.employee_name, de.document_type, de.document_number,
		       de.expiry_date, de.status, de.campus,
		       datediff(de.expiry_date, curdate()) as days_left
		from `tabAGS Document Expiry` de
		where de.expiry_date <= %(cutoff)s and {clause}
		order by de.expiry_date asc
		limit 100
		""",
		params,
		as_dict=True,
	)

	finding = Finding(
		code="expiring_documents",
		title=_("Documents expiring within {0} days").format(int(days)),
		unit="Number",
		notes=campus_note(scope, "AGS Document Expiry"),
	)

	if not rows:
		finding.headline = 0.0
		finding.summary = _("No employee document expires in the next {0} days.").format(
			int(days)
		)
		return finding

	expired = [r for r in rows if int(r.days_left or 0) < 0]
	finding.headline = float(len(rows))
	finding.rows = [
		{
			"employee": r.employee,
			"employee_name": r.employee_name,
			"document_type": r.document_type,
			"expiry_date": str(r.expiry_date),
			"days_left": int(r.days_left or 0),
			"status": r.status,
			"campus": r.campus,
		}
		for r in rows
	]
	finding.summary = _(
		"{0} document(s) expire within {1} days, of which {2} have already "
		"expired. Soonest: {3}'s {4} on {5}."
	).format(
		len(rows), int(days), len(expired), rows[0].employee_name,
		_(rows[0].document_type), rows[0].expiry_date,
	)
	return finding
