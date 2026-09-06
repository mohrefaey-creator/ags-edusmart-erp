# Retention for the AI query log.
#
# The log is an audit trail, so it is trimmed on a schedule rather than never
# (unbounded growth) or on write (which would make an audit record depend on the
# thing it audits succeeding).
import frappe
from frappe.utils import add_days, nowdate


def purge_query_log():
	days = frappe.db.get_single_value("AGS AI Settings", "query_log_retention_days")
	days = int(days or 0)
	if days <= 0:
		return {"skipped": "retention disabled"}

	cutoff = add_days(nowdate(), -days)
	deleted = frappe.db.sql(
		"delete from `tabAGS AI Query Log` where creation < %(cutoff)s",
		{"cutoff": cutoff},
	)
	frappe.db.commit()
	return {"cutoff": str(cutoff), "deleted": deleted}
