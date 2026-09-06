"""Whitelisted entry points for the AI layer.

Three ways in, all funnelling through the same scope resolution and the same
audit log:

* ``ask`` — natural language, routed to an analyzer.
* ``run`` — a named analysis, for dashboards and saved views.
* ``catalogue`` — what this user is allowed to ask, which is what makes the
  feature discoverable without a model guessing at its own capabilities.
"""

from __future__ import annotations

import frappe
from frappe import _

from ags_edusmart.ags_ai import narrator, registry, router
from ags_edusmart.ags_ai.scope import resolve


@frappe.whitelist()
def catalogue(company: str | None = None, campus: str | None = None) -> dict:
	"""The questions this user may ask, grouped by category."""
	scope = resolve(company=company, campus=campus)
	grouped: dict[str, list[dict]] = {}
	for item in registry.all_analyzers(scope):
		grouped.setdefault(item.category, []).append({
			"code": item.code,
			"question": _(item.question),
			"description": item.description,
		})
	return {"scope": scope.describe(), "categories": grouped}


@frappe.whitelist()
def ask(question: str, company: str | None = None, campus: str | None = None,
        academic_year: str | None = None, from_date: str | None = None,
        to_date: str | None = None, narrate: bool = True) -> dict:
	"""Answer a natural-language question, or say honestly that it cannot."""
	if not (question or "").strip():
		frappe.throw(_("Ask a question."))

	scope = resolve(
		company=company, campus=campus, academic_year=academic_year,
		from_date=from_date, to_date=to_date,
	)
	decision = router.route(question, scope)

	if not decision.matched:
		# Refusing clearly beats answering the wrong question. The suggestions
		# are already permission-filtered.
		return {
			"answered": False,
			"question": question,
			"confidence": decision.confidence,
			"message": _(
				"I could not match that to an analysis I can run. Here is what I "
				"can answer for you."
			),
			"suggestions": [
				{"code": a.code, "question": _(a.question), "category": a.category}
				for a in decision.alternatives
			],
			"scope": scope.describe(),
		}

	finding = registry.run(decision.analyzer.code, scope)
	payload = finding.to_dict()
	payload["narrative"] = (
		narrator.narrate(finding) if frappe.utils.cint(narrate)
		else narrator.compose(finding)
	)

	return {
		"answered": True,
		"question": question,
		"matched": {
			"code": decision.analyzer.code,
			"question": _(decision.analyzer.question),
			"category": decision.analyzer.category,
		},
		"confidence": decision.confidence,
		"alternatives": [
			{"code": a.code, "question": _(a.question)} for a in decision.alternatives
		],
		"finding": payload,
		"scope": scope.describe(),
	}


@frappe.whitelist()
def run(code: str, company: str | None = None, campus: str | None = None,
        academic_year: str | None = None, from_date: str | None = None,
        to_date: str | None = None, narrate: bool = True, **params) -> dict:
	"""Run one named analysis. Used by dashboards and scheduled briefings."""
	scope = resolve(
		company=company, campus=campus, academic_year=academic_year,
		from_date=from_date, to_date=to_date,
	)
	finding = registry.run(code, scope, params)
	payload = finding.to_dict()
	payload["narrative"] = (
		narrator.narrate(finding) if frappe.utils.cint(narrate)
		else narrator.compose(finding)
	)
	return {"finding": payload, "scope": scope.describe()}


@frappe.whitelist()
def briefing(company: str | None = None, campus: str | None = None) -> dict:
	"""A role-appropriate set of findings for a dashboard landing page.

	Each analysis is run independently and a failure is reported rather than
	swallowed: a briefing that silently drops the collections figure is worse
	than one that says it could not compute it.
	"""
	scope = resolve(company=company, campus=campus)
	wanted = [
		"outstanding_tuition", "collection_performance", "margin_drivers",
		"budget_overrun", "delayed_orders", "stockout_forecast",
		"expiring_documents", "attendance_risk",
	]

	findings, skipped = [], []
	for code in wanted:
		item = registry.REGISTRY.get(code) or (registry.load_all() or registry.REGISTRY.get(code))
		if not item or not item.may_run(scope):
			continue
		try:
			finding = registry.run(code, scope)
			payload = finding.to_dict()
			payload["narrative"] = narrator.compose(finding)
			findings.append(payload)
		except frappe.PermissionError:
			continue
		except Exception:
			frappe.log_error(
				title="AGS AI: briefing item failed",
				message=f"{code}\n{frappe.get_traceback()}",
			)
			skipped.append(code)

	return {"scope": scope.describe(), "findings": findings, "unavailable": skipped}
