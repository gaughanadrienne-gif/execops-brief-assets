# Tool fixes 2026-08-17: the parts an agent cannot ship

Companion to `EOB_Tools_PrePromotion_Audit_2026-08-16.md`. Everything in this
file lives in a Squarespace code block, so it reaches the live site only when
the owner pastes it. The repo-side half of the same release is already applied
in this working tree and is listed at the bottom for cross-checking.

**Before pasting anything, diff the local wrapper against the live page.**
`Website/pages_html/*.html` is a working source, not a mirror: it has carried
unpasted rewrites before. Build every paste from the live markup and apply
these pairs to it. The line numbers below are from the local files on
2026-08-17 and are a locator, not an address.

The authoritative figures are in `tools/compensation-data.json`
(`chiefOfStaff.bonusContext` and `chiefOfStaff.equityContext`): Chief of Staff
Collective **2026**, n=56, **57 percent** receive a bonus, recipients average
**16 percent** of base, **77 percent** hold equity. The retired 2025 figures
are 56 percent, 19 percent and 54 percent.

---

## 1. `/salary-benchmarker` wrapper (`Website/pages_html/salary-benchmarker.html`)

This is the one blocking the Monday post. Two occurrences, one visible and one
inside the FAQ schema. Change both or the page contradicts its own structured
data.

### 1a. Visible FAQ answer (line 137)

FIND
```
Not always. In a small Chief of Staff Collective survey, 56 percent received a bonus and recipients averaged 19 percent of base. That is useful context, not a universal entitlement or role-wide target.
```

REPLACE
```
Not always. In the small Chief of Staff Collective 2026 survey (n=56), 57 percent received a bonus and recipients averaged 16 percent of base. That is useful context, not a universal entitlement or role-wide target.
```

### 1b. FAQPage schema answer (line 210)

FIND
```
Not always. In a small Chief of Staff Collective survey, 56 percent received a bonus and recipients averaged 19 percent of base. That is context, not a universal entitlement or role-wide target.
```

REPLACE
```
Not always. In the small Chief of Staff Collective 2026 survey (n=56), 57 percent received a bonus and recipients averaged 16 percent of base. That is context, not a universal entitlement or role-wide target.
```

---

## 2. `/offer-evaluator` wrapper (`Website/pages_html/offer-evaluator.html`)

### 2a. Visible FAQ answer (line 143)

FIND
```
In a small Chief of Staff Collective survey, 56 percent received a bonus and recipients averaged 19 percent of base. EA data is different: C-Suite Assistants reports 52 percent discretionary and 16 percent guaranteed bonus, while the independent survey's 8.66 percent average has an unclear denominator. The tool keeps those contexts separate.
```

REPLACE
```
In the small Chief of Staff Collective 2026 survey (n=56), 57 percent received a bonus, recipients averaged 16 percent of base, and 77 percent held equity. EA data is different: C-Suite Assistants reports 52 percent discretionary and 16 percent guaranteed bonus, while the independent survey's 8.66 percent average has an unclear denominator. The tool keeps those contexts separate.
```

### 2b. FAQPage schema answer (line 216)

FIND
```
In a small CoS survey, 56 percent received a bonus and recipients averaged 19 percent of base. EA survey results differ, so the evaluator keeps role-specific bonus context separate.
```

REPLACE
```
In the small Chief of Staff Collective 2026 survey (n=56), 57 percent received a bonus and recipients averaged 16 percent of base. EA survey results differ, so the evaluator keeps role-specific bonus context separate.
```

### 2c. Optional, sources paragraph (line 122)

The paragraph says bonus and equity incidence is "linked in the result", which
is true: the tool cites the 2026 survey from the dataset, so no change is
required. If the owner wants the source named on the wrapper as well, add this
after the C-Suite Assistants sentence.

```
Bonus and equity incidence for Chief of Staff comes from the <a href="https://www.chiefofstaffcollective.org/2026-cosc-salary-survey" target="_blank" rel="noopener">Chief of Staff Collective 2026 survey</a> (n=56).
```

---

## 3. `/readiness-quiz` wrapper (`Website/pages_html/readiness-quiz.html`)

The wrapper's opening copy is already the cautious version, so audit finding 6
needs nothing here (see the note in section 7). What it does overpromise is the
tie: it states as fact that the result "names your weakest two". The tool now
reports ties instead of breaking them by source order, so these three
sentences have to follow.

### 3a. How it works (line 118)

FIND
```
with your two weakest highlighted. The tool then points you at the specific library articles that address those two gaps, because a low score on judgment and a low score on business acumen call for completely different work.
```

REPLACE
```
with your two suggested focus areas highlighted. When several areas tie at the same score, the result says so rather than choosing between them. The tool then points you at the specific library articles that address those gaps, because a low score on judgment and a low score on business acumen call for completely different work.
```

### 3b. Visible FAQ answer (line 148)

FIND
```
The result names your weakest two and points you at the work. That's a plan, not a verdict.
```

