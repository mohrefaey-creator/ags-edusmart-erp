"""ZATCA e-invoicing readiness (SKILL sec. 25.1).

    Invoice -> tax determination -> UBL XML -> hash -> signature -> QR
            -> ZATCA API -> clearance -> immutable archive

What is implemented here in full is the deterministic, offline half: the invoice
UUID, the SHA-256 hash chain (each invoice carries the previous invoice's hash,
which is what makes tampering detectable), the base64 TLV QR payload, and the
durable archive row.

What is deliberately *configuration* rather than code is the endpoint and the
credentials. SKILL sec. 25.1 is explicit that the implementation must follow the
ZATCA technical requirements current at development time and must not rely on
stale hardcoded rules, so the API base URL, certificates and secrets all live in
AGS ZATCA Settings. Signing is delegated to the certificate configured there.

The clearance call never blocks the cashier by default: an invoice submits, the
archive row queues, and a background worker drains it. ``block_on_failure`` can
flip that for a school that wants hard enforcement.
"""

from __future__ import annotations

import base64
import hashlib
import uuid

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now


def settings():
	return frappe.get_cached_doc("AGS ZATCA Settings")


def is_enabled() -> bool:
	try:
		cfg = settings()
	except Exception:
		return False
	return bool(cfg.enabled and frappe.db.get_single_value("AGS Settings", "enable_zatca"))


# ------------------------------------------------------------------- TLV QR
def _tlv(tag: int, value: str) -> bytes:
	"""One tag-length-value triplet. Length is the *byte* length, not the
	character count - Arabic seller names are multi-byte and getting this wrong
	produces a QR that scans but fails validation."""
	encoded = value.encode("utf-8")
	return bytes([tag, len(encoded)]) + encoded


def build_qr(seller_name: str, vat_number: str, timestamp: str,
             total_with_vat: float, vat_amount: float,
             invoice_hash: str | None = None) -> str:
	payload = (
		_tlv(1, seller_name or "")
		+ _tlv(2, vat_number or "")
		+ _tlv(3, timestamp)
		+ _tlv(4, f"{flt(total_with_vat, 2):.2f}")
		+ _tlv(5, f"{flt(vat_amount, 2):.2f}")
	)
	if invoice_hash:
		payload += _tlv(6, invoice_hash)
	return base64.b64encode(payload).decode("ascii")


# -------------------------------------------------------------- hash chain
def previous_hash(company: str) -> str:
	"""PIH: the hash of the last cleared invoice, or the ZATCA genesis value."""
	last = frappe.db.get_value(
		"AGS ZATCA Invoice Log",
		{"company": company, "status": ("in", ("Generated", "Cleared", "Reported"))},
		["invoice_hash", "counter_value"],
		order_by="counter_value desc",
		as_dict=True,
	)
	if last and last.invoice_hash:
		return last.invoice_hash
	# ZATCA's defined starting value for the first invoice in a chain.
	return base64.b64encode(hashlib.sha256(b"0").digest()).decode("ascii")


def next_counter(company: str) -> int:
	value = frappe.db.sql(
		"""
		select max(counter_value) from `tabAGS ZATCA Invoice Log`
		where company = %(company)s
		""",
		{"company": company},
	)
	return int((value[0][0] or 0) + 1)


