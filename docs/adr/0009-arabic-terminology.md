# ADR 0009 — Arabic terminology, and where translations live

**Status:** Accepted · 2026-09-06

## Context

Handover §25 requires an Arabic/English UI from day one. Frappe reads app
translations from a headerless `source,translation` CSV, which is a poor place
to make *decisions* — a reviewer sees 961 rows and no reasoning.

## Decision

`translations/ar.csv` is **generated**, from mappings in `tools/ar_*.py`, by
`tools/build_translations.py`. Terminology, short messages, long descriptions
and custom-field labels are separate modules, because a term is right or wrong
while a sentence also has to read naturally — different review.

The terminology decisions a second translator would otherwise undo:

| English | Arabic | Why not the obvious alternative |
|---|---|---|
| Campus | الحرم المدرسي | — |
| School Division | المرحلة الدراسية | Not القسم: ERPNext already uses that for Department, and AGS divisions genuinely are *stages* (KG, Primary, Middle, Secondary) |
| Payer Account | حساب الدافع | Not حساب ولي الأمر: §13.4 exists precisely because the payer is *not* necessarily the guardian |
| Commitment | ارتباط الميزانية | Standard Arabic public-sector budgeting term for reserved-not-spent |
| Custody / handover | عهدة | The word Saudi schools actually use for issued equipment |

**The "AGS" prefix is dropped in Arabic.** "AGS Campus" is الحرم المدرسي, not
"حرم AGS". Inside the AGS system the brand adds nothing, and mixing Latin and
Arabic inside one label is the bidi hazard documented in `utils/formatting.py`.

**Identifiers are never translated** — naming series, `SQL`, `UOM`, `UUID`,
language codes, provider names. Translating them would break the values they
name.

## Why generated rather than hand-edited

Three failure modes here are silent, and the builder catches all three:

1. **A dropped placeholder.** `"{0} is outstanding"` translated without `{0}`
   raises at `.format()` time — on the Arabic UI only.
2. **A translation identical to its source**, which is almost always a
   placeholder someone meant to return to.
3. **A source string that drifted**, leaving an entry that no longer matches and
   a label that silently reverts to English.

The builder validates 1 and 2; `tests/test_translations.py` re-checks them
against Frappe's *own* CSV reader, and fails if any DocType label lacks an entry
— so coverage cannot rot as fields are added.

## The extraction bug worth remembering

The first extractor used a regex for `_("...")`. Python concatenates adjacent
string literals at compile time, so

```python
_("Absence runs at {0}% overall and no department "
  "stands out against the others.")
```

is **one** string at runtime. The regex captured only the first fragment, which
would have produced ~40 source keys that could never match — translations
written, committed, and silently never applied. Extraction now goes through the
AST, which has already folded them.

A second pass covers `setup/custom_fields.py`: those labels are dict values, not
`_()` calls, and were invisible to both earlier passes.

## Consequences

- `python tools/build_translations.py` after any UI string change; the test
  suite enforces it.
- Coverage is 100% of 961 strings, and is measured rather than asserted.
- Adding a second language means one more `ar_*`-shaped module and one CSV.
