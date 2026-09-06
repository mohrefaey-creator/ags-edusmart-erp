"""AGS Core - the shared organisational model (SKILL sec. 4).

Every other module hangs its dimensions off these two masters, so this module is
generated first and nothing here may depend on a later one.
"""

from doctype_builder import SYS, column, doctype, f, perm, readonly_perm, section

MODULE = "AGS Core"

CAMPUS_PERMS = [
	perm(SYS),
	perm("AGS Group Executive", write=False, create=False, delete=False),
	readonly_perm("AGS Principal"),
	readonly_perm("AGS Finance Manager"),
	readonly_perm("Employee"),
]

CAMPUS_CONTROLLER = '''import frappe
from frappe import _
from frappe.model.document import Document


class AGSCampus(Document):
	def validate(self):
		self.validate_cost_center_company()

	def validate_cost_center_company(self):
		"""A campus pointing at a cost center in another company would split the
		ledger silently, so this is a hard stop rather than a warning."""
		if not self.cost_center:
			return
		cc_company = frappe.db.get_value("Cost Center", self.cost_center, "company")
		if cc_company and cc_company != self.company:
			frappe.throw(
				_("Cost Center {0} belongs to company {1}, but this campus belongs to {2}.").format(
					self.cost_center, cc_company, self.company
				),
				title=_("Company Mismatch"),
			)

	def on_trash(self):
		linked = frappe.db.count("AGS School Division", {"campus": self.name})
		if linked:
			frappe.throw(
				_("Cannot delete: {0} school division(s) still reference this campus.").format(linked)
			)
'''

DIVISION_CONTROLLER = '''import frappe
from frappe import _
from frappe.model.document import Document

from ags_edusmart.utils.grades import parse_grade_level


class AGSSchoolDivision(Document):
	def validate(self):
		self.validate_grade_range()

	def validate_grade_range(self):
		"""Programs carry no intrinsic order in Frappe Education, so the bounds
		are compared on the parsed year level rather than on the name."""
		if not (self.from_grade and self.to_grade):
			return
		low = parse_grade_level(self.from_grade)
		high = parse_grade_level(self.to_grade)
		if low is not None and high is not None and low > high:
			frappe.throw(
				_("From Grade ({0}) is above To Grade ({1}).").format(self.from_grade, self.to_grade)
			)
'''

USER_SCOPE_CONTROLLER = '''import frappe
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
'''


