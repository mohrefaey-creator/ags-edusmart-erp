"""Regenerate every ags_edusmart DocType JSON from the specs in this folder.

Idempotent: run it after editing any spec and commit the diff. Controllers that
already exist on disk are never overwritten unless the spec supplies one, so
hand-written business logic is safe.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import specs_core
import specs_fees
import specs_ops
import specs_platform
from doctype_builder import ensure_module_packages, write

APP_ROOT = os.path.join(
	os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
	"apps", "ags_edusmart", "ags_edusmart",
)

MODULES = [
	"AGS Core", "AGS Fees", "AGS Collections", "AGS Procurement", "AGS Inventory",
	"AGS Assets", "AGS HR", "AGS Approvals", "AGS Dashboards", "AGS Notifications",
	"AGS Localization", "AGS AI",
]


def main() -> int:
	ensure_module_packages(APP_ROOT, MODULES)

	all_specs = []
	for source in (specs_core, specs_fees, specs_ops, specs_platform):
		all_specs.extend(source.specs())

	seen: set[str] = set()
	for spec, controller in all_specs:
		name = spec["name"]
		if name in seen:
			raise SystemExit(f"duplicate DocType spec: {name}")
		seen.add(name)

		# A Link/Table option pointing at a DocType we never generate is the
		# single most common cause of a failed migrate, so check it up front.
		write(spec, APP_ROOT, controller)

	_validate_links(all_specs, seen)
	print(f"generated {len(all_specs)} DocTypes into {APP_ROOT}")
	return 0


# DocTypes owned by frappe / erpnext / hrms / education that specs may reference.
EXTERNAL = {
	"Company", "Cost Center", "Account", "Warehouse", "Item", "Supplier", "Customer",
	"User", "Role", "DocType", "Employee", "Department", "Project", "Fiscal Year",
	"Currency", "UOM", "Location", "Asset", "Asset Movement", "Stock Entry",
	"Material Request", "Purchase Order", "Purchase Receipt", "Purchase Invoice",
	"Sales Invoice", "Supplier Quotation", "Request for Quotation", "Payment Entry",
	"Student", "Guardian", "Program", "Academic Year", "Academic Term",
	"Student Category", "Fee Structure", "Fee Category", "Program Enrollment",
	"Student Group", "Phone", "Email", "Python", "SQL",
}


def _validate_links(all_specs, generated: set[str]) -> None:
	known = generated | EXTERNAL
	problems = []
	for spec, _ in all_specs:
		for field in spec["fields"]:
			ftype = field["fieldtype"]
			if ftype not in ("Link", "Table", "Table MultiSelect"):
				continue
			target = field.get("options")
			if not target:
				problems.append(f"{spec['name']}.{field['fieldname']}: {ftype} with no options")
			elif target not in known:
				problems.append(
					f"{spec['name']}.{field['fieldname']}: unknown target {target!r}"
				)
	if problems:
		for line in problems:
			print("  LINK ERROR:", line, file=sys.stderr)
		raise SystemExit(f"{len(problems)} unresolved link target(s)")


if __name__ == "__main__":
	raise SystemExit(main())
