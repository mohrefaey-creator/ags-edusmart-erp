# Employee self-service (SKILL sec. 22).
import frappe

from ags_edusmart.api.portal import my_assets, my_profile, my_requests

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/staff"
		raise frappe.Redirect

	context.no_cache = 1
	context.show_sidebar = True
	try:
		context.profile = my_profile()
		context.assets = my_assets()
		context.requests = my_requests()
		context.error = None
	except frappe.PermissionError as exc:
		context.profile = None
		context.assets = []
		context.requests = []
		context.error = str(exc)
	return context
