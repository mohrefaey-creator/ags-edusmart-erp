"""Academic analyses (SKILL sec. 28.5).

* Which students are at attendance risk?
* Which classes show declining academic performance?
* Which teachers have classes significantly below the school average?

The last one names individual staff against a performance measure, so it is
restricted to the roles that hold that conversation - and the analysis reports a
*variance to investigate*, never a judgement. A class average sits downstream of
intake, subject and cohort; treating the number as a verdict on the teacher would
be both unfair and wrong.
"""

from __future__ import annotations

import statistics

import frappe
from frappe import _
from frappe.utils import add_months, flt, getdate, nowdate

from ags_edusmart.ags_ai.registry import Finding, analyzer

ACADEMIC_ROLES = (
	"AGS Principal", "AGS Vice Principal", "AGS Academic Coordinator",
	"AGS Group Executive", "AGS Counselor",
)

# Naming a teacher against a performance number is a narrower conversation.
TEACHER_REVIEW_ROLES = (
	"AGS Principal", "AGS Vice Principal", "AGS Academic Coordinator",
	"AGS Group Executive",
)


@analyzer(
	code="attendance_risk",
	question="Which students are at attendance risk?",
	category="Academic",
	keywords=("attendance", "risk", "absent", "chronic", "student", "missing school"),
	roles=ACADEMIC_ROLES,
)
def attendance_risk(scope, threshold_percent: float = 90.0, minimum_days: int = 10,
                    limit: int = 30, **_params) -> Finding:
	"""Students below an attendance threshold over the scope window.

	``minimum_days`` guards against a student who joined last week appearing at
	the top of the list on the strength of two absences.
	"""
	rows = frappe.db.sql(
		"""
		select
			sa.student, sa.student_name,
			sum(case when sa.status = 'Present' then 1 else 0 end) as present,
			count(*) as recorded
		from `tabStudent Attendance` sa
		where sa.docstatus = 1
		  and sa.date between %(from_date)s and %(to_date)s
		group by sa.student, sa.student_name
		having count(*) >= %(minimum_days)s
		""",
		{
			"from_date": scope.from_date,
			"to_date": scope.to_date,
			"minimum_days": int(minimum_days),
		},
		as_dict=True,
	)

	finding = Finding(
		code="attendance_risk",
		title=_("Students at attendance risk"),
		unit="Number",
	)

	if not rows:
		finding.headline = 0.0
		finding.summary = _(
			"No student has at least {0} attendance records in this period, so "
			"attendance risk cannot be assessed."
		).format(int(minimum_days))
		finding.insufficient_data = True
		return finding

	# Campus scoping goes through the student rather than the attendance record,
	# which carries no campus of its own.
	allowed: set[str] | None = None
	if scope.campus_filter is not None:
		allowed = set(frappe.get_all(
			"Student",
			filters={"ags_campus": ("in", scope.campus_filter)},
			pluck="name",
		))

	at_risk = []
	for row in rows:
		if allowed is not None and row.student not in allowed:
			continue
		rate = flt(int(row.present) / int(row.recorded) * 100, 1)
		if rate < flt(threshold_percent):
			at_risk.append({
				"student": row.student,
				"student_name": row.student_name,
				"attendance_percent": rate,
				"present": int(row.present),
				"recorded": int(row.recorded),
				"absences": int(row.recorded) - int(row.present),
			})

	at_risk.sort(key=lambda r: r["attendance_percent"])

	if not at_risk:
		finding.headline = 0.0
		finding.summary = _("No student is below {0}% attendance.").format(
			flt(threshold_percent, 1)
		)
		return finding

	finding.headline = float(len(at_risk))
	finding.rows = at_risk[:limit]
	worst = at_risk[0]
	finding.summary = _(
		"{0} student(s) are below {1}% attendance. The lowest is {2} at {3}% "
		"({4} absences from {5} recorded days)."
	).format(
		len(at_risk), flt(threshold_percent, 1), worst["student_name"],
		worst["attendance_percent"], worst["absences"], worst["recorded"],
	)
	return finding


