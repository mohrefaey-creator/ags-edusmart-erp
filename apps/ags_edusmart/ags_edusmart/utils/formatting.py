"""Presentation helpers shared by the portal, print formats and notifications."""

from __future__ import annotations

import frappe
from frappe.utils import fmt_money as _fmt_money

# Identifier shapes that the Unicode bidi algorithm reorders inside an RTL
# document. A leading digit run followed by a neutral and then letters is the
# dangerous case: class "1-A" renders as "A-1". Once a strong Latin letter comes
# first ("5B3", "12BSAT1") the whole run resolves LTR and is already safe.
#
# The wrapper is a no-op on safe shapes, so it is cheaper to apply it to any
# identifier-shaped value than to audit each one. It must NOT be applied to a
# slot that can hold prose (it would force LTR onto Arabic), nor to a formatted
# currency amount (it moves the currency symbol to the wrong side).


def fmt_money(value, currency: str | None = None) -> str:
	"""Currency for display. Never wrapped in a bidi isolate - see above."""
	if value is None:
		return ""
	return _fmt_money(value, currency=currency or _default_currency())


def _default_currency() -> str:
	return frappe.db.get_default("currency") or "SAR"


def bidi_code(value: str | None) -> str:
	"""Wrap an identifier so RTL layout cannot reorder it.

	``unicode-bidi: isolate`` alone is not enough - without ``direction: ltr``
	the run still inherits RTL and still flips. Both live in the ``.code`` class
	shipped in the portal stylesheet.
	"""
	if value is None or value == "":
		return ""
	return f'<span class="code">{frappe.utils.escape_html(str(value))}</span>'


def money_words(value, currency: str | None = None) -> str:
	from frappe.utils import money_in_words

	return money_in_words(value, currency or _default_currency())