def specs() -> list[tuple[dict, str | None]]:
	out: list[tuple[dict, str | None]] = []

	# ------------------------------------------------------------------ Campus
	out.append((doctype(
		"AGS Campus", MODULE,
		[
			section("sb_identity"),
			f("campus_name", "Data", "Campus Name", reqd=1, in_list_view=1),
			f("campus_name_ar", "Data", "Campus Name (Arabic)"),
			f("abbr", "Data", "Abbreviation", reqd=1, unique=1, in_list_view=1,
			  description="Short code used in naming series and report headers."),
			column("cb_identity"),
			f("company", "Link", "Company", options="Company", reqd=1, in_list_view=1,
			  search_index=1),
			f("is_active", "Check", "Active", default="1", in_list_view=1),
			f("gender_type", "Select", "Gender Type", options="Mixed\nBoys\nGirls",
			  default="Mixed"),

			section("sb_accounting", "Accounting"),
			f("cost_center", "Link", "Cost Center", options="Cost Center",
			  description="Parent cost center for every division and department on this campus."),
			f("default_warehouse", "Link", "Default Store", options="Warehouse"),
			column("cb_accounting"),
			f("default_receivable_account", "Link", "Student Receivable Account", options="Account"),
			f("default_income_account", "Link", "Default Fee Income Account", options="Account"),

			section("sb_contact", "Location & Contact"),
			f("city", "Data", "City"),
			f("region", "Data", "Region"),
			f("address_line", "Small Text", "Address"),
			column("cb_contact"),
			f("phone", "Data", "Phone", options="Phone"),
			f("email", "Data", "Email", options="Email"),
			f("principal", "Link", "Principal", options="Employee"),
		],
		autoname="field:campus_name",
		title_field="campus_name",
		search_fields="abbr,company,city",
		permissions=CAMPUS_PERMS,
		description="A physical campus, sitting between the legal entity and its school divisions.",
	), CAMPUS_CONTROLLER))

	# --------------------------------------------------------- School Division
	out.append((doctype(
		"AGS School Division", MODULE,
		[
			section("sb_identity"),
			f("division_name", "Data", "Division Name", reqd=1, in_list_view=1),
			f("division_name_ar", "Data", "Division Name (Arabic)"),
			f("abbr", "Data", "Abbreviation", reqd=1),
			column("cb_identity"),
			f("campus", "Link", "Campus", options="AGS Campus", reqd=1, in_list_view=1,
			  search_index=1),
			f("company", "Data", "Company", fetch_from="campus.company", read_only=1),
			f("division_type", "Select", "Division Type",
			  options="Kindergarten\nPrimary\nMiddle\nSecondary\nSenior",
			  reqd=1, in_list_view=1),
			f("is_active", "Check", "Active", default="1"),

			section("sb_academic", "Academic Range"),
			f("from_grade", "Link", "From Grade", options="Program"),
			f("to_grade", "Link", "To Grade", options="Program"),
			column("cb_academic"),
			f("head_of_division", "Link", "Head of Division", options="Employee"),
			f("cost_center", "Link", "Cost Center", options="Cost Center"),
		],
		autoname="format:{campus}-{abbr}",
		title_field="division_name",
		search_fields="campus,division_type",
		permissions=CAMPUS_PERMS,
	), DIVISION_CONTROLLER))

	# ----------------------------------------------------------- User scoping
	out.append((doctype(
		"AGS Campus Link", MODULE,
		[f("campus", "Link", "Campus", options="AGS Campus", reqd=1, in_list_view=1)],
		is_child=True,
	), None))

	out.append((doctype(
		"AGS User Scope", MODULE,
		[
			f("user", "Link", "User", options="User", reqd=1, unique=1, in_list_view=1),
			f("full_name", "Data", "Full Name", fetch_from="user.full_name", read_only=1,
			  in_list_view=1),
			section("sb_scope", "Access Scope"),
			f("all_campuses", "Check", "Access All Campuses", default="0",
			  description="Group-level roles (CEO, CFO, Auditor) normally have this set."),
			f("campuses", "Table MultiSelect", "Campuses", options="AGS Campus Link",
			  depends_on="eval:!doc.all_campuses"),
			column("cb_scope"),
			f("default_campus", "Link", "Default Campus", options="AGS Campus",
			  description="Pre-selected on new documents."),
			f("company", "Link", "Company", options="Company"),
		],
		autoname="field:user",
		title_field="full_name",
		permissions=[perm(SYS)],
		description="Campus row scoping. A user with no scope row sees no campus-bound records.",
	), USER_SCOPE_CONTROLLER))

	# ------------------------------------------------------------ AGS Settings
	out.append((doctype(
		"AGS Settings", MODULE,
		[
			section("sb_org", "Organisation"),
			f("default_company", "Link", "Default Company", options="Company"),
			f("default_campus", "Link", "Default Campus", options="AGS Campus"),
			column("cb_org"),
			f("current_academic_year", "Link", "Current Academic Year", options="Academic Year"),

			section("sb_revenue", "Revenue Recognition"),
			f("enable_deferred_revenue", "Check", "Enable Deferred Tuition Revenue", default="1",
			  description="Tuition collected up front is parked in a liability and released monthly (SKILL sec. 5.4)."),
			f("deferred_revenue_account", "Link", "Deferred Tuition Revenue Account",
			  options="Account", depends_on="enable_deferred_revenue"),
			column("cb_revenue"),
			f("recognition_basis", "Select", "Recognition Basis",
			  options="Monthly Straight Line\nBy Academic Term\nBy Teaching Days",
			  default="Monthly Straight Line", depends_on="enable_deferred_revenue"),

			section("sb_budget", "Budget Control"),
			f("enable_commitment_accounting", "Check", "Enable Commitment Accounting", default="1",
			  description="Approved requests and open orders consume budget before the invoice lands (SKILL sec. 7.1)."),
			f("commitment_action", "Select", "Action If Committed Budget Exceeded",
			  options="Warn\nStop\nRequire Override Approval", default="Warn",
			  depends_on="enable_commitment_accounting"),

			section("sb_fees", "Fees & Collections"),
			f("enable_late_fees", "Check", "Enable Late Fees", default="0"),
			f("late_fee_item", "Link", "Late Fee Item", options="Item",
			  depends_on="enable_late_fees"),
			f("late_fee_grace_days", "Int", "Grace Days", default="7",
			  depends_on="enable_late_fees"),
			column("cb_fees"),
			f("late_fee_type", "Select", "Late Fee Type",
			  options="Fixed Amount\nPercent of Overdue", default="Fixed Amount",
			  depends_on="enable_late_fees"),
			f("late_fee_value", "Float", "Late Fee Value", depends_on="enable_late_fees"),
			f("consolidate_sibling_invoices", "Check",
			  "Consolidate Sibling Invoices on Payer", default="0"),

			section("sb_notify", "Notifications"),
			f("enable_notifications", "Check", "Enable Notification Engine", default="1"),
			f("default_channels", "Small Text", "Default Channels", default="In-App, Email",
			  description="Comma separated. Supported: In-App, Email, SMS, WhatsApp."),
			column("cb_notify"),
			f("sms_gateway_url", "Data", "SMS Gateway URL"),
			f("whatsapp_gateway_url", "Data", "WhatsApp Gateway URL"),

			section("sb_zatca", "Saudi Localization"),
			f("enable_zatca", "Check", "Enable ZATCA e-Invoicing", default="0",
			  description="Phase-2 clearance. Requires certificates in AGS ZATCA Settings."),
			f("default_vat_rate", "Percent", "Default VAT Rate", default="15"),
			column("cb_zatca"),
			f("enable_gosi", "Check", "Enable GOSI Payroll Components", default="1"),
		],
		is_single=True,
		permissions=[perm(SYS), readonly_perm("AGS Finance Manager")],
	), None))

	return out
