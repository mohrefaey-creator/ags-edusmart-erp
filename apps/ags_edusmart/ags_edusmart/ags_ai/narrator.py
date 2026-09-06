"""Turn a structured Finding into prose.

The division of labour is the whole point of this module:

* **The analyzer produces every number.** It reads the ledger.
* **The narrator only phrases them.** It never queries anything, and it is
  handed a finished Finding.

That means a misbehaving or unavailable language model can produce clumsy
English, but it cannot produce a wrong figure, cannot reach data outside the
caller's scope, and cannot invent a payer's name. It also means the feature works
with no model configured at all - the deterministic path below is the default,
not a degraded fallback nobody tested.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import flt

from ags_edusmart.ags_ai.registry import Finding

ARROW = {"up": "↑", "down": "↓", "flat": "→"}


def narrate(finding: Finding, language: str | None = None) -> str:
	"""Prose for a finding. Uses a model only if one is configured and enabled."""
	deterministic = compose(finding, language)

	settings = _settings()
	if not settings or not settings.get("enable_narration"):
		return deterministic

	try:
		enriched = _narrate_with_model(finding, deterministic, settings, language)
		return enriched or deterministic
	except Exception:
		# Narration is a nicety. A model outage must not take the answer with it.
		frappe.log_error(
			title="AGS AI: narration failed",
			message=f"{finding.code}\n{frappe.get_traceback()}",
		)
		return deterministic


def compose(finding: Finding, language: str | None = None) -> str:
	"""Deterministic narration, assembled from the finding itself."""
	lines: list[str] = []

	if finding.summary:
		lines.append(finding.summary)

	if finding.drivers:
		lines.append("")
		lines.append(_("Main drivers:"))
		for driver in finding.drivers:
			lines.append(
				"  {arrow} {label}  {pct:+.1f}%  ({share:.0f}% of the movement)".format(
					arrow=ARROW.get(driver.direction, "→"),
					label=driver.label,
					pct=flt(driver.change_percent, 1),
					share=flt(driver.contribution_percent, 0),
				)
			)

	if finding.insufficient_data:
		lines.append("")
		lines.append(_("There is not enough data to answer this confidently yet."))

	for note in finding.notes:
		lines.append("")
		lines.append(f"— {note}")

	if finding.scope_description:
		lines.append("")
		lines.append(_("Basis: {0}").format(finding.scope_description))

	return "\n".join(lines).strip()


def _settings() -> dict | None:
	try:
		doc = frappe.get_cached_doc("AGS AI Settings")
	except Exception:
		return None
	return {
		"enable_narration": doc.enable_narration,
		"provider": doc.provider,
		"model": doc.model,
		"api_base": doc.api_base,
		"max_output_tokens": doc.max_output_tokens,
		"doc": doc,
	}


def _narrate_with_model(finding: Finding, deterministic: str, settings: dict,
                        language: str | None) -> str | None:
	"""Ask the configured model to phrase an already-computed finding.

	The payload carries only the finding. No credentials, no query access, and
	no identifying data beyond what the analyzer already returned to this user -
	which they are, by construction, permitted to see.
	"""
	api_key = settings["doc"].get_password("api_key", raise_exception=False)
	if not api_key:
		return None

	language = language or frappe.local.lang or "en"
	payload = json.dumps(finding.to_dict(), default=str, ensure_ascii=False)

	instruction = (
		"You are summarising a finance/operations finding for a school ERP. "
		"Rewrite the supplied analysis as two or three short sentences for a "
		"school executive.\n"
		"Rules, without exception:\n"
		"- Use ONLY the numbers present in the JSON. Never compute, round "
		"differently, estimate, or introduce a figure that is not there.\n"
		"- If `insufficient_data` is true, say plainly that the data is not "
		"sufficient yet. Do not speculate about what the answer might be.\n"
		"- Do not invent causes. The `drivers` array is the only causal "
		"information available.\n"
		"- Keep every name and identifier exactly as written.\n"
		f"- Reply in {'Arabic' if language.startswith('ar') else 'English'}.\n"
	)

	provider = (settings["provider"] or "Anthropic").lower()
	if provider == "anthropic":
		return _call_anthropic(settings, api_key, instruction, payload)
	if provider == "openai-compatible":
		return _call_openai_compatible(settings, api_key, instruction, payload)
	return None


def _call_anthropic(settings: dict, api_key: str, instruction: str,
                    payload: str) -> str | None:
	import requests

	base = (settings["api_base"] or "https://api.anthropic.com").rstrip("/")
	response = requests.post(
		f"{base}/v1/messages",
		headers={
			"x-api-key": api_key,
			"anthropic-version": "2023-06-01",
			"content-type": "application/json",
		},
		json={
			"model": settings["model"] or "claude-sonnet-5",
			"max_tokens": int(settings["max_output_tokens"] or 400),
			"system": instruction,
			"messages": [{"role": "user", "content": payload}],
		},
		timeout=20,
	)
	response.raise_for_status()
	blocks = response.json().get("content") or []
	text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
	return text.strip() or None


def _call_openai_compatible(settings: dict, api_key: str, instruction: str,
                            payload: str) -> str | None:
	import requests

	base = (settings["api_base"] or "https://api.openai.com/v1").rstrip("/")
	response = requests.post(
		f"{base}/chat/completions",
		headers={
			"Authorization": f"Bearer {api_key}",
			"Content-Type": "application/json",
		},
		json={
			"model": settings["model"] or "gpt-4o-mini",
			"max_tokens": int(settings["max_output_tokens"] or 400),
			"messages": [
				{"role": "system", "content": instruction},
				{"role": "user", "content": payload},
			],
		},
		timeout=20,
	)
	response.raise_for_status()
	choices = response.json().get("choices") or []
	if not choices:
		return None
	return (choices[0].get("message", {}).get("content") or "").strip() or None
