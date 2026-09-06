"""Arabic translation tests.

A translation file fails silently. If a source string drifts by one character
the entry stops matching and that label quietly reverts to English on the Arabic
UI, with nothing logged. These tests make that loud.
"""

from __future__ import annotations

import csv
import os
import re

import frappe
from frappe.tests import UnitTestCase
from frappe.translate import get_translation_dict_from_file

PLACEHOLDER = re.compile(r"\{\d+\}")
ARABIC = re.compile(r"[؀-ۿ]")

AR_CSV = frappe.get_app_path("ags_edusmart", "translations", "ar.csv")


def _rows() -> list[list[str]]:
	with open(AR_CSV, encoding="utf-8", newline="") as handle:
		return [row for row in csv.reader(handle) if row]


class TestArabicTranslations(UnitTestCase):
	def test_file_exists_and_is_not_trivial(self):
		self.assertTrue(os.path.exists(AR_CSV), "ar.csv is missing")
		self.assertGreater(len(_rows()), 500, "ar.csv looks truncated")

	def test_frappe_can_parse_it(self):
		"""Parsed with Frappe's own reader, not ours - the formats must agree."""
		mapping = get_translation_dict_from_file(AR_CSV, "ar", "ags_edusmart", throw=True)
		self.assertGreater(len(mapping), 500)
		self.assertEqual(mapping.get("AGS Fee Plan"), "خطة الرسوم")
		self.assertEqual(mapping.get("Payer Account"), "حساب الدافع")

	def test_every_row_is_a_pair(self):
		for index, row in enumerate(_rows(), start=1):
			self.assertIn(
				len(row), (2, 3),
				f"row {index} has {len(row)} columns: {row!r}",
			)

	def test_placeholders_survive_translation(self):
		"""A dropped {0} becomes a KeyError at .format() time, in Arabic only."""
		for source, target, *_rest in _rows():
			self.assertEqual(
				set(PLACEHOLDER.findall(source)),
				set(PLACEHOLDER.findall(target)),
				f"placeholder mismatch: {source!r} -> {target!r}",
			)

	def test_no_row_is_left_untranslated(self):
		for source, target, *_rest in _rows():
			self.assertTrue(target.strip(), f"empty translation for {source!r}")
			self.assertNotEqual(source, target, f"untranslated: {source!r}")
			self.assertTrue(
				ARABIC.search(target),
				f"no Arabic characters in translation of {source!r}: {target!r}",
			)

	def test_terminology_is_consistent(self):
		"""The decisions recorded in tools/ar_translations.py must hold."""
		mapping = get_translation_dict_from_file(AR_CSV, "ar", "ags_edusmart")

		# Campus and School Division must not collide with Department (القسم),
		# which ERPNext already owns.
		self.assertEqual(mapping.get("Campus"), "الحرم المدرسي")
		self.assertEqual(mapping.get("School Division"), "المرحلة الدراسية")
		self.assertEqual(mapping.get("Department"), "القسم")
		self.assertNotEqual(mapping.get("School Division"), mapping.get("Department"))

		# The payer is deliberately not "guardian" - the model keeps them apart.
		self.assertNotIn("ولي الأمر", mapping.get("Payer Account", ""))
		self.assertEqual(mapping.get("Guardian"), "ولي الأمر")

	def test_identifiers_are_not_translated(self):
		"""Naming series and code tokens must stay verbatim."""
		mapping = get_translation_dict_from_file(AR_CSV, "ar", "ags_edusmart")
		for identifier in ("AGS-PAY-.#####", "AGS-FP-.YYYY.-.#####", "SQL", "UUID",
		                   "Anthropic", "en", "ar"):
			self.assertNotIn(
				identifier, mapping,
				f"{identifier} is an identifier and must not be translated",
			)

	def test_arabic_does_not_leak_into_the_source_column(self):
		"""A source key with Arabic in it means the columns were swapped."""
		for source, _target, *_rest in _rows():
			self.assertIsNone(
				ARABIC.search(source),
				f"source column contains Arabic (columns swapped?): {source!r}",
			)


class TestTranslationCoverage(UnitTestCase):
	def test_no_translatable_string_is_missing(self):
		"""Every string the app can show has an Arabic entry.

		This is what stops coverage rotting: add a new field label and this test
		fails until it is translated.
		"""
		import ast
		import json

		app_root = frappe.get_app_path("ags_edusmart")
		mapping = get_translation_dict_from_file(AR_CSV, "ar", "ags_edusmart")

		# Identifiers that are deliberately never translated.
		skip = {
			"#", "ar", "en", "SQL", "UOM", "UUID", "Anthropic",
			"OpenAI-Compatible", "Python", "ICV", "PIH",
		}

		missing: list[str] = []

		# DocType metadata is the surface most often forgotten.
		for base, dirs, files in os.walk(app_root):
			dirs[:] = [d for d in dirs if d != "__pycache__"]
			if os.sep + "doctype" + os.sep not in base:
				continue
			for name in files:
				if not name.endswith(".json"):
					continue
				try:
					spec = json.load(open(os.path.join(base, name), encoding="utf-8"))
				except (OSError, ValueError):
					continue
				if spec.get("doctype") != "DocType":
					continue

				candidates = [spec["name"]]
				for field in spec.get("fields", []):
					if field.get("label"):
						candidates.append(field["label"])
					if field.get("fieldtype") == "Select" and field.get("options"):
						candidates.extend(
							o.strip() for o in str(field["options"]).split("\n") if o.strip()
						)

				for value in candidates:
					if value.startswith("AGS-") or value in skip:
						continue
					if value not in mapping:
						missing.append(f"{spec['name']}: {value}")

		self.assertEqual(
			missing[:20], [],
			f"{len(missing)} untranslated DocType string(s); "
			f"run `python tools/build_translations.py`",
		)
