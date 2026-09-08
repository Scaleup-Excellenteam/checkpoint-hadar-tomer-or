"""Unit tests for the shared DLP scorer in :mod:`dlp`."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import dlp


@pytest.mark.unit
@pytest.mark.parametrize("message", [
    "אני אוהב פיצה עם זיתים",
    "I like pizza with olives",
    "pepperoni is my favorite topping",
    "תוסיף גם קצת אורגנו",
])
def test_casual_pizza_talk_is_never_blocked(message):
    decision = dlp.scan(message)

    assert decision.allowed is True
    assert decision.reason_code is None


@pytest.mark.unit
def test_a_lone_recipe_question_is_not_blocked():
    decision = dlp.scan("יש לך מתכון טוב לפיצה?")

    assert decision.allowed is True
    assert decision.score < dlp.BLOCK_THRESHOLD


@pytest.mark.unit
def test_declaration_alone_scores_below_threshold():
    decision = dlp.scan("מתכון")

    assert decision.score == dlp.DECLARATION_SCORE
    assert decision.allowed is True


@pytest.mark.unit
def test_ingredients_with_quantities_and_preparation_is_blocked():
    decision = dlp.scan("250 גרם קמח, 7 גרם שמרים, לאפות ב-220 מעלות ל-12 דקות")

    assert decision.allowed is False
    assert decision.reason_code == dlp.RECIPE_LEAK_SUSPECTED
    assert decision.score >= dlp.BLOCK_THRESHOLD


@pytest.mark.unit
def test_declaration_plus_ingredients_is_blocked():
    decision = dlp.scan("מתכון: לערבב רוטב ומוצרלה")

    assert decision.allowed is False


@pytest.mark.unit
def test_english_ingredient_and_preparation_combo_is_blocked():
    decision = dlp.scan("add sauce and bake")

    assert decision.allowed is False


@pytest.mark.unit
def test_repeating_the_same_ingredient_does_not_inflate_score_past_its_cap():
    decision = dlp.scan("זיתים זיתים זיתים זיתים זיתים")

    assert decision.score == dlp.INGREDIENT_SCORE  # capped at one match, not five
    assert decision.allowed is True


@pytest.mark.unit
def test_empty_or_none_message_is_allowed():
    assert dlp.scan("").allowed is True
    assert dlp.scan(None).allowed is True


@pytest.mark.unit
@pytest.mark.parametrize("message", [
    "אננס",
    "pineapple",
    "PINEAPPLE is forbidden",
    "אני אוהב פיצה עם אננס",  # otherwise-casual message, still blocked
])
def test_pineapple_is_always_blocked_regardless_of_score(message):
    decision = dlp.scan(message)

    assert decision.allowed is False
    assert decision.reason_code == dlp.FORBIDDEN_PINEAPPLE


@pytest.mark.unit
def test_pineapple_rule_takes_priority_over_recipe_scoring():
    # Also has clear recipe-structure signals, but the reason code should
    # still be the pineapple rule since it's checked first.
    decision = dlp.scan("אננס: 250 גרם קמח, לאפות")

    assert decision.reason_code == dlp.FORBIDDEN_PINEAPPLE


@pytest.mark.unit
def test_findings_report_which_categories_contributed():
    decision = dlp.scan("מתכון: 200 גרם קמח, לאפות")

    categories = {finding.category for finding in decision.findings}
    assert categories == {"declaration", "ingredient", "quantity", "preparation"}
