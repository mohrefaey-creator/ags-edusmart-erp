# Align fee plan currency with the company currency.
#
# For a Link-to-Currency field, Frappe applies the *user* default (Global
# Defaults, INR out of the box) ahead of the DocType field's own default. Plans
# created before AGSFeePlan.set_defaults started aligning the value explicitly
# therefore carry the wrong currency, and the failure surfaces late and
# confusingly - at invoice submit, as "Party Account currency (SAR) and document
# currency (INR) should be same".
#
# Only the stored currency is corrected. No amount is touched: the figures were
# always in company currency, the label on them was wrong.
import frappe


def execute():
	if not frappe.db.table_exists("AGS Fee Plan"):
		return

	rows = frappe.db.sql(
		"""
		select fp.name, fp.currency, c.default_currency
		from `tabAGS Fee Plan` fp
		inner join `tabCompany` c on c.name = fp.company
		where fp.currency != c.default_currency
		""",
		as_dict=True,
	)
	for row in rows:
		frappe.db.set_value(
			"AGS Fee Plan", row.name, "currency", row.default_currency,
			update_modified=False,
		)

	if rows:
		frappe.db.commit()
		print(f"aligned currency on {len(rows)} fee plan(s)")
