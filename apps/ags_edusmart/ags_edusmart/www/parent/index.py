# Parent portal landing page.
#
# Context is resolved server-side from the logged-in user; nothing identifying
# is accepted from the query string, so a parent cannot read another family's
# data by editing a URL.
import frappe

from ags_edusmart.api.portal import my_children, my_outstanding

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/parent"
		raise frappe.Redirect

	context.no_cache = 1
	context.show_sidebar = True
	try:
		context.children = my_children()
		context.summary = my_outstanding()
		context.error = None
	except frappe.PermissionError as exc:
		# A staff member who wandered in, or a parent whose guardian record is
		# not linked yet. Say so plainly rather than showing an empty page.
		context.children = []
		context.summary = None
		context.error = str(exc)
	return context
