"""Extract every translatable string in the app.

Frappe translates three surfaces and it is easy to remember only the first:

1. ``_("...")`` / ``__("...")`` calls in Python, JS and Jinja;
2. DocType metadata - the doctype name, every field label, every Select option,
   and field descriptions;
3. the workspace/report labels Frappe generates from those names.

Run ``python tools/extract_strings.py`` to list what is not yet translated in
``translations/ar.csv``. Run with ``--all`` to list everything.
"""

from __future__ import annotations

import ast
import csv
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "apps", "ags_edusmart", "ags_edusmart")
AR_CSV = os.path.join(APP, "translations", "ar.csv")

# _("...") and __("...") with either quote style. Deliberately does not try to
# handle f-strings or concatenation: those are not translatable anyway.
CALL_RE = re.compile(r"""\b_{1,2}\(\s*(["'])((?:\\.|(?!\1).)*?)\1""", re.DOTALL)

SKIP_DIRS = {"__pycache__", "node_modules", ".git", "dist"}


def _iter_files(*extensions: str):
	for base, dirs, files in os.walk(APP):
		dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
		for name in files:
			if name.endswith(extensions):
				yield os.path.join(base, name)


def _is_translation_call(node) -> bool:
	"""``_(...)`` or ``frappe._(...)``."""
	func = node.func
	if isinstance(func, ast.Name):
		return func.id == "_"
	if isinstance(func, ast.Attribute):
		return func.attr == "_"
	return False


def from_python(path: str) -> set[str]:
	"""Extract via AST, not regex.

	Python concatenates adjacent string literals at compile time, so

	    _("Absence runs at {0}% overall and no department "
	      "stands out against the others.")

	is a *single* string at runtime. A regex that grabs the first quoted literal
	produces a source key that can never match, and the translation silently
	never applies. The AST has already folded them.
	"""
	found: set[str] = set()
	try:
		tree = ast.parse(open(path, encoding="utf-8").read())
	except (OSError, UnicodeDecodeError, SyntaxError):
		return found

	for node in ast.walk(tree):
		if not isinstance(node, ast.Call) or not _is_translation_call(node):
			continue
		if not node.args:
			continue
		first = node.args[0]
		if isinstance(first, ast.Constant) and isinstance(first.value, str):
			found.add(first.value)
	return found


def from_code() -> set[str]:
	found: set[str] = set()

	for path in _iter_files(".py"):
		found |= from_python(path)

	# JS and Jinja have no implicit concatenation in this codebase, so a regex
	# is sufficient and avoids depending on a JS parser.
	for path in _iter_files(".js", ".html"):
		try:
			text = open(path, encoding="utf-8").read()
		except (OSError, UnicodeDecodeError):
			continue
		for _quote, value in CALL_RE.findall(text):
			value = value.replace("\\n", "\n").replace('\\"', '"').replace("\\'", "'")
			found.add(value)

	# Placeholders survive translation; a bare "{0}" needs no entry.
	return {v for v in found if v.strip() and not re.fullmatch(r"[\s{}\d.]*", v)}


def from_custom_fields() -> set[str]:
	"""Labels, descriptions and Select options declared in setup/custom_fields.py.

	These are ordinary UI strings - they render as field labels and help text on
	Student, Employee, Sales Invoice and the rest - but they live in dict
	literals rather than ``_()`` calls, so neither the AST pass nor the DocType
	pass sees them. Missing them leaves visibly untranslated fields on otherwise
	fully Arabic forms.
	"""
	path = os.path.join(APP, "setup", "custom_fields.py")
	found: set[str] = set()
	if not os.path.exists(path):
		return found

	try:
		tree = ast.parse(open(path, encoding="utf-8").read())
	except (OSError, UnicodeDecodeError, SyntaxError):
		return found

	def literal(node):
		"""Resolve a constant or an implicitly concatenated string."""
		if isinstance(node, ast.Constant) and isinstance(node.value, str):
			return node.value
		return None

	for node in ast.walk(tree):
		if not isinstance(node, ast.Dict):
			continue
		for key_node, value_node in zip(node.keys, node.values):
			key = literal(key_node)
			value = literal(value_node)
			if not key or not value:
				continue
			if key in ("label", "description"):
				found.add(value)
			elif key == "options":
				# Only Select options are free text; a Link's options is a
				# DocType name, which the DocType pass already covers.
				if "\n" in value:
					for option in value.split("\n"):
						if option.strip():
							found.add(option.strip())
	return found


def from_doctypes() -> set[str]:
	found: set[str] = set()
	for path in _iter_files(".json"):
		if os.sep + "doctype" + os.sep not in path:
			continue
		try:
			spec = json.load(open(path, encoding="utf-8"))
		except (OSError, ValueError):
			continue
		if spec.get("doctype") != "DocType":
			continue

		found.add(spec["name"])
		if spec.get("description"):
			found.add(spec["description"])

		for field in spec.get("fields", []):
			if field.get("label"):
				found.add(field["label"])
			if field.get("description"):
				found.add(field["description"])
			# Select options are shown verbatim in the UI and are missed by
			# every extractor that only looks at labels.
			if field.get("fieldtype") == "Select" and field.get("options"):
				for option in str(field["options"]).split("\n"):
					if option.strip():
						found.add(option.strip())
	return found


def existing() -> dict[str, str]:
	if not os.path.exists(AR_CSV):
		return {}
	out: dict[str, str] = {}
	with open(AR_CSV, encoding="utf-8", newline="") as handle:
		for row in csv.reader(handle):
			if len(row) >= 2 and row[0].strip():
				out[row[0]] = row[1]
	return out


def main() -> int:
	show_all = "--all" in sys.argv
	strings = from_code() | from_doctypes() | from_custom_fields()
	have = existing()

	missing = sorted(s for s in strings if s not in have)
	translated = sorted(s for s in strings if s in have and have[s].strip())

	print(f"translatable strings : {len(strings)}")
	print(f"translated (ar)      : {len(translated)}")
	print(f"missing              : {len(missing)}")
	coverage = len(translated) / len(strings) * 100 if strings else 0
	print(f"coverage             : {coverage:.1f}%")

	target = strings if show_all else missing
	if target and ("--list" in sys.argv or show_all or missing):
		print()
		for value in sorted(target)[:400]:
			print(f"  {value}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
