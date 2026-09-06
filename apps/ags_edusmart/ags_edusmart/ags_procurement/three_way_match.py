"""Three-way matching: PO <-> Goods Receipt <-> Supplier Invoice (SKILL sec. 8.6).

Exceptions are recorded as documents rather than raised as bare errors, because
finance needs the list of what is blocking payment and an audit trail of who
overrode what. A Blocking exception stops the invoice; a Warning records and
lets it through.

Tolerances are read from the company's existing ERPNext settings where they
exist, so this does not become a second place to configure the same number.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from ags_edusmart.utils.dimensions import campus_of

# Fallbacks when the company has not set its own tolerance.
DEFAULT_PRICE_TOLERANCE_PERCENT = 2.0
DEFAULT_QTY_TOLERANCE_PERCENT = 0.0


def validate_three_way_match(doc, method=None):
	if doc.get("is_return") or doc.get("update_stock") is None:
		pass  # returns and stand-alone invoices are still checked for duplicates

	exceptions: list[dict] = []
	exceptions.extend(_check_duplicate(doc))
	exceptions.extend(_check_against_orders(doc))
	exceptions.extend(_check_against_receipts(doc))

	if not exceptions:
		_clear_stale_exceptions(doc)
		return

	blocking = [e for e in exceptions if e["severity"] == "Blocking"]
	_record(doc, exceptions)

	if blocking and not _override_allowed(doc):
		frappe.throw(
			_("{0} blocking three-way match exception(s) on this invoice:<br>{1}").format(
				len(blocking),
				"<br>".join(f"- {e['exception_type']}: {e['detail']}" for e in blocking),
			),
			title=_("Three-Way Match Failed"),
		)


def _override_allowed(doc) -> bool:
	"""An explicitly resolved or overridden exception set unblocks the invoice."""
	open_blocking = frappe.db.count(
		"AGS Three Way Match Exception",
		{"purchase_invoice": doc.name, "severity": "Blocking", "status": "Open"},
	)
	return open_blocking == 0 and bool(doc.name and not doc.is_new())


# ------------------------------------------------------------------- checks
def _check_duplicate(doc) -> list[dict]:
	if not doc.get("bill_no"):
		return []
	duplicate = frappe.db.get_value(
		"Purchase Invoice",
		{
			"supplier": doc.supplier,
			"bill_no": doc.bill_no,
			"docstatus": 1,
			"name": ("!=", doc.name),
		},
		"name",
	)
	if not duplicate:
		return []
	return [{
		"exception_type": "Duplicate Invoice",
		"severity": "Blocking",
		"detail": _("Supplier bill {0} is already booked as {1}.").format(
			doc.bill_no, duplicate
		),
		"expected_value": duplicate,
		"actual_value": doc.bill_no,
		"variance_amount": 0,
		"item_code": None,
		"purchase_order": None,
		"purchase_receipt": None,
	}]


def _check_against_orders(doc) -> list[dict]:
	out: list[dict] = []
	price_tol = _price_tolerance(doc.company)

	for row in doc.items:
		order = row.get("purchase_order")
		order_item = row.get("po_detail")
		if not (order and order_item):
			continue

		po_row = frappe.db.get_value(
			"Purchase Order Item", order_item,
			["rate", "qty", "received_qty", "billed_amt", "amount", "item_code"],
			as_dict=True,
		)
		if not po_row:
			continue

		po_supplier = frappe.db.get_value("Purchase Order", order, "supplier")
		if po_supplier and po_supplier != doc.supplier:
			out.append(_exc(
				"Supplier Mismatch", "Blocking", row.item_code, order, None,
				po_supplier, doc.supplier, 0,
				_("Order {0} belongs to {1}.").format(order, po_supplier),
			))

		# Price variance
		if flt(po_row.rate):
			variance = (flt(row.rate) - flt(po_row.rate)) / flt(po_row.rate) * 100
			if variance > price_tol:
				out.append(_exc(
					"Price Variance", "Blocking", row.item_code, order, None,
					po_row.rate, row.rate,
					flt((flt(row.rate) - flt(po_row.rate)) * flt(row.qty), 2),
					_("Invoiced rate {0} exceeds ordered rate {1} by {2}%.").format(
						row.rate, po_row.rate, flt(variance, 2)
					),
				))

		# Over-billing against the ordered value
		already = flt(po_row.billed_amt)
		if flt(po_row.amount) and already + flt(row.amount) > flt(po_row.amount) + 0.01:
			out.append(_exc(
				"Over Billing", "Blocking", row.item_code, order, None,
				po_row.amount, flt(already + flt(row.amount), 2),
				flt(already + flt(row.amount) - flt(po_row.amount), 2),
				_("Billing {0} against an ordered value of {1}.").format(
					flt(already + flt(row.amount), 2), po_row.amount
				),
			))

	return out


def _check_against_receipts(doc) -> list[dict]:
	out: list[dict] = []
	qty_tol = DEFAULT_QTY_TOLERANCE_PERCENT

	for row in doc.items:
		order_item = row.get("po_detail")
		if not order_item:
			continue
		# Invoicing more than was received is the classic school-supplies leak.
		received = flt(
			frappe.db.get_value("Purchase Order Item", order_item, "received_qty")
		)
		if received <= 0 and not row.get("purchase_receipt"):
			out.append(_exc(
				"Unreceived Item", "Blocking", row.item_code,
				row.get("purchase_order"), None, 0, row.qty, 0,
				_("No goods receipt exists for {0}.").format(row.item_code),
			))
			continue

		if received and flt(row.qty) > received * (1 + qty_tol / 100) + 0.001:
			out.append(_exc(
				"Quantity Variance", "Blocking", row.item_code,
				row.get("purchase_order"), row.get("purchase_receipt"),
				received, row.qty,
				flt((flt(row.qty) - received) * flt(row.rate), 2),
				_("Invoiced {0} but only {1} received.").format(row.qty, received),
			))

	return out


def _price_tolerance(company: str) -> float:
	value = frappe.db.get_single_value("Buying Settings", "over_billing_allowance")
	return flt(value) or DEFAULT_PRICE_TOLERANCE_PERCENT


def _exc(kind, severity, item_code, order, receipt, expected, actual, variance, detail):
	return {
		"exception_type": kind,
		"severity": severity,
		"item_code": item_code,
		"purchase_order": order,
		"purchase_receipt": receipt,
		"expected_value": str(expected),
		"actual_value": str(actual),
		"variance_amount": variance,
		"detail": detail,
	}


# ------------------------------------------------------------------ persist
def _record(doc, exceptions: list[dict]) -> None:
	_clear_stale_exceptions(doc)
	for exc in exceptions:
		if frappe.db.exists("AGS Three Way Match Exception", {
			"purchase_invoice": doc.name,
			"exception_type": exc["exception_type"],
			"item_code": exc["item_code"],
			"status": "Open",
		}):
			continue
		row = frappe.get_doc({
			"doctype": "AGS Three Way Match Exception",
			"purchase_invoice": doc.name,
			"purchase_order": exc["purchase_order"],
			"purchase_receipt": exc["purchase_receipt"],
			"supplier": doc.supplier,
			"company": doc.company,
			"campus": campus_of(doc),
			"exception_type": exc["exception_type"],
			"severity": exc["severity"],
			"item_code": exc["item_code"],
			"expected_value": exc["expected_value"],
			"actual_value": exc["actual_value"],
			"variance_amount": exc["variance_amount"],
			"status": "Open",
			"resolution_notes": exc["detail"],
		})
		row.flags.ignore_permissions = True
		row.insert()


def _clear_stale_exceptions(doc) -> None:
	"""Drop open exceptions from a previous save of the same draft invoice."""
	if doc.is_new():
		return
	frappe.db.delete("AGS Three Way Match Exception", {
		"purchase_invoice": doc.name,
		"status": "Open",
	})


@frappe.whitelist()
def resolve(exception_name: str, notes: str, override: bool = False) -> str:
	from frappe.utils import now

	exc = frappe.get_doc("AGS Three Way Match Exception", exception_name)
	exc.status = "Overridden" if override else "Resolved"
	exc.resolved_by = frappe.session.user
	exc.resolved_on = now()
	exc.resolution_notes = notes
	exc.flags.ignore_permissions = True
	exc.save()
	return exc.status
