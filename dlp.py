"""
Shared DLP (Data Loss Prevention) scanner for the TSPO chat: protects the
secret pizza recipe from leaking through chat messages.

Score-based on purpose: a single casual mention of a topping, or the word
"recipe" on its own, must never block a message (e.g. "אני אוהב פיצה עם
זיתים" / "I like pizza with olives" is normal conversation). Only a real
combination of signals - a declaration, ingredients, quantities, and/or
preparation steps together - should cross the block threshold.

Importable from both client.py and the server, but the server's verdict is
the one that matters: the project brief requires DLP decisions to be applied
server-side, before a message is distributed to any recipient.
"""

from dataclasses import dataclass
import re
import unicodedata


BLOCK_THRESHOLD = 5

# Always blocked outright, regardless of score - a house rule, not a leak signal.
PINEAPPLE_TERMS = ("אננס", "pineapple")
FORBIDDEN_PINEAPPLE = "DLP_FORBIDDEN_PINEAPPLE"

DECLARATION_TERMS = (
    "מתכון", "המתכון", "מרכיבים", "הוראות הכנה",
    "recipe", "ingredients", "instructions",
)
DECLARATION_SCORE = 3
DECLARATION_CAP = 3

INGREDIENT_TERMS = (
    "בצק", "רוטב", "גבינה", "מוצרלה", "זיתים", "פטריות", "עגבניות",
    "שום", "בזיליקום", "אורגנו", "בצל", "קמח", "שמרים",
    "dough", "crust", "sauce", "mozzarella", "cheese", "pepperoni",
    "olives", "mushrooms", "tomato", "garlic", "basil", "oregano", "onion",
    "flour", "yeast",
)
INGREDIENT_SCORE = 1
INGREDIENT_CAP = 3

QUANTITY_TERMS = (
    "גרם", "קילו", "כוס", "כפית", "כף", "מעלות",
    "ml", "kg", "grams", "cup", "teaspoon", "tablespoon", "degrees",
)
QUANTITY_SCORE = 2
QUANTITY_CAP = 4

PREPARATION_TERMS = (
    "ללוש", "לערבב", "לאפות", "לחמם", "להוסיף",
    "mix", "knead", "bake", "heat", "add",
)
PREPARATION_SCORE = 2
PREPARATION_CAP = 4

_CATEGORIES = (
    ("declaration", DECLARATION_TERMS, DECLARATION_SCORE, DECLARATION_CAP),
    ("ingredient", INGREDIENT_TERMS, INGREDIENT_SCORE, INGREDIENT_CAP),
    ("quantity", QUANTITY_TERMS, QUANTITY_SCORE, QUANTITY_CAP),
    ("preparation", PREPARATION_TERMS, PREPARATION_SCORE, PREPARATION_CAP),
)

RECIPE_LEAK_SUSPECTED = "DLP_RECIPE_LEAK_SUSPECTED"


@dataclass(frozen=True)
class DLPFinding:
    category: str
    matched_terms: tuple
    score: int


@dataclass(frozen=True)
class DLPDecision:
    allowed: bool
    score: int
    reason_code: str | None
    findings: tuple = ()


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold().strip()
    return re.sub(r"\s+", " ", normalized)


def _score_category(normalized, terms, per_term_score, cap):
    matched = tuple(term for term in terms if term in normalized)
    score = min(len(matched) * per_term_score, cap)
    return matched, score


def scan(message: str, threshold: int = BLOCK_THRESHOLD) -> DLPDecision:
    """
    Scores a chat message for pizza-recipe leak signals and returns an
    allow/block decision. `findings` records which categories contributed
    and by how much, so the caller can show "the decision and reason"
    (required by the project brief) without re-deriving it.
    """
    normalized = _normalize(message or "")

    pineapple_matches = tuple(term for term in PINEAPPLE_TERMS if term in normalized)
    if pineapple_matches:
        return DLPDecision(
            allowed=False,
            score=threshold,
            reason_code=FORBIDDEN_PINEAPPLE,
            findings=(DLPFinding(category="pineapple", matched_terms=pineapple_matches, score=threshold),),
        )

    findings = []
    total_score = 0

    for category, terms, per_term_score, cap in _CATEGORIES:
        matched, score = _score_category(normalized, terms, per_term_score, cap)
        if matched:
            findings.append(DLPFinding(category=category, matched_terms=matched, score=score))
            total_score += score

    if total_score >= threshold:
        return DLPDecision(
            allowed=False,
            score=total_score,
            reason_code=RECIPE_LEAK_SUSPECTED,
            findings=tuple(findings),
        )

    return DLPDecision(allowed=True, score=total_score, reason_code=None, findings=tuple(findings))