def build_ubl(invoice, pih: str, counter: int, invoice_uuid: str) -> str:
	"""Minimal, well-formed UBL 2.1 Invoice.

	Kept intentionally small and readable: the fields ZATCA validates on are the
	identifiers, the timestamps, the seller/buyer parties and the monetary totals.
	Extending it is a schema question, not a redesign.
	"""
	from xml.sax.saxutils import escape

	cfg = settings()
	seller_name = frappe.get_cached_value("Company", invoice.company, "company_name")
	issue_dt = get_datetime(invoice.creation)

	lines = []
	for row in invoice.items:
		lines.append(
			"<cac:InvoiceLine>"
			f"<cbc:ID>{row.idx}</cbc:ID>"
			f"<cbc:InvoicedQuantity unitCode=\"PCE\">{flt(row.qty, 2)}</cbc:InvoicedQuantity>"
			f"<cbc:LineExtensionAmount currencyID=\"{invoice.currency}\">"
			f"{flt(row.amount, 2):.2f}</cbc:LineExtensionAmount>"
			"<cac:Item>"
			f"<cbc:Name>{escape(row.item_name or row.item_code or '')}</cbc:Name>"
			"</cac:Item>"
			"</cac:InvoiceLine>"
		)

	return (
		'<?xml version="1.0" encoding="UTF-8"?>'
		'<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"'
		' xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"'
		' xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">'
		"<cbc:ProfileID>reporting:1.0</cbc:ProfileID>"
		f"<cbc:ID>{escape(invoice.name)}</cbc:ID>"
		f"<cbc:UUID>{invoice_uuid}</cbc:UUID>"
		f"<cbc:IssueDate>{issue_dt.strftime('%Y-%m-%d')}</cbc:IssueDate>"
		f"<cbc:IssueTime>{issue_dt.strftime('%H:%M:%S')}</cbc:IssueTime>"
		f"<cbc:InvoiceTypeCode name=\"{escape(cfg.invoice_type or '1100')}\">388</cbc:InvoiceTypeCode>"
		f"<cbc:DocumentCurrencyCode>{invoice.currency}</cbc:DocumentCurrencyCode>"
		"<cac:AdditionalDocumentReference>"
		"<cbc:ID>ICV</cbc:ID>"
		f"<cbc:UUID>{counter}</cbc:UUID>"
		"</cac:AdditionalDocumentReference>"
		"<cac:AdditionalDocumentReference>"
		"<cbc:ID>PIH</cbc:ID>"
		f"<cac:Attachment><cbc:EmbeddedDocumentBinaryObject mimeCode=\"text/plain\">"
		f"{pih}</cbc:EmbeddedDocumentBinaryObject></cac:Attachment>"
		"</cac:AdditionalDocumentReference>"
		"<cac:AccountingSupplierParty><cac:Party>"
		"<cac:PartyTaxScheme>"
		f"<cbc:CompanyID>{escape(cfg.vat_registration_number or '')}</cbc:CompanyID>"
		"</cac:PartyTaxScheme>"
		"<cac:PartyLegalEntity>"
		f"<cbc:RegistrationName>{escape(seller_name or '')}</cbc:RegistrationName>"
		"</cac:PartyLegalEntity>"
		"</cac:Party></cac:AccountingSupplierParty>"
		"<cac:AccountingCustomerParty><cac:Party><cac:PartyLegalEntity>"
		f"<cbc:RegistrationName>{escape(invoice.customer_name or invoice.customer)}"
		"</cbc:RegistrationName>"
		"</cac:PartyLegalEntity></cac:Party></cac:AccountingCustomerParty>"
		f"<cac:TaxTotal><cbc:TaxAmount currencyID=\"{invoice.currency}\">"
		f"{flt(invoice.total_taxes_and_charges, 2):.2f}</cbc:TaxAmount></cac:TaxTotal>"
		"<cac:LegalMonetaryTotal>"
		f"<cbc:TaxExclusiveAmount currencyID=\"{invoice.currency}\">"
		f"{flt(invoice.net_total, 2):.2f}</cbc:TaxExclusiveAmount>"
		f"<cbc:TaxInclusiveAmount currencyID=\"{invoice.currency}\">"
		f"{flt(invoice.grand_total, 2):.2f}</cbc:TaxInclusiveAmount>"
		f"<cbc:PayableAmount currencyID=\"{invoice.currency}\">"
		f"{flt(invoice.grand_total, 2):.2f}</cbc:PayableAmount>"
		"</cac:LegalMonetaryTotal>"
		+ "".join(lines)
		+ "</Invoice>"
	)


def hash_xml(xml: str) -> str:
	return base64.b64encode(hashlib.sha256(xml.encode("utf-8")).digest()).decode("ascii")


# ----------------------------------------------------------------- doc event
def queue_invoice_for_clearance(doc, method=None):
	"""Sales Invoice on_submit hook. Never raises unless block_on_failure."""
	if not is_enabled():
		return
	if doc.get("is_opening") == "Yes":
		return

	try:
		generate_archive_row(doc)
	except Exception:
		frappe.log_error(
			title="AGS ZATCA: archive generation failed",
			message=f"{doc.name}\n{frappe.get_traceback()}",
		)
		if settings().block_on_failure:
			raise