REPLACE
```
The result names two suggested focus areas, says plainly when several areas are tied, and points you at the work. That's a plan, not a verdict.
```

### 3c. FAQPage schema answer (line 221)

FIND
```
The result names your weakest two competencies and points you at the work to close them.
```

REPLACE
```
The result names two suggested focus areas, reports a tie when competencies share the same score, and points you at the work to close them.
```

---

## 4. `/tools` hub (`Website/tools/tools-hub.html`)

The hub is held as the campaign destination anyway, but it carries the same tie
overclaim, and its quiz preview names two competencies the quiz does not
measure. The six real labels are business and operating acumen, communication
and influence, judgment and discretion, execution and follow-through, managing
up and the principal, and comfort with ambiguity. "Operating rhythm" and "data
fluency" are neither.

### 4a. Card copy (line 262)

FIND
```
It asks how often you actually do specific things, then names your weakest two.
```

REPLACE
```
It asks how often you actually do specific things, then names two suggested focus areas and flags any tie.
```

### 4b. Preview alt text (line 263)

FIND
```
aria-label="Example of the output: six competencies scored, with the weakest two named in words as well as marked on the chart."
```

REPLACE
```
aria-label="Example of the output: six competencies scored, with two suggested focus areas named in words as well as marked on the chart."
```

### 4c. Preview tag (line 271)

FIND
```
<span class="pv-tag">Weakest two: operating rhythm, data fluency</span>
```

REPLACE
```
<span class="pv-tag">Focus areas: business acumen, comfort with ambiguity</span>
```

---

## 5. Verify after pasting

1. View source on each pasted page and confirm zero hits for `56 percent`,
   `19 percent` and `weakest two`.
2. Confirm the FAQ schema block survived the paste: each changed sentence must
   appear twice, once visible and once inside the JSON-LD.
3. Hard-reload `/salary-benchmarker` and `/offer-evaluator` and confirm the
   iframes still render, since the CDN tools changed in the same release.
4. Re-run `python -m pytest tools/test_tool_copy.py` in this repo. It guards
   the repo half only. The wrapper half has no automated cover, which is why
   step 1 is manual.

---

## 6. Already applied in this repo (context for the reviewer)

- `tools/offer-evaluator.html`: the 2025 Collective source link swapped for
  2026, a 409A valuation-date field added, the banned word removed, and a
  297-line inert `text/plain` legacy script block deleted. That block never
  rendered but did ship retired figures inside the served HTML.
- `tools/offer-evaluator-v2.js`: every survey percentage now read from
  `compensation-data.json`, the under-1000 salary shorthand removed and
  replaced with explicit range validation, negatives rejected rather than
  silently made positive, the bonus row relabelled "Bonus used for target
  cash" with an explanation that a guaranteed minimum replaces the target
  rather than stacking, and the 409A valuation age reported.
- `tools/salary-benchmarker.html`: the EA bonus and equity incidence sentence
  now reads the dataset instead of quoting typed percentages.
- `tools/readiness-quiz.html`: ties reported instead of broken by source order,
  the cautious header sentence published, the "five skills" line now clearly
  describes the linked guide rather than the quiz, banned word and em-dash
  removed.
- `tools/test_tool_copy.py`: new, 29 tests, fails if any retired figure, any
  hardcoded survey percentage, any banned word or any em-dash appears in the
  published tools.

---

## 7. Two audit lines that did not survive checking

- **"One recommendation says five skills although the quiz measures six."**
  Both "five skills" sentences describe the linked guide *The Skills That
  Actually Get You Hired*, and that article does have exactly five numbered
  skills. The figure was right and the reference was ambiguous, so the wording
  now names the guide instead of being changed to six.
- **"The published wrapper says the six competencies are what the role actually
  runs on and promises a candid read."** That sentence is not in the wrapper.
  It was in the published tool, `tools/readiness-quiz.html`, and the cautious
  version the audit wanted was sitting unpublished in the stale duplicate at
  `Website/tools/readiness-quiz.html`. Fixed in the repo, not by a paste.

---

## 8. Out of scope, still open

Three consumers outside the tools carry the retired 2025 figures. None was
touched, because each one is correctly attributed to the 2025 survey and is
tied to article prose that would have to change with it.

- `eob-site-scripts.js`, the `chief-of-staff-salary-guide` stat graphic:
  `"56% / 54%"`, labelled as a small mixed-geography survey.
- `seo/faq-schema.json`: an answer citing "roughly 19% of base" and attributing
  it to the Chief of Staff Network 2025 report. That attribution looks wrong
  regardless of the update question: 19 percent is a Chief of Staff Collective
  figure, not a Chief of Staff Network one.
- `import/chief-of-staff-salary-guide.html` and
  `import/negotiate-chief-of-staff-offer.html`, which state the 2025 figures in
  prose with the 2025 link.

Deciding whether those articles move to the 2026 survey is an editorial call,
not a copy fix, and it needs the article, the graphic and the schema to move
together.
