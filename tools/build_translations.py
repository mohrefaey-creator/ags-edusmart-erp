"""Build ``translations/ar.csv`` from the mappings in this folder.

Frappe reads app translations as a headerless CSV of ``source,translation``
(a third column, when present, is a disambiguation context). This emits exactly
that, sorted, so a re-run produces no spurious diff.

It also *validates* the translations, because the failure modes here are silent:

* a placeholder dropped in translation turns a message into a crash at
  ``.format()`` time, on the Arabic UI only;
* a translation identical to its source is almost always an untranslated
  placeholder someone meant to come back to;
* a translation with no Arabic characters at all is the same mistake.

    python tools/build_translations.py            # build + report
    python tools/build_translations.py --check    # validate only, non-zero on error
"""

from __future__ import annotations

import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ar_long
import ar_messages
import ar_translations
import extract_strings as extractor

OUT = os.path.join(
	os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
	"apps", "ags_edusmart", "ags_edusmart", "translations", "ar.csv",
)

PLACEHOLDER = re.compile(r"\{\d+\}")
ARABIC = re.compile(r"[؀-ۿ]")


def mapping() -> dict[str, str]:
	merged: dict[str, str] = {}
	for source in (
		ar_translations.DOCTYPES,
		ar_translations.NATIVE_TERMS,
		ar_translations.LABELS,
		ar_translations.OPTIONS,
		ar_translations.CUSTOM_FIELDS,
		ar_messages.MESSAGES,
		ar_long.LONG,
	):
		for key, value in source.items():
			if key in merged and merged[key] != value:
				raise SystemExit(
					f"conflicting translations for {key!r}: "
					f"{merged[key]!r} vs {value!r}"
				)
			merged[key] = value
	return merged


def validate(translations: dict[str, str]) -> list[str]:
	problems: list[str] = []
	for source, target in translations.items():
		if not target.strip():
			problems.append(f"empty translation: {source!r}")
			continue

		# A dropped placeholder is a crash waiting to happen, in Arabic only.
		want = set(PLACEHOLDER.findall(source))
		got = set(PLACEHOLDER.findall(target))
		if want != got:
			problems.append(
				f"placeholder mismatch for {source!r}: expected {sorted(want)}, "
				f"got {sorted(got)}"
			)

		if source == target:
			problems.append(f"untranslated (identical to source): {source!r}")
		elif not ARABIC.search(target):
			problems.append(f"no Arabic characters in translation of {source!r}")

	return problems


def main() -> int:
	translations = mapping()
	problems = validate(translations)

	strings = (
		extractor.from_code()
		| extractor.from_doctypes()
		| extractor.from_custom_fields()
	)
	skip = ar_translations.DO_NOT_TRANSLATE
	needed = {s for s in strings if s not in skip}

	covered = sorted(s for s in needed if s in translations)
	missing = sorted(s for s in needed if s not in translations)
	# Translations for strings the extractor no longer finds: harmless, but they
	# accumulate, so they are reported rather than silently carried.
	orphans = sorted(k for k in translations if k not in strings)

	if problems:
		print("VALIDATION ERRORS")
		for problem in problems:
			print("  ", problem)
		print()

	print(f"translatable (excluding identifiers) : {len(needed)}")
	print(f"translated                           : {len(covered)}")
	print(f"missing                              : {len(missing)}")
	print(f"coverage                             : {len(covered) / len(needed) * 100:.1f}%")
	if orphans:
		print(f"orphaned (no longer in source)       : {len(orphans)}")

	if "--check" in sys.argv:
		if "--list-missing" in sys.argv:
			print()
			for value in missing:
				print(f"  {value}")
		return 1 if problems else 0

	os.makedirs(os.path.dirname(OUT), exist_ok=True)
	with open(OUT, "w", encoding="utf-8", newline="") as handle:
		writer = csv.writer(handle, lineterminator="\n")
		for source in sorted(translations):
			writer.writerow([source, translations[source]])

	print(f"\nwrote {len(translations)} rows -> {OUT}")
	if "--list-missing" in sys.argv:
		print()
		for value in missing:
			print(f"  {value}")
	return 1 if problems else 0


if __name__ == "__main__":
	raise SystemExit(main())
