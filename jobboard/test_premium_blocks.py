# -*- coding: utf-8 -*-
"""Guards for the Offer Evaluator's premium blocks (2026-08-18 audit C1).

The failure mode this exists to kill: the premium blocks freezing while
roles.json moves daily. These tests recompute the blocks from the current
board and assert the stored file matches, so a stale file fails the suite
instead of quietly grading offers against last month's market.
"""
import json
import os
import statistics
from datetime import date

import build_premium_blocks as bpb

HERE = os.path.dirname(os.path.abspath(__file__))


def _load():
    with open(os.path.join(HERE, "roles.json"), encoding="utf-8") as fh:
        roles = json.load(fh)["roles"]
    with open(bpb.COMP, encoding="utf-8") as fh:
        comp = json.load(fh)
    return roles, comp


def _annual(roles, cat):
    rows = [r for r in roles if r.get("category") == cat
            and isinstance(r.get("comp_low"), (int, float))
            and isinstance(r.get("comp_high"), (int, float))]
    return [r for r in rows
            if r.get("comp_period") != "hr" and r["comp_high"] >= bpb.HOURLY_THRESHOLD]


def test_premium_blocks_match_current_board():
    roles, comp = _load()
    for key, cat in bpb.CUTS.items():
        annual = _annual(roles, cat)
        mids = [(r["comp_low"] + r["comp_high"]) / 2 for r in annual]
        block = comp[key]["premium"]
        assert block["sample"] == len(annual), (
            f"{key}: stored sample {block['sample']} != board {len(annual)}; "
            "run build_premium_blocks.py")
        assert block["median"] == round(statistics.median(mids)), (
            f"{key}: stored median {block['median']} != recomputed; "
            "run build_premium_blocks.py")


def test_premium_blocks_carry_recent_asof():
    _, comp = _load()
    for key in bpb.CUTS:
        as_of = comp[key]["premium"].get("asOf")
        assert as_of, f"{key}: premium block has no asOf stamp"
        age = (date.today() - date(*[int(x) for x in as_of.split("-")])).days
        assert age <= 7, (
            f"{key}: premium asOf {as_of} is {age} days old; the daily "
            "refresh step is not running")


def test_premium_blocks_respect_floor_and_hourly_rule():
    roles, comp = _load()
    for key, cat in bpb.CUTS.items():
        annual = _annual(roles, cat)
        for r in annual:
            assert (r["comp_low"] + r["comp_high"]) / 2 >= bpb.FLOOR
        block = comp[key]["premium"]
        assert block["sample"] >= bpb.MIN_SAMPLE
        # hourly rows must not be inside the displayed stats
        hourly = [r for r in roles if r.get("category") == cat
                  and r.get("comp_period") == "hr"]
        if hourly:
            assert block.get("hourlyExcluded") == len(hourly)
