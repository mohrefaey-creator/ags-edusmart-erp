import frappe
from frappe import _
from frappe.model.document import Document

from ags_edusmart.ags_core.permissions import clear_scope_cache


class AGSUserScope(Document):
	def validate(self):
		if not self.all_campuses and not self.campuses:
			frappe.throw(
				_("Grant at least one campus, or tick Access All Campuses."),
				title=_("Empty Scope"),
			)
		if self.default_campus and not self.all_campuses:
			allowed = {row.campus for row in self.campuses}
			if self.default_campus not in allowed:
				frappe.throw(
					_("Default Campus {0} is not in the granted campus list.").format(
						self.default_campus
					)
				)

	def on_update(self):
		clear_scope_cache(self.user)

	def on_trash(self):
		clear_scope_cache(self.user)