@analyzer(
	code="declining_classes",
	question="Which classes show declining performance?",
	category="Academic",
	keywords=("class", "declining", "performance", "results", "falling", "worse"),
	roles=ACADEMIC_ROLES,
)
def declining_classes(scope, limit: int = 20, **_params) -> Finding:
	"""Student groups whose average result has fallen against the prior period."""
	midpoint = str(add_months(getdate(scope.to_date), -6))

	def averages(from_date: str, to_date: str) -> dict[str, tuple[float, int]]:
		rows = frappe.db.sql(
			"""
			select ar.student_group as grp,
			       avg(ar.total_score / nullif(ar.maximum_score, 0) * 100) as pct,
			       count(*) as n
			from `tabAssessment Result` ar
			where ar.docstatus = 1 and ar.student_group is not null
			  and ar.maximum_score > 0
			  and ar.creation between %(from_date)s and %(to_date)s
			group by ar.student_group
			""",
			{"from_date": from_date, "to_date": to_date},
			as_dict=True,
		)
		return {r.grp: (flt(r.pct, 1), int(r.n)) for r in rows if r.pct is not None}

	recent = averages(midpoint, scope.to_date)
	earlier = averages(scope.from_date, midpoint)

	finding = Finding(
		code="declining_classes",
		title=_("Classes with declining results"),
		unit="Percent",
	)

	common = set(recent) & set(earlier)
	if not common:
		finding.summary = _(
			"There are not two comparable periods of assessment results yet, so "
			"a trend cannot be measured."
		)
		finding.insufficient_data = True
		return finding

	declining = []
	for group in common:
		now_pct, now_n = recent[group]
		then_pct, then_n = earlier[group]
		change = flt(now_pct - then_pct, 1)
		if change < 0:
			declining.append({
				"student_group": group,
				"recent_average": now_pct,
				"previous_average": then_pct,
				"change": change,
				"recent_results": now_n,
				"previous_results": then_n,
			})

	declining.sort(key=lambda r: r["change"])

	if not declining:
		finding.headline = 0.0
		finding.summary = _("No class average has fallen between the two periods.")
		return finding

	finding.headline = declining[0]["change"]
	finding.rows = declining[:limit]
	worst = declining[0]
	finding.summary = _(
		"{0} class(es) show a lower average than the previous period. The largest "
		"fall is {1}, from {2}% to {3}% ({4} points)."
	).format(
		len(declining), worst["student_group"], worst["previous_average"],
		worst["recent_average"], worst["change"],
	)
	return finding


@analyzer(
	code="teacher_variance",
	question="Which classes sit significantly below the school average?",
	category="Academic",
	keywords=("teacher", "instructor", "below average", "variance", "underperform"),
	roles=TEACHER_REVIEW_ROLES,
	description="Class averages by instructor, expressed as a variance to investigate.",
)
def teacher_variance(scope, deviation_points: float = 10.0, limit: int = 20,
                     **_params) -> Finding:
	"""Instructors whose class averages sit well below the school mean.

	Reported as a gap worth investigating, not a ranking. Subject difficulty and
	cohort intake move these numbers at least as much as teaching does.
	"""
	rows = frappe.db.sql(
		"""
		select
			sgi.instructor,
			i.instructor_name,
			ar.student_group,
			avg(ar.total_score / nullif(ar.maximum_score, 0) * 100) as pct,
			count(*) as n
		from `tabAssessment Result` ar
		inner join `tabStudent Group Instructor` sgi
		        on sgi.parent = ar.student_group and sgi.parenttype = 'Student Group'
		inner join `tabInstructor` i on i.name = sgi.instructor
		where ar.docstatus = 1 and ar.maximum_score > 0
		  and ar.creation between %(from_date)s and %(to_date)s
		group by sgi.instructor, i.instructor_name, ar.student_group
		having count(*) >= 5
		""",
		{"from_date": scope.from_date, "to_date": scope.to_date},
		as_dict=True,
	)

	finding = Finding(
		code="teacher_variance",
		title=_("Class averages below the school mean"),
		unit="Percent",
		notes=[
			_("A class average reflects intake, subject and cohort as well as "
			  "teaching. Treat this as a variance to investigate, not a judgement."),
		],
	)

	if len(rows) < 3:
		finding.summary = _(
			"Only {0} class-instructor combination(s) have at least five results, "
			"which is too few to compare against a school average."
		).format(len(rows))
		finding.insufficient_data = True
		return finding

	school_average = flt(statistics.mean([flt(r.pct) for r in rows]), 1)

	below = [
		{
			"instructor": r.instructor,
			"instructor_name": r.instructor_name,
			"student_group": r.student_group,
			"class_average": flt(r.pct, 1),
			"school_average": school_average,
			"gap": flt(flt(r.pct) - school_average, 1),
			"results": int(r.n),
		}
		for r in rows
		if flt(r.pct) < school_average - flt(deviation_points)
	]
	below.sort(key=lambda r: r["gap"])

	finding.headline = school_average

	if not below:
		finding.summary = _(
			"No class sits more than {0} points below the school average of {1}%."
		).format(flt(deviation_points, 1), school_average)
		return finding

	finding.rows = below[:limit]
	worst = below[0]
	finding.summary = _(
		"The school average is {0}%. {1} class(es) sit more than {2} points below "
		"it. The widest gap is {3} ({4}) at {5}%, {6} points below."
	).format(
		school_average, len(below), flt(deviation_points, 1),
		worst["student_group"], worst["instructor_name"], worst["class_average"],
		abs(worst["gap"]),
	)
	return finding
