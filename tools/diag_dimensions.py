import frappe

print("DIMENSIONS", frappe.get_all(
	"Accounting Dimension",
	fields=["name", "document_type", "fieldname", "disabled"],
))

for dt in ("Budget", "Sales Invoice", "Payment Entry", "Material Request"):
	cols = [c[0] for c in frappe.db.sql(f"describe `tab{dt}`")]
	print(dt, "HAS_CAMPUS_COL", "campus" in cols, "HAS_GRADE_COL", "grade" in cols)

print("CF", frappe.get_all(
	"Custom Field",
	filters={"fieldname": ("in", ["campus", "school_division", "grade", "academic_year"])},
	fields=["dt", "fieldname"],
	limit=50,
))
