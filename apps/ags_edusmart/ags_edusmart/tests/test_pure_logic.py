"""Unit tests for logic that needs no database.

These are the rules most likely to be broken by a well-meaning refactor: grade
parsing, ageing bucket boundaries, the installment split's rounding invariant,
and the byte-length rule in the ZATCA TLV encoder.
"""

from __future__ import annotations

from frappe.tests import UnitTestCase

from ags_edusmart.ags_collections.ageing import bucket_for
from ags_edusmart.ags_fees.doctype.ags_fee_plan.ags_fee_plan import _split_amount
from ags_edusmart.ags_localization.zatca import _tlv, build_qr, hash_xml
from ags_edusmart.utils.grades import parse_grade_level, sort_programs


class TestGradeParsing(UnitTestCase):
	def test_plain_grades(self):
		self.assertEqual(parse_grade_level("Grade 5"), 5)
		self.assertEqual(parse_grade_level("Year 11"), 11)
		self.assertEqual(parse_grade_level("12"), 12)

	def test_kindergarten_sorts_below_grade_one(self):
		# The trap: a loose "first digit" search reads KG2 as grade 2 and files a
		# five-year-old with the seven-year-olds.
		self.assertEqual(parse_grade_level("KG1"), -1)
		self.assertEqual(parse_grade_level("KG2"), 0)
		self.assertLess(parse_grade_level("KG2"), parse_grade_level("Grade 1"))

	def test_grade_zero_is_real_not_unknown(self):
		# KG2 maps to 0, so callers must test `is None`, never falsiness.
		self.assertIsNotNone(parse_grade_level("KG2"))
		self.assertEqual(parse_grade_level("KG2"), 0)

	def test_non_grades_are_not_parsed(self):
		# Anchored at the start, so a room code is not mistaken for a year group.
		self.assertIsNone(parse_grade_level("Room 42"))
		self.assertIsNone(parse_grade_level("Lab 3"))
		self.assertIsNone(parse_grade_level(""))
		self.assertIsNone(parse_grade_level(None))

	def test_sort_keeps_unparseable_last_and_stable(self):
		ordered = sort_programs(["Grade 5", "KG2", "Foundation", "Grade 1", "KG1"])
		self.assertEqual(ordered[:4], ["KG1", "KG2", "Grade 1", "Grade 5"])
		self.assertEqual(ordered[-1], "Foundation")


class TestAgeingBuckets(UnitTestCase):
	def test_boundaries_are_inclusive_at_the_top(self):
		self.assertEqual(bucket_for(0), "bucket_current")
		self.assertEqual(bucket_for(-5), "bucket_current")
		self.assertEqual(bucket_for(1), "bucket_1_30")
		self.assertEqual(bucket_for(30), "bucket_1_30")
		self.assertEqual(bucket_for(31), "bucket_31_60")
		self.assertEqual(bucket_for(60), "bucket_31_60")
		self.assertEqual(bucket_for(90), "bucket_61_90")
		self.assertEqual(bucket_for(120), "bucket_91_120")
		self.assertEqual(bucket_for(121), "bucket_120_plus")

	def test_no_gap_between_buckets(self):
		seen = {bucket_for(day) for day in range(-10, 400)}
		self.assertEqual(len(seen), 6)


class TestInstallmentSplit(UnitTestCase):
	def test_parts_always_sum_back_to_the_total(self):
		# The invariant that keeps installments reconciling to the fee plan.
		for total in (24500, 22500, 10000, 7333.33, 0.03):
			for count in (1, 2, 3, 4, 10):
				parts = _split_amount(total, count)
				self.assertEqual(len(parts), count)
				self.assertAlmostEqual(sum(parts), round(total, 2), places=2)

	def test_remainder_lands_on_the_last_part(self):
		parts = _split_amount(100, 3)
		self.assertEqual(parts[0], 33.33)
		self.assertEqual(parts[1], 33.33)
		self.assertEqual(parts[2], 33.34)


class TestZatcaEncoding(UnitTestCase):
	def test_tlv_length_is_bytes_not_characters(self):
		# An Arabic seller name is multi-byte; using len(str) produces a QR that
		# scans but fails ZATCA validation.
		arabic = "مدارس"
		encoded = _tlv(1, arabic)
		self.assertEqual(encoded[0], 1)
		self.assertEqual(encoded[1], len(arabic.encode("utf-8")))
		self.assertNotEqual(encoded[1], len(arabic))

	def test_qr_is_deterministic_base64(self):
		import base64

		qr = build_qr("AGS", "300000000000003", "2026-09-01T08:00:00Z", 1150.00, 150.00)
		again = build_qr("AGS", "300000000000003", "2026-09-01T08:00:00Z", 1150.00, 150.00)
		self.assertEqual(qr, again)
		raw = base64.b64decode(qr)
		self.assertEqual(raw[0], 1)  # first tag is the seller name

	def test_amounts_are_two_decimal_strings(self):
		import base64

		raw = base64.b64decode(build_qr("A", "3", "2026-01-01T00:00:00Z", 5, 0.5))
		self.assertIn(b"5.00", raw)
		self.assertIn(b"0.50", raw)

	def test_hash_changes_when_the_document_changes(self):
		first = hash_xml("<Invoice>1</Invoice>")
		second = hash_xml("<Invoice>2</Invoice>")
		self.assertNotEqual(first, second)
		self.assertEqual(first, hash_xml("<Invoice>1</Invoice>"))