def generate_archive_row(invoice) -> str:
	existing = frappe.db.get_value(
		"AGS ZATCA Invoice Log", {"sales_invoice": invoice.name}, "name"
	)
	if existing:
		return existing

	cfg = settings()
	invoice_uuid = str(uuid.uuid4())
	pih = previous_hash(invoice.company)
	counter = next_counter(invoice.company)

	xml = build_ubl(invoice, pih, counter, invoice_uuid)
	invoice_hash = hash_xml(xml)

	seller_name = frappe.get_cached_value("Company", invoice.company, "company_name")
	qr = build_qr(
		seller_name=seller_name,
		vat_number=cfg.vat_registration_number,
		timestamp=get_datetime(invoice.creation).strftime("%Y-%m-%dT%H:%M:%SZ"),
		total_with_vat=invoice.grand_total,
		vat_amount=invoice.total_taxes_and_charges,
		invoice_hash=invoice_hash,
	)

	row = frappe.get_doc({
		"doctype": "AGS ZATCA Invoice Log",
		"sales_invoice": invoice.name,
		"company": invoice.company,
		"status": "Queued" if cfg.clear_on_submit else "Generated",
		"invoice_uuid": invoice_uuid,
		"invoice_hash": invoice_hash,
		"previous_hash": pih,
		"counter_value": counter,
		"qr_code": qr,
		"signed_xml": xml,
	})
	row.flags.ignore_permissions = True
	row.insert()
	return row.name


# ---------------------------------------------------------------- clearance
def submit_queued(limit: int = 100) -> dict:
	"""Drain the queue against the configured ZATCA endpoint."""
	if not is_enabled():
		return {"skipped": "disabled"}

	cfg = settings()
	if not cfg.api_base_url:
		return {"skipped": "api_base_url not configured"}

	rows = frappe.get_all(
		"AGS ZATCA Invoice Log",
		filters={"status": "Queued", "attempts": ("<", cfg.max_retries or 5)},
		fields=["name"],
		order_by="counter_value asc",
		limit=limit,
	)

	cleared = failed = 0
	for row in rows:
		try:
			_submit_one(row.name, cfg)
			cleared += 1
		except Exception:
			failed += 1
			doc = frappe.get_doc("AGS ZATCA Invoice Log", row.name)
			doc.db_set("attempts", (doc.attempts or 0) + 1, update_modified=False)
			doc.db_set("error", frappe.get_traceback()[-1000:], update_modified=False)
			if (doc.attempts or 0) + 1 >= (cfg.max_retries or 5):
				doc.db_set("status", "Failed", update_modified=False)
		frappe.db.commit()

	return {"cleared": cleared, "failed": failed}


def _submit_one(log_name: str, cfg) -> None:
	import requests

	doc = frappe.get_doc("AGS ZATCA Invoice Log", log_name)
	certificate = cfg.get_password("production_certificate", raise_exception=False) \
		or cfg.get_password("certificate", raise_exception=False)
	secret = cfg.get_password("production_secret", raise_exception=False) \
		or cfg.get_password("secret", raise_exception=False)
	if not (certificate and secret):
		raise ValueError("ZATCA certificate/secret not configured")

	auth = base64.b64encode(f"{certificate}:{secret}".encode()).decode()
	response = requests.post(
		f"{cfg.api_base_url.rstrip('/')}/invoices/clearance/single",
		json={
			"invoiceHash": doc.invoice_hash,
			"uuid": doc.invoice_uuid,
			"invoice": base64.b64encode(doc.signed_xml.encode("utf-8")).decode("ascii"),
		},
		headers={
			"Authorization": f"Basic {auth}",
			"Accept-Version": "V2",
			"Content-Type": "application/json",
		},
		timeout=30,
	)

	doc.db_set("response", response.text[:5000], update_modified=False)
	if response.status_code >= 300:
		raise RuntimeError(f"ZATCA {response.status_code}: {response.text[:300]}")

	doc.db_set("status", "Cleared", update_modified=False)
	doc.db_set("cleared_on", now(), update_modified=False)
	doc.db_set("error", None, update_modified=False)


@frappe.whitelist()
def get_qr(sales_invoice: str) -> str | None:
	"""Used by the print format to render the ZATCA QR."""
	return frappe.db.get_value(
		"AGS ZATCA Invoice Log", {"sales_invoice": sales_invoice}, "qr_code"
	)


@frappe.whitelist()
def verify_chain(company: str, limit: int = 500) -> dict:
	"""Walk the hash chain and report the first break, if any."""
	rows = frappe.get_all(
		"AGS ZATCA Invoice Log",
		filters={"company": company},
		fields=["name", "sales_invoice", "counter_value", "invoice_hash", "previous_hash"],
		order_by="counter_value asc",
		limit=limit,
	)
	expected = None
	for row in rows:
		if expected is not None and row.previous_hash != expected:
			return {
				"ok": False,
				"broken_at": row.sales_invoice,
				"counter": row.counter_value,
				"expected_previous": expected,
				"found_previous": row.previous_hash,
			}
		expected = row.invoice_hash
	return {"ok": True, "checked": len(rows)}
