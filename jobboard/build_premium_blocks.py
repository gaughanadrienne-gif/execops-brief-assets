#!/usr/bin/env python
"""Regenerate the `premium` blocks in tools/compensation-data.json from roles.json.

Fixes 2026-08-18 audit finding C1: the Offer Evaluator graded offers against a
hand-built copy of the board frozen at 2026-07-31 while roles.json refreshes
daily. This script recomputes the three premium cuts from the live board and
stamps each block with an asOf date, and run_refresh.bat calls it right after
build_comp_explorer.py so the figures can never be older than the board.

Method notes:
- Midpoint = (comp_low + comp_high) / 2 of the published figures.
- HOURLY rows are EXCLUDED from every displayed statistic. roles.json's own
  _note says hourly rates are annualized "ONLY to apply the floor, never for
  display" (audit finding M4). Hourly rows are detected by magnitude
  (comp_high < 1000).
- Raises instead of writing on any invariant failure (floor breach on an
  annual row, sample below MIN_SAMPLE, missing category), same philosophy as
  build_comp_explorer.py: a bad board cannot publish a figure. The write is
  temp-file-then-os.replace, so failure leaves the previous file intact.
"""
import json
import os
import statistics
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROLES = os.path.join(HERE, "roles.json")
COMP = os.path.normpath(os.path.join(HERE, "..", "tools", "compensation-data.json"))

CUTS = {
    "executiveAssistant": "Executive Assistant",
    "chiefOfStaff": "Chief of Staff",
    "executiveOperations": "Executive Operations",
}
MIN_SAMPLE = 10
FLOOR = 100000
HOURLY_THRESHOLD = 1000  # comp_high below this = verbatim $/hr row


def q(vals, p):
    """Linear-interpolation percentile matching the original hand-built blocks."""
    s = sorted(vals)
    if len(s) == 1:
        return float(s[0])
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def main():
    with open(ROLES, encoding="utf-8") as fh:
        board = json.load(fh)
    roles = board["roles"]

    with open(COMP, encoding="utf-8") as fh:
        comp = json.load(fh)

    today = date.today().isoformat()
    summary = []
    for key, cat in CUTS.items():
        rows = [r for r in roles if r.get("category") == cat
                and isinstance(r.get("comp_low"), (int, float))
                and isinstance(r.get("comp_high"), (int, float))]
        annual = [r for r in rows
                  if r.get("comp_period") != "hr" and r["comp_high"] >= HOURLY_THRESHOLD]
        hourly_excluded = len(rows) - len(annual)
        if len(annual) < MIN_SAMPLE:
            raise SystemExit(f"REFUSING TO WRITE: {cat} sample {len(annual)} below {MIN_SAMPLE}")
        mids = [(r["comp_low"] + r["comp_high"]) / 2 for r in annual]
        low_breach = [m for m in mids if m < FLOOR]
        if low_breach:
            raise SystemExit(f"REFUSING TO WRITE: {cat} has {len(low_breach)} annual midpoints below the ${FLOOR:,} floor")

        block = comp[key]["premium"]
        block["p25"] = round(q(mids, 0.25))
        block["median"] = round(statistics.median(mids))
        block["p75"] = round(q(mids, 0.75))
        block["medianPublishedLow"] = round(statistics.median(r["comp_low"] for r in annual))
        block["medianPublishedHigh"] = round(statistics.median(r["comp_high"] for r in annual))
        block["sample"] = len(annual)
        block["asOf"] = today
        if hourly_excluded:
            block["hourlyExcluded"] = hourly_excluded
        elif "hourlyExcluded" in block:
            del block["hourlyExcluded"]
        summary.append(f"{key}: n={len(annual)} (hourly excluded {hourly_excluded}) "
                       f"p25={block['p25']:,} med={block['median']:,} p75={block['p75']:,}")

    tmp = COMP + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(comp, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, COMP)
    print(f"premium blocks regenerated {today}")
    for line in summary:
        print(" ", line)


if __name__ == "__main__":
    main()
