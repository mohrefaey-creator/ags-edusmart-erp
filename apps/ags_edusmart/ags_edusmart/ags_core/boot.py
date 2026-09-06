# Session bootinfo: the desk reads this once at load, so anything the AGS UI
# needs on every page belongs here rather than in a per-page call.
import frappe

from ags_edusmart.ags_core.permissions import get_user_scope


def boot_session(bootinfo):
	user = frappe.session.user
	if user == "Guest":
		return

	scope = get_user_scope(user)
	bootinfo.ags = {
		"unrestricted": scope["unrestricted"],
		"campuses": scope["campuses"],
		"default_campus": frappe.db.get_value("AGS User Scope", {"user": user}, "default_campus"),
		"settings": _public_settings(),
	}


def _public_settings():
	# Only flags the client actually branches on. Gateway URLs and keys stay server side.
	fields = [
		"default_company",
		"default_campus",
		"current_academic_year",
		"enable_deferred_revenue",
		"enable_commitment_accounting",
		"commitment_action",
		"enable_late_fees",
		"enable_zatca",
		"default_vat_rate",
	]
	try:
		settings = frappe.get_cached_doc("AGS Settings")
	except Exception:
		return {}
	return {field: settings.get(field) for field in fields}
