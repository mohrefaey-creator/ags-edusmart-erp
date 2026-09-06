"""Canonical DocType JSON emitter for the ags_edusmart app.

Frappe reads DocType definitions from JSON on disk. Hand-writing ~40 of those
drifts fast: a missing ``permissions`` block or a stale ``field_order`` only
surfaces at migrate time. This module gives the specs a compact Python DSL and
emits JSON that is byte-stable, so re-running it produces no spurious diff.
"""

from __future__ import annotations

import json
import os
from typing import Any

STAMP = "2026-09-06 00:00:00.000000"

# Roles that exist by the time the app installs. Anything referenced in a
# permission block must be created in setup/roles.py or migrate will fail.
SYS = "System Manager"


def f(fieldname: str, fieldtype: str, label: str | None = None, **kw: Any) -> dict:
	"""One DocType field. Keyword args map straight onto Frappe field properties."""
	field: dict[str, Any] = {"fieldname": fieldname, "fieldtype": fieldtype}
	if label is not None:
		field["label"] = label
	for key, value in kw.items():
		if value is None:
			continue
		field[key] = value
	return field


def section(name: str, label: str = "", **kw: Any) -> dict:
	return f(name, "Section Break", label or None, **kw)


def column(name: str) -> dict:
	return f(name, "Column Break")


def perm(role: str, *, level: int = 0, submit: bool = False, cancel: bool = False,
         amend: bool = False, write: bool = True, create: bool = True,
         delete: bool = True, read: bool = True, report: bool = True,
         export: bool = True, share: bool = True, print_: bool = True,
         email: bool = True, if_owner: bool = False) -> dict:
	block = {
		"role": role,
		"permlevel": level,
		"read": int(read),
		"write": int(write),
		"create": int(create),
		"delete": int(delete),
		"report": int(report),
		"export": int(export),
		"share": int(share),
		"print": int(print_),
		"email": int(email),
	}
	if submit:
		block["submit"] = 1
	if cancel:
		block["cancel"] = 1
	if amend:
		block["amend"] = 1
	if if_owner:
		block["if_owner"] = 1
	return block


def readonly_perm(role: str) -> dict:
	return perm(role, write=False, create=False, delete=False)


def doctype(
	name: str,
	module: str,
	fields: list[dict],
	*,
	autoname: str | None = None,
	is_submittable: bool = False,
	is_child: bool = False,
	is_single: bool = False,
	is_tree: bool = False,
	track_changes: bool = True,
	track_seen: bool = False,
	permissions: list[dict] | None = None,
	title_field: str | None = None,
	search_fields: str | None = None,
	sort_field: str = "modified",
	sort_order: str = "DESC",
	naming_rule: str | None = None,
	description: str | None = None,
	allow_rename: bool = True,
	quick_entry: bool = False,
	states: list[dict] | None = None,
) -> dict:
	spec: dict[str, Any] = {
		"actions": [],
		"allow_rename": int(allow_rename),
		"creation": STAMP,
		"doctype": "DocType",
		"editable_grid": 1,
		"engine": "InnoDB",
		"field_order": [fld["fieldname"] for fld in fields],
		"fields": fields,
		"index_web_pages_for_search": 1,
		"links": [],
		"modified": STAMP,
		"modified_by": "Administrator",
		"module": module,
		"name": name,
		"owner": "Administrator",
		"permissions": permissions if permissions is not None else [perm(SYS)],
		"sort_field": sort_field,
		"sort_order": sort_order,
		"states": states or [],
	}
	if autoname:
		spec["autoname"] = autoname
	if naming_rule:
		spec["naming_rule"] = naming_rule
	if is_submittable:
		spec["is_submittable"] = 1
	if is_child:
		spec["istable"] = 1
		spec["permissions"] = []
		spec["allow_rename"] = 0
	if is_single:
		spec["issingle"] = 1
		spec["allow_rename"] = 0
	if is_tree:
		spec["is_tree"] = 1
	if track_changes:
		spec["track_changes"] = 1
	if track_seen:
		spec["track_seen"] = 1
	if title_field:
		spec["title_field"] = title_field
		spec["show_title_field_in_link"] = 1
	if search_fields:
		spec["search_fields"] = search_fields
	if description:
		spec["description"] = description
	if quick_entry:
		spec["quick_entry"] = 1
	return spec


def _module_dir(module: str) -> str:
	"""'AGS Core' -> 'ags_core' (the package folder Frappe expects)."""
	return module.lower().replace(" ", "_")


def _doctype_dir(name: str) -> str:
	return name.lower().replace(" ", "_").replace("-", "_")


def write(spec: dict, app_root: str, controller: str | None = None) -> str:
	"""Write <module>/doctype/<name>/{name}.json + __init__.py + controller."""
	module_dir = _module_dir(spec["module"])
	dt_dir = _doctype_dir(spec["name"])
	target = os.path.join(app_root, module_dir, "doctype", dt_dir)
	os.makedirs(target, exist_ok=True)

	init_path = os.path.join(target, "__init__.py")
	if not os.path.exists(init_path):
		open(init_path, "w", encoding="utf-8").close()

	json_path = os.path.join(target, f"{dt_dir}.json")
	with open(json_path, "w", encoding="utf-8", newline="\n") as handle:
		json.dump(spec, handle, indent=1, ensure_ascii=False)
		handle.write("\n")

	# Child tables and Singles still need a controller module for Frappe to import.
	py_path = os.path.join(target, f"{dt_dir}.py")
	if controller is not None:
		with open(py_path, "w", encoding="utf-8", newline="\n") as handle:
			handle.write(controller)
	elif not os.path.exists(py_path):
		cls = spec["name"].replace(" ", "").replace("-", "")
		base = "Document"
		with open(py_path, "w", encoding="utf-8", newline="\n") as handle:
			handle.write(
				"from frappe.model.document import Document\n\n\n"
				f"class {cls}({base}):\n\tpass\n"
			)
	return json_path


def ensure_module_packages(app_root: str, modules: list[str]) -> None:
	for module in modules:
		module_dir = os.path.join(app_root, _module_dir(module))
		os.makedirs(os.path.join(module_dir, "doctype"), exist_ok=True)
		for path in (module_dir, os.path.join(module_dir, "doctype")):
			init = os.path.join(path, "__init__.py")
			if not os.path.exists(init):
				open(init, "w", encoding="utf-8").close()
