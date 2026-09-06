"""Map a natural-language question to an analyzer.

Deliberately not a language model. Routing is a small, closed classification
problem - a few dozen known questions - and a deterministic router has two
properties that matter more here than flexibility:

* **It knows when it does not know.** Below the confidence floor it returns the
  questions it *can* answer instead of guessing. A model asked to pick from a
  list will always pick something.
* **It is auditable.** "Why did it run the payroll analysis?" has an answer you
  can read, which matters when the answer contained salary figures.

Arabic is matched alongside English because the UI is bilingual, and a router
that only understands English would quietly make the Arabic interface useless.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ags_edusmart.ags_ai.registry import Analyzer, all_analyzers
from ags_edusmart.ags_ai.scope import Scope

# Arabic keyword aliases, keyed by analyzer code. Kept beside the router rather
# than in the analyzers so translators can work on one file.
ARABIC_KEYWORDS: dict[str, tuple[str, ...]] = {
	"outstanding_tuition": ("المتبقي", "المستحق", "الرسوم", "غير مدفوع", "مديونية"),
	"overdue_by_campus": ("متأخر", "الفرع", "الحرم", "أعلى", "أي فرع"),
	"margin_drivers": ("الهامش", "الربح", "لماذا", "انخفض", "تراجع", "أسباب"),
	"budget_overrun": ("الميزانية", "تجاوز", "تجاوزت", "انحراف"),
	"expected_collection": ("التحصيل", "متوقع", "الشهر القادم", "توقع", "نقد"),
	"revenue_trend": ("الإيرادات", "الدخل", "نمو", "اتجاه"),
	"long_overdue_payers": ("أولياء الأمور", "متأخرين", "90", "تسعين", "من يدين"),
	"collection_performance": ("نسبة التحصيل", "أداء التحصيل", "التحصيل حسب"),
	"supplier_ranking": ("المورد", "الموردين", "أفضل", "تقييم"),
	"delayed_orders": ("أوامر الشراء", "متأخرة", "تأخير", "لم تصل"),
	"price_drift": ("السعر", "الأسعار", "ارتفاع", "أغلى", "زيادة"),
	"consolidation_opportunities": ("دمج", "توحيد", "طلبات متكررة"),
	"stockout_forecast": ("نفاد", "سينفد", "المخزون", "نقص", "إعادة طلب"),
	"consumption_outliers": ("استهلاك", "الأقسام", "مرتفع", "غير طبيعي"),
	"non_moving_items": ("راكد", "بطيء الحركة", "لم يتحرك", "ستة أشهر"),
	"absenteeism_outliers": ("الغياب", "غياب الموظفين", "الأقسام", "مرتفع"),
	"payroll_projection": ("الرواتب", "الأجور", "توقع", "السنة القادمة", "تكلفة"),
	"expiring_documents": ("انتهاء", "الإقامة", "العقد", "تنتهي", "تجديد"),
	"attendance_risk": ("حضور", "غياب الطلاب", "خطر", "الطلاب المتغيبين"),
	"declining_classes": ("الفصول", "تراجع", "النتائج", "أداء أكاديمي"),
	"teacher_variance": ("المعلم", "المعلمين", "أقل من المتوسط", "الفروقات"),
}

# Words that carry no signal for routing. Stripping them stops a long, polite
# question from scoring lower than a terse one.
STOPWORDS = {
	"what", "which", "who", "how", "why", "is", "are", "the", "our", "we", "us",
	"a", "an", "of", "in", "on", "for", "to", "and", "do", "does", "did", "me",
	"show", "tell", "give", "list", "please", "much", "many", "at", "by", "from",
	# Arabic stopwords are listed in their normalised form (see _normalise_arabic:
	# diacritics removed, alef/ya variants folded, definite article stripped).
	"ما", "ماهي", "هي", "هو", "هذا", "هذه", "من", "في", "علي", "الي", "هل",
	"كم", "لماذا", "اي", "التي", "الذي", "عن", "مع", "عند", "لدي",
}

MINIMUM_CONFIDENCE = 0.34


@dataclass
class Route:
	analyzer: Analyzer | None
	confidence: float
	alternatives: list[Analyzer]

	@property
	def matched(self) -> bool:
		return self.analyzer is not None


# Arabic normalisation. Without it the router misses constantly: "الاستهلاك"
# (with the definite article) and "استهلاك" are the same word to a reader and
# two unrelated tokens to a naive matcher, and Arabic writes the same letter
# several ways depending on position and typist.
_DIACRITICS = re.compile(r"[ً-ْٰـ]")
_ARABIC = re.compile(r"[؀-ۿ]")


def _normalise_arabic(word: str) -> str:
	word = _DIACRITICS.sub("", word)
	# Alef and ya/ta-marbuta variants are routinely typed interchangeably.
	for source, target in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"),
	                       ("ى", "ي"), ("ة", "ه")):
		word = word.replace(source, target)
	# Strip the definite article, but only when a real stem remains - "ال"
	# alone, or "الم", is not a word with an article on it.
	if len(word) > 4 and word.startswith("ال"):
		word = word[2:]
	return word


def _tokenise(text: str) -> set[str]:
	# Keep Arabic letters alongside Latin; \w under re.UNICODE already does, but
	# being explicit documents the intent.
	words = re.findall(r"[\w؀-ۿ]+", (text or "").lower(), flags=re.UNICODE)
	tokens = set()
	for word in words:
		if _ARABIC.search(word):
			word = _normalise_arabic(word)
		if word and word not in STOPWORDS and len(word) > 1:
			tokens.add(word)
	return tokens


def _score(question_tokens: set[str], item: Analyzer) -> float:
	"""Overlap between the asked question and one analyzer's vocabulary."""
	vocabulary: set[str] = set()
	for keyword in item.keywords + ARABIC_KEYWORDS.get(item.code, ()):
		vocabulary |= _tokenise(keyword)
	vocabulary |= _tokenise(item.question)

	if not vocabulary or not question_tokens:
		return 0.0

	hits = question_tokens & vocabulary
	if not hits:
		return 0.0

	# Normalised by the question, not the vocabulary: an analyzer with many
	# keywords should not win simply for having a large surface.
	coverage = len(hits) / len(question_tokens)
	specificity = len(hits) / len(vocabulary)
	return round(0.75 * coverage + 0.25 * specificity, 4)


def route(question: str, scope: Scope) -> Route:
	"""Best analyzer for a question, restricted to what this user may run."""
	candidates = all_analyzers(scope)
	tokens = _tokenise(question)

	scored = sorted(
		((_score(tokens, item), item) for item in candidates),
		key=lambda pair: pair[0],
		reverse=True,
	)
	scored = [(s, a) for s, a in scored if s > 0]

	if not scored or scored[0][0] < MINIMUM_CONFIDENCE:
		# Offer what is available rather than guessing. The suggestions are the
		# permitted set, so they never advertise an analysis the user is not
		# allowed to run.
		return Route(analyzer=None, confidence=scored[0][0] if scored else 0.0,
		             alternatives=candidates[:8])

	best_score, best = scored[0]

	# A near-tie is not a confident answer. Surfacing both is more useful than
	# picking one and being wrong half the time.
	runners = [a for s, a in scored[1:4] if best_score - s < 0.08]
	return Route(analyzer=best, confidence=best_score, alternatives=runners)
