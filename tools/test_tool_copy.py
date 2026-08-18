"""Regression guard for the copy inside the published tools.

Why this exists: on 2026-08-16 the pre-promotion audit found that updating
compensation-data.json had not updated the sentences that quote it. The
Salary Benchmarker, the Offer Evaluator and two Squarespace wrappers were
still stating Chief of Staff Collective 2025 figures (56% bonus incidence,
19% average payout, 54% equity incidence) and one of them still linked the
2025 survey. The dataset had moved to the 2026 survey (57%, 16%, 77%, n=56).

The rule this file enforces: a survey percentage is READ from
compensation-data.json at runtime, never retyped into the copy. So neither
the retired figures nor the current ones may appear as literals in the tool
markup or scripts. Brand rules are checked in the same sweep because the same
files are the ones that ship them.

Squarespace wrappers (Website/pages_html/*.html) cannot be covered here: they
are pasted by the owner and are not part of this repo. Their find/replace
pairs live in TOOLFIXES_2026-08-17_PASTE_NOTES.md.

Run: python -m pytest tools/test_tool_copy.py
"""

import json
import re
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent
DATA = json.loads((TOOLS / "compensation-data.json").read_text(encoding="utf-8"))

SOURCE_FILES = sorted(
    [p for p in TOOLS.glob("*.html")] + [p for p in TOOLS.glob("*.js")]
)

STYLE_BLOCK = re.compile(r"<style\b.*?</style>", re.S | re.I)


def prose(path: Path) -> str:
    """File text with CSS removed, so a width:16% rule is not read as a claim."""
    return STYLE_BLOCK.sub(" ", path.read_text(encoding="utf-8"))


def as_percent(value) -> str:
    """0.57 -> '57%', 16 -> '16%', 0.234 -> '23.4%'."""
    number = value * 100 if value <= 1 else value
    number = round(number, 1)
    if number == int(number):
        number = int(number)
    return f"{number}%"


# Figures that are supposed to come from the dataset at runtime.
BOUND_FIGURES = [
    as_percent(DATA["chiefOfStaff"]["bonusContext"]["prevalence"]),
    as_percent(DATA["chiefOfStaff"]["bonusContext"]["averagePercentAmongRecipients"]),
    as_percent(DATA["chiefOfStaff"]["equityContext"]["prevalence"]),
    as_percent(DATA["executiveAssistant"]["bonusContext"]["discretionaryShare"]),
    as_percent(DATA["executiveAssistant"]["bonusContext"]["guaranteedShare"]),
    as_percent(DATA["executiveAssistant"]["equityContext"]["cSuiteShare"]),
    as_percent(DATA["executiveAssistant"]["equityContext"]["independentShare"]),
]

# Figures and links the 2026 dataset retired.
RETIRED_STRINGS = [
    "2025-cosc-salary-survey",
    "Chief of Staff Collective 2025",
    "CoS Collective 2025",
    "56% received",
    "56% of Chiefs of Staff",
    "19% of base",
    "54% held equity",
    "56 percent",
    "19 percent",
]

# Brand rules. The board admits roles by a published pay midpoint, so any word
# implying human screening is an overclaim, not a style preference.
BANNED_WORDS = ["vetted", "curated", "Vetted", "Curated"]


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda p: p.name)
def test_no_retired_survey_figures_or_links(path):
    text = prose(path)
    found = [s for s in RETIRED_STRINGS if s in text]
    assert not found, f"{path.name} still carries retired survey copy: {found}"


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda p: p.name)
def test_survey_percentages_are_not_retyped(path):
    text = prose(path)
    found = [f for f in BOUND_FIGURES if f in text]
    assert not found, (
        f"{path.name} hardcodes {found}. Read the value from compensation-data.json "
        "instead, so the next dataset update carries the sentence with it."
    )


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda p: p.name)
def test_no_banned_brand_words(path):
    text = prose(path)
    found = [w for w in BANNED_WORDS if w in text]
    assert not found, f"{path.name} uses banned wording: {found}"


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda p: p.name)
def test_no_em_dashes(path):
    text = prose(path)
    assert "\u2014" not in text, f"{path.name} contains an em-dash"


def test_dataset_points_at_the_2026_survey():
    for section in ("bonusContext", "equityContext"):
        block = DATA["chiefOfStaff"][section]
        assert "2026" in block["source"], block["source"]
        assert "2026-cosc" in block["sourceUrl"], block["sourceUrl"]


def test_offer_evaluator_collects_a_valuation_date():
    """The result claims the 409A date matters, so the form has to collect it."""
    markup = (TOOLS / "offer-evaluator.html").read_text(encoding="utf-8")
    assert 'id="eob-oe-409a-date"' in markup


def test_offer_evaluator_has_no_silent_salary_shorthand():
    script = (TOOLS / "offer-evaluator-v2.js").read_text(encoding="utf-8")
    assert "base *= 1000" not in script, (
        "The under-1000 shorthand made 999 mean $999,000 and 1000 mean $1,000."
    )
    assert "validateInputs" in script


def test_offer_evaluator_does_not_call_a_guaranteed_floor_the_target_bonus():
    script = (TOOLS / "offer-evaluator-v2.js").read_text(encoding="utf-8")
    assert '"Bonus used for target cash"' in script
    assert '["Target bonus",money(annualBonusUsed)]' not in script


def test_readiness_quiz_reports_ties():
    markup = (TOOLS / "readiness-quiz.html").read_text(encoding="utf-8")
    assert "allLevel" in markup
    assert "Your lowest score is shared by" in markup
