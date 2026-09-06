# Fees and payments: what is due, what is overdue, and the full statement.
import frappe

from ags_edusmart.api.portal import my_installments, my_outstanding, my_statement

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/parent/fees"
		raise frappe.Redirect

	context.no_cache = 1
	context.show_sidebar = True
	try:
		context.summary = my_outstanding()
		context.installments = my_installments()
		context.statement = my_statement()
		context.error = None
	except frappe.PermissionError as exc:
		context.summary = None
		context.installments = []
		context.statement = None
		context.error = str(exc)
	return context
