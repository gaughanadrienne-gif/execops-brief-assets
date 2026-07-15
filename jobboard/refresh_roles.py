#!/usr/bin/env python3
"""
refresh_roles.py  --  Live-ish refresh for The Exec Ops Brief job board.

Rebuilds the board from recruiting agencies, direct job boards, and VC portfolio
feeds; applies the taxonomy and filtering rules documented in
REFRESH_README.md; and rewrites roles.json so a scheduled run stays fresh.

Design principles (see REFRESH_README.md):
  * COMP HONESTY: real published comp only. Never fabricate/estimate/infer.
    comp_low / comp_high = null unless the source publishes a figure.
  * RESILIENCE: every source parser is wrapped in try/except. One failing
    source never kills the run and never wipes good data.
  * DEDUPE: by apply_url and by (title, org, location).
  * The run date is passed in (argv[1] or env REFRESH_DATE); we avoid baking
    datetime.now() into the data. Falls back to today's date if not supplied.

Usage:
    python refresh_roles.py [YYYY-MM-DD]
    REFRESH_DATE=2026-07-04 python refresh_roles.py

Requires the firecrawl CLI on PATH (firecrawl scrape <url> --wait-for <ms> -o <file>).
"""

import os
import re
import sys
import json
import gzip
import time
import shutil
import subprocess
import tempfile
import urllib.request
import urllib.parse
from collections import Counter
from datetime import date, timedelta
from html import unescape as html_unescape

# --------------------------------------------------------------------------- #
# Paths / config
# --------------------------------------------------------------------------- #
HERE = os.path.dirname(os.path.abspath(__file__))
ROLES_PATH = os.path.join(HERE, "roles.json")

SCRATCH = os.environ.get(
    "REFRESH_SCRATCH",
    tempfile.gettempdir(),
)

# firecrawl resolves to a .cmd shim on Windows; shutil.which handles that.
FIRECRAWL = (
    shutil.which("firecrawl")
    or shutil.which("firecrawl.cmd")
    or "firecrawl"
)

# If the post-floor board comes back below this, we assume something went
# broadly wrong (network down, firecrawl broken) and REFUSE to overwrite
# roles.json, so a bad run never wipes a good board. The expanded board runs
# above 200 roles; 30 is deliberately conservative and catches broad pipeline
# failure without treating an ordinary hiring slowdown as an outage.
MIN_SAFE_TOTAL = 30

# THE BOARD PROMISE, enforced in code. Every published role clears this on the
# MIDPOINT of its published range; a role whose comp the source does not print
# is not published at all.
PAY_FLOOR = 100000
HOURS_PER_YEAR = 2080

# Politeness / runtime guards for the daily 7am run: these are small firms.
SCRAPE_MIN_INTERVAL = 0.8    # seconds between outbound fetches
# Hard cap on per-role detail fetches per run. Raised 90 -> 200 with the
# priority-1 sources: the board tripled, and most of the new detail pages are
# employer ATS pages that fetch_detail() reads over plain HTTP in ~1s rather than
# through firecrawl's browser. The cap is a runtime guard, and it is not a
# cosmetic one -- a BROAD or CONDITIONAL role that runs out of budget never gets
# a description, so scope_gate() cannot validate it and it is DROPPED. At 90,
# 69 real Executive Operations / COO roles were being starved and lost. enrich()
# now also spends the budget on scope-critical roles FIRST.
MAX_DETAIL_FETCHES = 200
_last_fetch_at = [0.0]


def _throttle():
    gap = time.time() - _last_fetch_at[0]
    if gap < SCRAPE_MIN_INTERVAL:
        time.sleep(SCRAPE_MIN_INTERVAL - gap)
    _last_fetch_at[0] = time.time()


DEFAULT_NOTE = (
    "REAL curated Executive Assistant, Executive Operations, and Chief of Staff "
    "roles for The Exec Ops Brief job board, aggregated from recruiting agencies, "
    "direct job boards, and VC portfolio feeds. "
    "PAY FLOOR (enforced in code since 2026-07-13): every role on this board "
    "carries a compensation figure PUBLISHED BY THE SOURCE whose midpoint -- "
    "(comp_low + comp_high) / 2, or the single figure where only one is "
    "published -- is at least $100,000. A role whose published midpoint falls "
    "below $100k is excluded, and a role whose source publishes no comp figure "
    "at all is excluded (there are no 'comp not listed' rows). No comp figure "
    "is ever estimated, inferred, or invented; comp honesty outranks board "
    "size. Where a posting publishes an HOURLY rate instead of a salary, "
    "comp_period='hr' and comp_low/comp_high hold the verbatim $/hr figures "
    "(annualized at 2080h ONLY to apply the floor, never for display). "
    "Most roles also carry a short summary excerpted VERBATIM from the posting "
    "(never paraphrased); summary is null rather than invented when the source "
    "lacks readable role-specific text. A benefits list (bonus, equity, 401(k), health "
    "coverage, PTO, etc) detected only where the posting states them. Apply "
    "links point to the original source listing."
)

# --------------------------------------------------------------------------- #
# Firecrawl helper
# --------------------------------------------------------------------------- #
def scrape(url, wait=3500):
    """Scrape a URL to markdown via the firecrawl CLI. Returns markdown text.

    Raises RuntimeError on failure so the caller's try/except can skip the
    source cleanly.
    """
    _throttle()
    fd, out = tempfile.mkstemp(suffix=".md", dir=SCRATCH)
    os.close(fd)
    try:
        proc = subprocess.run(
            [FIRECRAWL, "scrape", url, "--wait-for", str(wait), "-o", out],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
        )
        if not os.path.exists(out) or os.path.getsize(out) == 0:
            raise RuntimeError(
                f"firecrawl produced no output for {url} "
                f"(rc={proc.returncode}): {proc.stderr[:300]}"
            )
        with open(out, "r", encoding="utf-8", errors="replace") as fh:
            md = fh.read()
        if len(md.strip()) < 40:
            raise RuntimeError(f"firecrawl output too short for {url}")
        return md
    finally:
        try:
            os.remove(out)
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# Plain HTTP helper (added 2026-07-14 with the priority-1 sources)
#
# Every source added in the taxonomy release answers a plain GET/POST -- WordPress
# REST (Beacon Hill, LaSalle), a JSON search API (Consider, Getro), or
# server-rendered HTML (Chief of Staff Network, Pocketbook). firecrawl is a
# browser; using it for these would be an order of magnitude slower for no gain,
# and the 7am run has to finish. The ten original sources keep using scrape().
#
# SOFT-404: a 200 is not proof of a live page. Recruiterflow answers 200 with
# "This job does not exist" for a filled posting; Next.js boards answer 200 with
# a "not found" shell. Every page fetched here has its BODY checked.
# --------------------------------------------------------------------------- #
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

_SOFT_404 = (
    "this job does not exist", "job does not exist", "job not found",
    "no longer available", "position has been filled", "this position is closed",
    "page not found", "404 not found", "we can't find that page",
    "we couldn't find that page",
    "job you are looking for is no longer here",
    "job board you were viewing is no longer active",
)


def is_soft_404(text):
    """True when a 200 response is really a dead posting. Check the BODY."""
    if not text:
        return True
    low_all = text.lower()
    low = low_all[:4000]
    if any(m in low for m in _SOFT_404):
        return True
    # Databricks places its specific removed-page message after a large nav wall.
    return "has been removed, renamed, or is unavailable" in low_all


def http_get(url, headers=None, timeout=45, as_json=False, data=None):
    """Throttled GET (POST when `data` is given). Returns text or parsed JSON."""
    _throttle()
    h = {"User-Agent": UA,
         "Accept": "application/json" if as_json else "text/html,*/*",
         "Accept-Language": "en-US,en;q=0.9"}
    if headers:
        h.update(headers)
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        text = raw.decode("utf-8", "replace")
    return json.loads(text) if as_json else text


def http_json(url, data=None, headers=None, timeout=60):
    return http_get(url, headers=headers, timeout=timeout, as_json=True, data=data)


# --------------------------------------------------------------------------- #
# ROLE TAXONOMY + FILTERING RULES
#
# Source of truth: reference/EOB_Job_Board_Role_Taxonomy_and_New_Sources.xlsx
# (Adrienne, 2026-07-13). Three sheets, all three implemented here:
#
#   "Role Taxonomy"   -> TAXONOMY below: 130 titles across 5 VISIBLE CATEGORIES,
#                        each Include or Conditional.
#   "Filtering Rules" -> _EXCLUSION_RULES (functional / industry operations),
#                        _INCLUSION_SIGNALS (the 7 positive signals), and the
#                        conditional-title rule (ambiguous titles need >= 2
#                        inclusion signals in the job description).
#   "New Sources"     -> the parsers at the bottom of this file.
#
# Before 2026-07-14 classification was a hand-rolled EA/CoS heuristic and the
# board came out 92% Executive Assistant (73 of 79). The taxonomy is what lets
# real Chief of Staff and Executive Operations roles onto the board.
#
# HOW A TITLE IS CLASSIFIED
#   1. Normalize it (case, punctuation, "EA" -> executive assistant, "Sr." ->
#      senior, "&" -> and, "VP"/"SVP", "COO" -> chief operating officer, ...).
#   2. Find every TAXONOMY title that appears in it; keep the LONGEST match, so
#      "Director of Business Operations" beats the shorter "Director of
#      Operations" and lands in the right category.
#   3. No match -> the role is out. (This is the whole exclusion mechanism for
#      the thousands of engineering / sales / support roles on the new VC boards:
#      they simply do not match a taxonomy title.)
#
# HOW SCOPE IS VALIDATED ("a matching title is not enough for broad operations
# roles" -- the sheet's own quality-control rule)
#   * CORE titles (Executive Assistant / Chief of Staff family) are trusted on
#     the title alone. They are unambiguous.
#   * BROAD titles (Executive Operations / Director-VP of Operations / COO) are
#     additionally scanned against the job description for the functional and
#     industry exclusions (Sales Ops, People Ops, Manufacturing, Clinical, ...).
#   * CONDITIONAL titles (any category) must show >= 2 INCLUSION SIGNALS in the
#     description. No description -> not published. We do not guess at scope any
#     more than we guess at pay.
#   Both of those run in scope_gate(), after enrich() has the description text.
# --------------------------------------------------------------------------- #
CAT_EA = "Executive Assistant"
CAT_COS = "Chief of Staff"
CAT_XOPS = "Executive Operations"
CAT_DVP = "Director / VP of Operations"
CAT_COO = "COO / Operating Executive"

VISIBLE_CATEGORIES = [CAT_EA, CAT_COS, CAT_XOPS, CAT_DVP, CAT_COO]

INC = "Include"
CON = "Conditional"

# The "Role Taxonomy" sheet, verbatim (130 rows; 3 titles appear under two
# categories and are kept under the first, which is the sheet's own order).
TAXONOMY = [
    ("Executive Assistant", CAT_EA, INC),
    ("Senior Executive Assistant", CAT_EA, INC),
    ("Lead Executive Assistant", CAT_EA, INC),
    ("Executive Assistant to the CEO", CAT_EA, INC),
    ("Executive Assistant to the Founder", CAT_EA, INC),
    ("Executive Assistant to the President", CAT_EA, INC),
    ("Executive Assistant to the COO", CAT_EA, INC),
    ("Executive Assistant to the Chair", CAT_EA, INC),
    ("Executive Assistant to the Managing Partner", CAT_EA, INC),
    ("Executive Business Partner", CAT_EA, INC),
    ("Senior Executive Business Partner", CAT_EA, INC),
    ("Administrative Business Partner", CAT_EA, INC),
    ("Executive Partner", CAT_EA, INC),
    ("Strategic Executive Assistant", CAT_EA, INC),
    ("Chief Executive Assistant", CAT_EA, INC),
    ("Executive Support Lead", CAT_EA, INC),
    ("Executive Operations Coordinator", CAT_EA, INC),
    ("Executive Office Manager", CAT_EA, CON),
    ("Business Partner to the CEO", CAT_EA, CON),
    ("Executive Coordinator", CAT_EA, CON),
    ("Chief of Staff", CAT_COS, INC),
    ("Chief of Staff to the CEO", CAT_COS, INC),
    ("Chief of Staff to the Founder", CAT_COS, INC),
    ("Chief of Staff to the President", CAT_COS, INC),
    ("Chief of Staff to the COO", CAT_COS, INC),
    ("Deputy Chief of Staff", CAT_COS, INC),
    ("Associate Chief of Staff", CAT_COS, INC),
    ("Business Chief of Staff", CAT_COS, INC),
    ("Strategic Chief of Staff", CAT_COS, INC),
    ("Executive Chief of Staff", CAT_COS, INC),
    ("Chief of Staff, Office of the CEO", CAT_COS, INC),
    ("Chief of Staff and Operations", CAT_COS, INC),
    ("Chief of Staff and Strategy", CAT_COS, INC),
    ("Chief of Staff and Business Operations", CAT_COS, INC),
    ("Head of the Office of the CEO", CAT_COS, INC),
    ("Director, Office of the CEO", CAT_COS, INC),
    ("Principal, Office of the CEO", CAT_COS, INC),
    ("CEO Office Lead", CAT_COS, INC),
    ("Founder's Office Lead", CAT_COS, INC),
    ("President's Office Lead", CAT_COS, INC),
    ("Executive Office Director", CAT_COS, INC),
    ("Special Assistant to the CEO", CAT_COS, CON),
    ("Special Assistant to the President", CAT_COS, CON),
    ("Executive Advisor to the CEO", CAT_COS, CON),
    ("Senior Advisor to the CEO", CAT_COS, CON),
    ("Director of Executive Operations", CAT_XOPS, INC),
    ("Head of Executive Operations", CAT_XOPS, INC),
    ("Executive Operations Manager", CAT_XOPS, INC),
    ("Executive Operations Lead", CAT_XOPS, INC),
    ("Executive Operations Partner", CAT_XOPS, INC),
    ("Executive Operations Program Manager", CAT_XOPS, INC),
    ("Executive Office Operations Manager", CAT_XOPS, INC),
    ("Business Operations Manager", CAT_XOPS, INC),
    ("Senior Business Operations Manager", CAT_XOPS, INC),
    ("Business Operations Lead", CAT_XOPS, INC),
    ("Head of Business Operations", CAT_XOPS, INC),
    ("Director of Business Operations", CAT_XOPS, INC),
    ("Senior Director of Business Operations", CAT_XOPS, INC),
    ("VP of Business Operations", CAT_XOPS, INC),
    ("Strategy and Operations Manager", CAT_XOPS, INC),
    ("Senior Strategy and Operations Manager", CAT_XOPS, INC),
    ("Strategy and Operations Lead", CAT_XOPS, INC),
    ("Head of Strategy and Operations", CAT_XOPS, INC),
    ("Director of Strategy and Operations", CAT_XOPS, INC),
    ("Senior Director of Strategy and Operations", CAT_XOPS, INC),
    ("VP of Strategy and Operations", CAT_XOPS, INC),
    ("Strategic Operations Manager", CAT_XOPS, INC),
    ("Strategic Operations Lead", CAT_XOPS, INC),
    ("Director of Strategic Operations", CAT_XOPS, INC),
    ("Corporate Operations Manager", CAT_XOPS, INC),
    ("Corporate Operations Lead", CAT_XOPS, INC),
    ("Director of Corporate Operations", CAT_XOPS, INC),
    ("Head of Corporate Operations", CAT_XOPS, INC),
    ("Company Operations Lead", CAT_XOPS, INC),
    ("Head of Company Operations", CAT_XOPS, INC),
    ("Director of Organizational Operations", CAT_XOPS, INC),
    ("Director of Strategic Initiatives", CAT_XOPS, INC),
    ("Head of Strategic Initiatives", CAT_XOPS, INC),
    ("Special Projects Director", CAT_XOPS, INC),
    ("Executive Business Manager", CAT_XOPS, INC),
    ("Business Manager, Office of the CEO", CAT_XOPS, INC),
    ("Senior Business Operations Analyst", CAT_XOPS, INC),
    ("Strategy and Operations Analyst", CAT_XOPS, INC),
    ("Corporate Operations Analyst", CAT_XOPS, INC),
    ("Senior Operations Analyst", CAT_XOPS, CON),
    ("Transformation Office Lead", CAT_XOPS, CON),
    ("Enterprise Program Lead", CAT_XOPS, CON),
    ("Operating Cadence Lead", CAT_XOPS, CON),
    ("Director of Operations", CAT_DVP, INC),
    ("Senior Director of Operations", CAT_DVP, INC),
    ("Executive Director of Operations", CAT_DVP, CON),
    ("Head of Operations", CAT_DVP, INC),
    ("VP of Operations", CAT_DVP, INC),
    ("SVP of Operations", CAT_DVP, INC),
    ("Operations Lead", CAT_DVP, CON),
    ("Director of Administration and Operations", CAT_DVP, INC),
    ("Director of Company Operations", CAT_DVP, INC),
    ("Director of Enterprise Operations", CAT_DVP, INC),
    ("Director of Operational Excellence", CAT_DVP, CON),
    ("Head of Administration", CAT_DVP, CON),
    ("Director of Administration", CAT_DVP, CON),
    ("Administrative Director", CAT_DVP, CON),
    ("General Manager", CAT_DVP, CON),
    ("Managing Director", CAT_DVP, CON),
    ("Director of Business Management", CAT_DVP, CON),
    ("Chief Operating Officer", CAT_COO, INC),
    ("Deputy Chief Operating Officer", CAT_COO, INC),
    ("Associate Chief Operating Officer", CAT_COO, INC),
    ("Divisional Chief Operating Officer", CAT_COO, INC),
    ("Business Unit Chief Operating Officer", CAT_COO, INC),
    ("Regional Chief Operating Officer", CAT_COO, INC),
    ("Fractional Chief Operating Officer", CAT_COO, INC),
    ("Chief Administrative Officer", CAT_COO, INC),
    ("Chief Business Officer", CAT_COO, CON),
    ("Chief Management Officer", CAT_COO, INC),
    ("Operating Executive", CAT_COO, INC),
    ("Operating Partner", CAT_COO, CON),
    ("Head of Portfolio Operations", CAT_COO, INC),
    ("Director of Portfolio Operations", CAT_COO, INC),
    ("Senior Director of Portfolio Operations", CAT_COO, INC),
    ("VP of Portfolio Operations", CAT_COO, INC),
    ("Portfolio Operations Lead", CAT_COO, INC),
    ("Portfolio Company Operations Lead", CAT_COO, INC),
    ("Value Creation Director", CAT_COO, INC),
    ("Head of Value Creation", CAT_COO, INC),
    ("Value Creation Operating Partner", CAT_COO, INC),
    ("Portfolio Performance Director", CAT_COO, CON),
]

# Title normalization. Job titles in the wild are written every possible way
# ("Sr. EA to the CEO", "Chief of Staff / BizOps Lead", "VP, Strategy & Ops");
# the taxonomy is written one way. Normalize both ends and the match is honest.
_ABBREV = [
    (r"\bsr\.?\b", "senior"),
    (r"\bjr\.?\b", "junior"),
    (r"\bexec\.?\b", "executive"),
    (r"\bassist\.?\b", "assistant"),
    (r"\badmin\.?\b", "administrative"),
    (r"\bbiz\s*ops\b", "business operations"),
    (r"\bbizops\b", "business operations"),
    (r"\bstratops\b", "strategy and operations"),
    (r"\bops\b", "operations"),
    (r"\bea\b", "executive assistant"),
    (r"\bcos\b", "chief of staff"),
    (r"\bchief of staff\s*/\s*executive assistant\b",
     "chief of staff executive assistant"),
    (r"\bsenior vice president\b", "svp"),
    (r"\bvice president\b", "vp"),
    (r"\bcoo\b", "chief operating officer"),
    (r"\bcao\b", "chief administrative officer"),
    (r"\bceo\b", "ceo"),
]


def normalize_title(title):
    """A job title reduced to comparable words. Used on BOTH sides of the match."""
    t = (title or "").lower()
    t = t.replace("’", "'").replace("‘", "'")
    t = t.replace("&", " and ")
    # Punctuation -> spaces, but keep the apostrophe ("founder's office lead").
    t = re.sub(r"[^a-z0-9']+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    for pat, rep in _ABBREV:
        t = re.sub(pat, rep, t)
    return " " + re.sub(r"\s+", " ", t).strip() + " "


def _tax_variants(t):
    """A taxonomy title and its comma form.

    The sheet writes "VP of Strategy and Operations"; the market writes
    "VP, Strategy & Ops". Both mean the same job. Indexing the "of"-less variant
    turns a large class of real VC-board titles ("Director, Business Operations",
    "Head, Corporate Operations") from misses into matches. The variant of
    "Chief of Staff" is the nonsense string "chief staff", which simply never
    matches anything -- harmless.
    """
    base = normalize_title(t).strip()
    out = [base]
    alt = re.sub(r"\s+of\s+", " ", base).strip()
    if alt != base:
        out.append(alt)
    return out


# Pre-normalized taxonomy. Sorted longest-first only as a tiebreak convenience;
# classify_role() does the real earliest-then-longest selection.
_TAX_NORM = sorted(
    ((v, t, cat, act)
     for t, cat, act in TAXONOMY
     for v in _tax_variants(t)),
    key=lambda x: -len(x[0]),
)

# --------------------------------------------------------------------------- #
# Private-service / household exclusion. NOT in the xlsx -- it predates it and
# is still law: this is a corporate exec-ops board, not a domestic-staffing one.
# Matched against the TITLE, and (for the stronger tokens) the DESCRIPTION too,
# since a "Personal Assistant" that is really estate/family-home staff often
# only reveals itself in the body.
# --------------------------------------------------------------------------- #
_HOUSEHOLD_TITLE = ("nanny", "housekeeper", "estate manager", "house manager",
                    "household", "domestic", "gift & bill", "bill pay",
                    "property manager", "director of properties",
                    "hnw", "uhnw", "high net worth", "principal of",
                    "to principal", "to the principal")
_HOUSEHOLD_CONTEXT = ("family's home", "family home", "household staff",
                      "private residence", "personal residence",
                      "estate/vineyard", "family estate", "nanny",
                      "hnw principal", "uhnw")

# --------------------------------------------------------------------------- #
# "Filtering Rules" sheet -- EXCLUSIONS.
#
# Two strengths, deliberately:
#   _EXCL_TITLE  matched on the TITLE -> immediate exclusion. A "Director of
#                Revenue Operations" is a Sales Ops role however it is written.
#   _EXCL_DESC   matched on the DESCRIPTION -> excludes only BROAD titles, and
#                only on >= 2 distinct hits. This is what kills LaSalle's
#                "Director of Operations" whose posting is
#                "...all aspects of MANUFACTURING and operational performance
#                within a high-volume PRODUCTION environment", while leaving a
#                Director of Operations at a research nonprofit alone. One
#                stray mention of a factory in a company boilerplate paragraph
#                is not a functional scope; two is.
#
# Neither ever runs against a CORE Executive Assistant / Chief of Staff title.
# "Executive Assistant to the Chief People Officer" is an EA role, not an HR
# Ops role, and the board has published it for months.
# --------------------------------------------------------------------------- #
_EXCL_TITLE = re.compile(
    r"\b(?:people|human\s+resources|hr|talent|recruit\w*)\s+(?:operations|ops)\b"
    r"|\b(?:sales|revenue|rev|gtm|go[\s-]to[\s-]market|commercial)\s+(?:operations|ops)\b"
    r"|\b(?:marketing|growth|demand|brand)\s+(?:operations|ops)\b"
    r"|\b(?:customer|client|support|success|member|patient)\s+(?:operations|ops)\b"
    r"|\bproduct\s+(?:operations|ops)\b"
    r"|\b(?:clinical|healthcare|health\s*care|nursing|medical|care)\s+(?:operations|ops)\b"
    r"|\b(?:manufacturing|plant|production|factory|fab)\s+(?:operations|ops)\b"
    r"|\b(?:warehouse|logistics|fulfillment|distribution|transportation|fleet)\s+(?:operations|ops)\b"
    r"|\b(?:retail|store|restaurant|venue|field|branch|site)\s+(?:operations|ops)\b"
    r"|\b(?:it|network|cloud|security|infrastructure|data|platform|devops|technical|engineering)\s+(?:operations|ops)\b"
    r"|\b(?:facilities|workplace|office|real\s+estate)\s+(?:operations|ops)\b"
    r"|\b(?:supply\s+chain|procurement|sourcing|purchasing|inventory)\s+(?:operations|ops)\b"
    r"|\b(?:legal|finance|financial|accounting|payroll|treasury|tax|trading|credit|lending|claims)\s+(?:operations|ops)\b"
    r"|\bportfolio\s+manager\b|\binvestment\s+(?:portfolio|analyst|associate|manager)\b"
    r"|\bsecurity\s+operations\s+cent\w+\b|\bnoc\b|\bsoc\s+analyst\b",
    re.I)

# Broad operations titles are also out when the functional domain is separated
# from "operations" by words such as "strategy and" or appears as a suffix.
# Examples seen live: "Sales Strategy and Operations Manager", "Finance and
# Business Operations Lead", and "Business Operations Lead, Commercial Launch
# Sales". The adjacency-only expression above cannot catch those forms.
# This never runs against core EA / Chief of Staff titles, so an Executive
# Assistant supporting a Chief People Officer remains an EA role.
_EXCL_BROAD_TITLE_TOKEN = re.compile(
    r"\b(?:people|human\s+resources|hr|talent|recruit\w*|sales|revenue|gtm|"
    r"go[\s-]to[\s-]market|commercial|marketing|growth|demand|brand|customer|"
    r"client|support|success|member|patient|product|clinical|healthcare|"
    r"health\s*care|nursing|medical|manufacturing|plant|production|factory|"
    r"warehouse|logistics|fulfillment|distribution|transportation|fleet|"
    r"retail|store|restaurant|venue|field|branch|site|network|cloud|security|"
    r"infrastructure|data|platform|devops|technical|engineering|facilities|"
    r"workplace|real\s+estate|supply\s+chain|procurement|sourcing|purchasing|"
    r"inventory|legal|finance|financial|accounting|payroll|treasury|tax|"
    r"trading|credit|lending|claims)\b",
    re.I)

_EXCL_DESC = [
    ("Clinical / healthcare",
     r"\bclinical\s+(?:operations|trial|staff|team|care)\b|\bpatient\s+care\b"
     r"|\bpatients\b|\bnursing\b|\bphysicians?\b|\bclinic(?:s|al)\b"),
    ("Manufacturing / production",
     r"\bmanufacturing\b|\bproduction\s+(?:floor|line|environment|schedule)\b"
     r"|\bplant\s+(?:floor|manager|operations)\b|\bshop\s+floor\b|\bassembly\s+line\b"),
    ("Warehouse / logistics",
     r"\bwarehouse\b|\bdistribution\s+cent\w+\b|\bfulfillment\s+cent\w+\b"
     r"|\bfreight\b|\blast[\s-]mile\b|\binventory\s+management\b"),
    ("Retail / store / restaurant",
     r"\bstore\s+(?:manager|operations|level)\b|\brestaurant\b|\bfront[\s-]of[\s-]house\b"
     r"|\bretail\s+locations?\b|\bfoot\s+traffic\b"),
    ("Sales / revenue operations",
     r"\bsales\s+(?:operations|pipeline|quota|territory)\b|\brevenue\s+operations\b"
     r"|\bcrm\s+administration\b|\bquota\s+attainment\b"),
    ("People / HR operations",
     r"\bhris\b|\bbenefits\s+administration\b|\bpayroll\s+processing\b"
     r"|\bemployee\s+relations\b|\bfull[\s-]cycle\s+recruit\w+\b"),
    ("IT / security operations",
     r"\bincident\s+response\b|\bon[\s-]call\s+rotation\b|\bsiem\b|\bkubernetes\b"
     r"|\bnetwork\s+uptime\b|\bsysadmin\b"),
]

# --------------------------------------------------------------------------- #
# "Filtering Rules" sheet -- the 7 INCLUSION SIGNALS.
# A Conditional title must show at least TWO of these in the job description.
# --------------------------------------------------------------------------- #
_INCLUSION_SIGNALS = [
    ("Executive reporting line",
     r"report(?:s|ing)?\s+(?:directly\s+)?(?:in)?to\s+(?:the\s+)?"
     r"(?:ceo|chief\s+executive|founder|co[\s-]?founder|president|coo"
     r"|chief\s+operating|chair(?:man|woman|person)?|managing\s+partner"
     r"|managing\s+director|executive\s+team|leadership\s+team|c[\s-]suite)"
     r"|\bpartner\s+to\s+the\s+(?:ceo|founder|president)\b"),
    ("Cross-functional ownership",
     r"cross[\s-]?functional|across\s+(?:multiple\s+)?(?:departments|teams|functions"
     r"|business\s+units)|company[\s-]wide|enterprise[\s-]wide|org(?:anization)?[\s-]wide"),
    ("Operating cadence",
     r"\bokrs?\b|operating\s+(?:cadence|rhythm|review)|leadership\s+(?:meetings|offsites)"
     r"|executive\s+(?:staff\s+)?meetings|priority\s+tracking|decision\s+log"
     r"|business\s+review|accountability\s+system|\bqbrs?\b|weekly\s+leadership"),
    ("Strategic planning",
     r"(?:annual|quarterly|long[\s-]range|strategic)\s+planning|strategic\s+initiatives"
     r"|enterprise\s+roadmap|operating\s+plan|goal[\s-]setting\s+process"),
    ("Executive decision support",
     r"board\s+(?:materials|decks?|meetings?|presentations?)|investor\s+(?:materials|updates?)"
     r"|executive\s+(?:brief\w*|summar\w+)|decision\s+support"
     r"|(?:analysis|recommendations)\s+(?:to|for)\s+(?:the\s+)?(?:ceo|executive|leadership)"),
    ("Special projects",
     r"special\s+projects|high(?:est)?[\s-]priority\s+(?:work|initiatives|projects)"
     r"|priority\s+initiatives|strategic\s+projects"),
    ("Systems and scale",
     r"company[\s-]wide\s+process|operating\s+system|scalable\s+(?:process|system|infrastructure)"
     r"|organizational\s+infrastructure|build\w*\s+(?:the\s+)?(?:systems|processes|infrastructure)"
     r"|governance|process\s+improvement"),
]


def count_signals(text):
    """How many of the 7 inclusion signals the posting actually states."""
    if not text:
        return 0
    return sum(1 for _, pat in _INCLUSION_SIGNALS if re.search(pat, text, re.I))


def excluded_by_description(text):
    """The functional/industry exclusion, read from the description.

    Returns the rule name when the posting shows >= 2 distinct mentions of one
    excluded domain, else None. Two hits, not one: a single stray word in a
    company boilerplate paragraph is not the role's scope.
    """
    if not text:
        return None
    for name, pat in _EXCL_DESC:
        if len(re.findall(pat, text, re.I)) >= 2:
            return name
    return None


def classify_role(title, context=""):
    """Classify a title against the taxonomy.

    Returns None when the role is out of scope, else a dict:
        category  -- one of the 5 VISIBLE_CATEGORIES
        action    -- INC or CON (CON => needs >= 2 inclusion signals)
        core      -- True for the unambiguous Executive Assistant / Chief of
                     Staff family. Core titles are never scope-scanned.
        matched   -- the taxonomy title that matched (for logging)
    """
    t = " " + (title or "").lower().replace("/", " / ") + " "
    ctx = ((title or "") + " " + (context or "")).lower()

    # Hard exclude: private-service / household. Predates the xlsx, still law.
    if any(x in t for x in _HOUSEHOLD_TITLE):
        return None
    if any(x in ctx for x in _HOUSEHOLD_CONTEXT):
        return None
    # A bare "Personal Assistant" (not an EA / CoS) is out.
    if "personal assistant" in t and not (
            "executive assistant" in t or "chief of staff" in t):
        return None

    norm = normalize_title(title)

    # Pick the taxonomy title that matches EARLIEST in the job title, and among
    # those the LONGEST.
    #
    # Earliest first, because the head of the title is the job:
    #   "Chief of Staff / Strategic Executive Assistant to the CEO" is a CHIEF OF
    #   STAFF role, but "Strategic Executive Assistant" is the longer phrase and
    #   longest-match alone would file it under Executive Assistant.
    #   Conversely "Executive Assistant to the CEO (with Chief of Staff duties)"
    #   really is an Executive Assistant, and leads with it.
    # Longest second, so "Director of Business Operations" beats the shorter
    # "Director of Operations" and lands in Executive Operations, not Director/VP.
    best = None
    for tax_norm, tax_raw, cat, act in _TAX_NORM:
        pos = norm.find(" " + tax_norm + " ")
        if pos < 0:
            continue
        key = (pos, -len(tax_norm))
        if best is None or key < best[0]:
            best = (key, tax_norm, tax_raw, cat, act)
    if not best:
        return None
    _, tax_norm, tax_raw, cat, act = best

    core = cat in (CAT_EA, CAT_COS)

    # An EA who also carries an operations mandate ("Executive Assistant to
    # Founder & Operations") belongs in Executive Operations -- the board has
    # bucketed those that way since launch. Only when the OPERATIONS word is
    # outside the matched taxonomy title, so "Executive Operations Coordinator"
    # (an EA title in the sheet) stays where the sheet puts it.
    if cat == CAT_EA and " operations " in norm and "operations" not in tax_norm:
        cat = CAT_XOPS               # ...but core stays True: still an EA role.

    # The title-level functional exclusion never runs against a core EA/CoS
    # title. "Executive Assistant to the Chief People Officer" is an EA job.
    if not core and (_EXCL_TITLE.search(title or "")
                     or _EXCL_BROAD_TITLE_TOKEN.search(title or "")):
        return None

    return {"category": cat, "action": act, "core": core, "matched": tax_raw}


def classify(title, context=""):
    """The board category for a title, or None. Thin wrapper over classify_role
    so the ten pre-existing source parsers keep their original call signature."""
    r = classify_role(title, context)
    return r["category"] if r else None


def seniority_of(title):
    """Seniority label. An Executive Assistant TO a VP is not a VP, so the
    exec-level labels are only read off titles that are not EA titles."""
    t = title.lower()
    is_ea = "executive assistant" in t or re.search(r"\bea\b", t)
    if not is_ea:
        if re.search(r"\bchief operating officer\b|\bcoo\b|\bchief \w+ officer\b", t):
            return "Executive"
        if re.search(r"\b(?:vp|svp|vice president)\b|\bhead of\b", t):
            return "VP"
    if "chief of staff" in t:
        return "Lead"
    if "director" in t:
        return "Director"
    if "senior" in t or "sr." in t or "sr " in t:
        return "Senior"
    return ""


# --------------------------------------------------------------------------- #
# Comp parsing  (NEVER invent -- only read what is printed)
#
# Rewritten 2026-07-13 (pay-floor release). The old version scanned a series of
# label windows and took the FIRST regex hit in each, which had two failure
# modes: a stray "$475/mo commuter benefit" sitting near a comp label could be
# read as a salary, and any window containing the word "hourly" lost its whole
# annual fallback.
#
# The new version enumerates EVERY money figure in the text, decides each one's
# period (annual / hourly / other) from the unit printed beside it, rejects
# figures sitting in a disqualifying context (stipends, allowances, monthly
# amounts), scores what survives, and takes the best. A figure is only ever
# accepted when the posting MARKS it as money ("$", a "k" suffix, or an explicit
# annual unit) AND anchors it to pay (a comp label, or that same unit). Prose
# like "competitive", "commensurate with experience", or a bare "DOE" yields
# nothing. Nothing is estimated, inferred, or interpolated -- ever.
# --------------------------------------------------------------------------- #

# A money figure: "165,000" | "165000" | "165" | "44.50", optional K suffix.
# The comma / long form must be tried first so "95000" is not read as "950".
_FIGURE = r"(?<![\d,.])(\d{1,3}(?:,\d{3})+|\d{2,6})(?:\.(\d{2}))?(?![\d])\s*([kK])?"

# The unit is often printed on BOTH ends of a range ("$130,000.00/yr -
# $150,000.00/yr", "$44/hr to $50/hr"), so the range allows an inline unit
# before the dash. Non-capturing: groups stay 1-6 = (num, cents, k) x 2.
_INLINE_UNIT = (r"(?:\s*(?:/\s*(?:yr|year|hr|hour|annum)"
                r"|per\s+(?:year|hour|annum)|annually|hourly))?")
_RANGE_RE = re.compile(
    r"\$?\s*" + _FIGURE + _INLINE_UNIT
    + r"\s*(?:-|–|—|to|through)\s*\$?\s*" + _FIGURE)
_BARE_RE = re.compile(_FIGURE)

_ANNUAL_UNIT = re.compile(
    r"^\s*(?:\.00)?\s*(?:/\s*(?:yr|year|annum)|per\s+(?:year|annum)|a\s+year"
    r"|annually|annual(?:ized)?|/\s*ann|per\s+yr)", re.I)
_HOURLY_UNIT = re.compile(
    r"^\s*(?:/\s*(?:hr|hour)|per\s+hour|an\s+hour|a\s+hour|hourly)", re.I)
_OTHER_UNIT = re.compile(
    r"^\s*(?:/\s*(?:mo|month|wk|week|day)|per\s+(?:month|week|day)|monthly"
    r"|weekly|daily|%|percent|million|billion|[mMbB]\b)", re.I)

# A comp label printed close BEFORE the figure ("Salary: $150,000",
# "Compensation | $150k", "base of $150,000", "paying up to $150,000").
_LABEL_RE = re.compile(
    r"(?:compensation|salary|salaried|base\s+pay|base\s+salary|pay\s+range"
    r"|pay\s+rate|hiring\s+range|target\s+comp\w*|\bcomp\b|\bpay\b|\bbase\b"
    r"|\bearn\w*|paying|\brate\b|\brange\b|\bdoe\b|\bup\s+to\b|starting\s+at)",
    re.I)
# ...or just AFTER it ("200k base", "$150,000 DOE", "150-180K commensurate").
_TRAIL_LABEL_RE = re.compile(
    r"^\s*(?:base\b|salary|annual\w*|per\s+year|\bdoe\b|compensation"
    r"|depending\s+on\s+experience|commensurate)", re.I)

# Context that disqualifies a figure from ever being a salary. Deliberately
# conservative: only phrases whose number could plausibly survive the $40k-$600k
# sanity band and masquerade as pay. Groupe Insearch really does print
# "Gym reimbursement $750/yr" and "Commuter benefits $475/mo" on pages that
# publish NO salary -- those must never become someone's compensation.
# ALWAYS disqualifying: a perk is never a salary, whatever unit it is printed in.
# "Gym reimbursement $750/yr" carries an annual unit and is still not pay.
_DISQ_HARD_RE = re.compile(
    r"reimburse\w*|stipend|allowance|commuter|gym\b|wellness|fitness|tuition"
    r"|square\s+feet|sq\.?\s*ft|zip\s*code", re.I)

# Disqualifying ONLY when the figure does not carry its own pay period.
# Beacon Hill writes "offers 25 hours per week, and pays $25-$35/hour": the
# "/hour" is bolted to the number and is authoritative; the "per week" is a
# SCHEDULE elsewhere on the line. Reading the schedule as the pay period threw
# away a real, published hourly rate.
_DISQ_PERIOD_RE = re.compile(
    r"per\s*month|/\s*mo\b|monthly|weekly|per\s+week|bi-?weekly", re.I)

# Scrubbed before scanning so their digits can never be misread as money. URLs
# and UUIDs are the big one: a Top Echelon detail page that publishes NO figure
# still carries ".../portals/4384ddd4-53cf-4f9f-be2f-180d5e77ccf9/..." and a
# "<Base64-Image-Removed>" placeholder. A number living inside a link, an image
# tag, a hex id or a UUID is never a published salary.
_PRESCRUB = [
    (re.compile(r"!?\[[^\]]*\]\([^)]*\)"), " "),      # markdown links / images
    (re.compile(r"<[^>\n]{0,160}>"), " "),            # html, <Base64-Image-Removed>
    (re.compile(r"https?://\S+|www\.\S+"), " "),      # bare URLs
    (re.compile(r"base\s*-?\s*64", re.I), " "),       # "Base64" is not a base salary
    # hex / uuid fragments -- MUST contain a letter, or this eats plain 6-digit
    # salaries ("$75000 - $105000": "105000" is itself [0-9a-f]{6}).
    (re.compile(r"\b(?=[0-9a-f]{6,}\b)[0-9a-f]*[a-f][0-9a-f]*\b", re.I), " "),
    (re.compile(r"401\s*\(?\s*k\s*\)?", re.I), " retirement-plan "),
    (re.compile(r"403\s*\(?\s*b\s*\)?", re.I), " retirement-plan "),
    (re.compile(r"\b(?:19|20)\d{2}\b"), " "),         # years
    (re.compile(r"\bID\s*j?-?\d+", re.I), " "),       # ATS job ids
]


def _prep(text):
    t = text.replace(" ", " ").replace("–", "-").replace("—", "-")
    for rx, rep in _PRESCRUB:
        t = rx.sub(rep, t)
    return t


def _to_annual(num_str, cents, k_flag):
    n = float(num_str.replace(",", ""))
    if cents:
        n += float("0." + cents)
    if k_flag or n < 1000:
        n *= 1000
    return int(round(n))


def _to_rate(num_str, cents, k_flag):
    if k_flag:
        return None                     # "$50K/hr" is not an hourly rate
    n = float(num_str.replace(",", ""))
    if cents:
        n += float("0." + cents)
    return n


def _sane(n):
    return n is not None and 40000 <= n <= 600000


def _sane_hr(v):
    return v is not None and 15 <= v <= 300


def _period_after(text, pos):
    """The unit printed immediately after a figure: 'yr'|'hr'|'other'|''."""
    tail = text[pos:pos + 22]
    if _HOURLY_UNIT.match(tail):
        return "hr"
    if _ANNUAL_UNIT.match(tail):
        return "yr"
    if _OTHER_UNIT.match(tail):
        return "other"
    return ""


def _labelled(text, start, end=None):
    """True when a comp label is printed right before (or right after) a figure."""
    if _LABEL_RE.search(text[max(0, start - 60):start]):
        return True
    if end is not None and _TRAIL_LABEL_RE.match(text[end:end + 30]):
        return True
    return False


def _disqualified(text, start, end, period=""):
    """Disqualifying context, read ONLY on the figure's own line.

    The window must NOT cross a newline. Tack Advisors prints

        "... CA (hybrid, 4 days per week)\n\nCOMPENSATION\n$150K - $180K base"

    and a flat character lookback swallows "per week" -- a SCHEDULE, not a pay
    period -- which would silently delete a real, published $150k-$180k salary.
    A stipend or a schedule on a NEIGHBOURING line says nothing about the figure
    on this one.

    `period` is the unit printed on the figure ITSELF ("hr" / "yr"). When the
    posting bolts a pay period onto the number, that beats a schedule word
    sharing the line: Beacon Hill writes "offers 25 hours per week, and pays
    $25-$35/hour", and reading its schedule as the pay period threw away a real,
    published hourly rate. A PERK (_DISQ_HARD_RE) is never pay whatever unit it
    wears -- "Gym reimbursement $750/yr" is annual and still not a salary.
    """
    ls = text.rfind("\n", 0, start) + 1              # start of this line
    le = text.find("\n", end)
    if le == -1:
        le = len(text)
    window = text[max(ls, start - 55):min(le, end + 25)]
    if _DISQ_HARD_RE.search(window):
        return True
    if period in ("hr", "yr"):
        return False
    return bool(_DISQ_PERIOD_RE.search(window))


def _candidates(text):
    """Every money figure / range in the text, with its span, unit and context."""
    out = []
    consumed = []                        # spans already claimed by a range

    for m in _RANGE_RE.finditer(text):
        period = _period_after(text, m.end())
        if not period:
            # "$130,000.00/yr - $150,000.00/yr": the unit is printed on the
            # FIRST figure too. Peek there before giving up.
            period = _period_after(text, max(m.end(1), m.end(2) or 0, m.end(3) or 0))
        if _disqualified(text, m.start(), m.end(), period):
            continue
        out.append({
            "kind": "range", "start": m.start(), "end": m.end(),
            "g": (m.group(1), m.group(2), m.group(3),
                  m.group(4), m.group(5), m.group(6)),
            "period": period,
            "label": _labelled(text, m.start(), m.end()),
            "dollar": "$" in text[max(0, m.start() - 2):m.end()],
        })
        consumed.append((m.start(), m.end()))

    for m in _BARE_RE.finditer(text):
        if any(s <= m.start() < e for s, e in consumed):
            continue
        period = _period_after(text, m.end())
        if _disqualified(text, m.start(), m.end(), period):
            continue
        out.append({
            "kind": "single", "start": m.start(), "end": m.end(),
            "g": (m.group(1), m.group(2), m.group(3)),
            "period": period,
            "label": _labelled(text, m.start(), m.end()),
            "dollar": text[max(0, m.start() - 2):m.start()].strip().endswith("$"),
        })
    return out


def extract_comp(text, field=False):
    """Return (comp_low, comp_high) in ANNUAL dollars, or (None, None).

    Hourly figures are not returned here -- extract_comp_hourly() handles those
    and the board stores them verbatim with comp_period='hr'.

    `field=True` tells the extractor that the caller has already isolated a
    dedicated COMP FIELD (a Career Group card's salary slot, CA People Search's
    "**Salary:**" line) whose only money figures ARE the salary. It relaxes the
    "must sit next to a comp label" anchor -- the field itself is the label --
    but it does NOT relax anything else: the figure must still be marked as
    money, still pass the sanity band, and still survive the disqualify rules.
    """
    if not text:
        return None, None
    t = _prep(text)
    best, best_score = None, 0
    for c in _candidates(t):
        if c["period"] in ("hr", "other"):
            continue
        g = c["g"]
        if c["kind"] == "range":
            # Bloom Talent prints "150-180K DOE": the "k" suffix is written ONCE,
            # on the SECOND figure, and it governs both ends. So the k flag for
            # this candidate is (first k OR second k), and that is also what
            # marks the pair as money.
            kflag = g[2] or g[5]
            lo = _to_annual(g[0], g[1], kflag)
            hi = _to_annual(g[3], g[4], g[5] or g[2])
            if lo > hi:
                lo, hi = hi, lo
            if not (_sane(lo) and _sane(hi)):
                continue
            score = 2                    # a two-ended range is a strong signal
        else:
            kflag = g[2]
            lo = hi = _to_annual(g[0], g[1], kflag)
            if not _sane(lo):
                continue
            score = 1 if kflag else 0    # a "k" suffix is itself a comp signal
        if c["period"] == "yr":
            score += 2
        if c["label"]:
            score += 2
        if c["dollar"]:
            score += 1

        # HONESTY GATE.
        #
        # MARKED: the posting must mark the figure as money -- a "$", a "k"
        # suffix, or an explicit annual unit. This is non-negotiable for both
        # kinds. It is what stops "100-200 employees" from becoming a
        # $100k-$200k salary, and it is how "<Base64-Image-Removed> base" once
        # became a $64,000 offer.
        #
        # ANCHORED: a LONE figure additionally has to be tied to pay -- a comp
        # label beside it ("Salary: $170,000"), an annual unit ("$170,000/yr"),
        # or a caller-isolated comp field. A single "$150,000" floating in a JD
        # could be a budget, a fund size, or a revenue target.
        #
        # A two-ended, money-marked RANGE ("150-180K+ DOE", "$120K-$140K") needs
        # no label: nothing else in a job posting is written that way. Requiring
        # one here silently deleted all 8 Bloom Talent salaries, because Bloom
        # writes "150-180K+ DOE" with no "$", no label, and a "+" that blocks the
        # trailing-label match.
        marked = c["dollar"] or bool(kflag) or c["period"] == "yr"
        if not marked:
            continue
        if c["kind"] == "single":
            anchored = c["label"] or c["period"] == "yr" or field
            if not anchored:
                continue

        if score > best_score:
            best, best_score = (lo, hi), score
    return best if best else (None, None)


def extract_comp_hourly(text, field=False):
    """Return (low, high) in $/hr where the posting prints an HOURLY rate.

    Same honesty rule as extract_comp: an hourly UNIT must be printed next to
    the figure. Stored with comp_period='hr' and displayed verbatim -- never
    converted into a salary for display. The $100k floor annualizes it (x2080)
    for FILTERING only.
    """
    if not text:
        return None, None
    t = _prep(text)
    best, best_score = None, 0
    for c in _candidates(t):
        if c["period"] != "hr":
            continue
        g = c["g"]
        if c["kind"] == "range":
            lo = _to_rate(g[0], g[1], g[2] or g[5])
            hi = _to_rate(g[3], g[4], g[5])
            if lo is None or hi is None:
                continue
            if lo > hi:
                lo, hi = hi, lo
            if not (_sane_hr(lo) and _sane_hr(hi)):
                continue
            score = 3
        else:
            lo = hi = _to_rate(g[0], g[1], g[2])
            if not _sane_hr(lo):
                continue
            score = 1
        if not (c["dollar"] or field):
            continue                     # an unmarked "40 hourly" is not a rate
        if c["label"]:
            score += 1
        if c["dollar"]:
            score += 1
        if score > best_score:
            best, best_score = (lo, hi), score
    return best if best else (None, None)


# --------------------------------------------------------------------------- #
# LinkedIn guest fetch  (the Truex Metier comp rescue, added 2026-07-13)
#
# Truex Metier's own site renders a LinkedIn widget that USED to print comp; as
# of 2026-07-13 it prints zero "$" characters, and firecrawl refuses linkedin.com
# outright ("we do not support this site"), so all four of their roles were
# landing on the board with null comp.
#
# LinkedIn's public, unauthenticated GUEST endpoint
#     /jobs-guest/jobs/api/jobPosting/<id>
# serves the posting fragment with the employer's own pay range inside
#     <div class="salary compensation__salary"> $150,000.00/yr - $190,000.00/yr </div>
#
# We read ONLY that div. The full /jobs/view/<id> page ALSO carries the salaries
# of "similar jobs" in its sidebar -- scraping that page wholesale would attach
# another company's pay to this role, which is exactly the fabrication this
# board refuses to do.
# --------------------------------------------------------------------------- #
_LI_ID_RE = re.compile(
    r"linkedin\.com/jobs/view/(?:[^/?#]*-)?(\d+)(?:[/?#]|$)", re.I)
_LI_SALARY_RE = re.compile(
    r'<div[^>]*class="[^"]*compensation__salary[^"]*"[^>]*>(.*?)</div>',
    re.I | re.S)
_LI_DESC_RE = re.compile(
    r'<div[^>]*class="[^"]*description__text[^"]*"[^>]*>(.*?)</section>',
    re.I | re.S)
_LI_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def _html_to_text(html):
    """Tags -> text. Block tags become newlines so paragraphs survive."""
    t = re.sub(r"(?i)<br\s*/?>|</(?:p|div|li|h\d|ul|ol|section)>", "\n", html)
    t = re.sub(r"<[^>]+>", " ", t)
    for ent, ch in (("&amp;", "&"), ("&nbsp;", " "), ("&#160;", " "),
                    ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'),
                    ("&#39;", "'"), ("&apos;", "'"), ("&rsquo;", "'"),
                    ("&ldquo;", '"'), ("&rdquo;", '"'), ("&mdash;", "-"),
                    ("&ndash;", "-")):
        t = t.replace(ent, ch)
    t = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), t)
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", t).strip()


def fetch_linkedin(url):
    """Return (comp_text, description_text) for a LinkedIn job URL.

    comp_text is the VERBATIM contents of the posting's own pay-range div, or
    None when LinkedIn shows no pay range for this job. Raises on transport
    failure so the caller's try/except can skip it.
    """
    m = _LI_ID_RE.search(url or "")
    if not m:
        raise RuntimeError(f"not a LinkedIn job URL: {url}")
    _throttle()
    api = ("https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/"
           + m.group(1))
    req = urllib.request.Request(api, headers={
        "User-Agent": _LI_UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=45) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        html = raw.decode("utf-8", "replace")
    if len(html) < 500:
        raise RuntimeError(f"LinkedIn returned a stub for {api}")
    sm = _LI_SALARY_RE.search(html)
    comp_text = _html_to_text(sm.group(1)) if sm else None
    dm = _LI_DESC_RE.search(html)
    desc = _html_to_text(dm.group(1)) if dm else None
    return comp_text, desc


# --------------------------------------------------------------------------- #
# Summary + benefits extraction (same honesty rule as comp: excerpt / detect
# only what the posting literally says -- never paraphrase, never infer)
# --------------------------------------------------------------------------- #
_SUMMARY_SKIP = (
    "cookie", "javascript", "sign in", "log in", "apply for", "apply now",
    "apply today", "back to", "share this", "powered by", "copyright",
    "all rights reserved", "toggle navigation", "equal opportunity",
    "privacy policy", "terms of", "subscribe", "return to", "upload your",
    # nav walls / site banners seen in the wild
    "skip to content", "temp-to-hire", "payroll services",
    "recruitment process", "ask job seekers",
    # PDF ligature damage ("Execu ve", "quali ed") -> text is corrupted
    "execu ve", "quali ed", "bene ts", "con den",
)

def _clip_sentence(s, limit=300):
    """Clip to <= limit chars, preferring a sentence boundary."""
    if len(s) <= limit:
        return s
    cut = s[:limit]
    dot = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if dot >= int(limit * 0.45):
        return cut[:dot + 1]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > 0 else cut).rstrip(",;:. ") + "..."

def extract_summary(md, title=""):
    """First substantive descriptive paragraph of a job detail page.

    Verbatim excerpt (clipped at a sentence boundary), never generated.
    Returns None when nothing suitable is found.
    """
    if not md:
        return None
    # A document with dropped fi/ti ligatures ("Execu ve", "por olio") is
    # corrupted throughout -- no excerpt from it is publishable.
    lig = re.findall(r"execu ve|quali |speci c|bene ts|of ce|mee ngs"
                     r"|por olio|con den| nanc", md, re.I)
    if len(lig) >= 2:
        return None
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", md)       # drop images
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # links -> their text
    tlow = _clean(title or "").lower()
    paras = re.split(r"\n\s*\n", text)
    cleaned = [_clean(unescape_md(re.sub(r"[#>*_`]+", " ", p))).lower()
               for p in paras]
    # ATS pages bury the JD under site chrome and compensation boilerplate.
    # Start after the job title, then prefer an explicit role-description
    # heading ("The Role", "Overview", "What You'll Do") when one exists.
    # This keeps an Ashby compensation-policy paragraph from becoming the card
    # summary when the actual role description appears a few sections later.
    order = list(range(len(paras)))
    title_anchor = None
    if tlow:
        for i, c in enumerate(cleaned):
            if tlow in c and len(c) < len(tlow) + 40:
                title_anchor = i
    role_heading = re.compile(
        r"(?:the role|about the role|your role|role overview|position overview"
        r"|the opportunity|job description|overview|what you(?:'|’)ll do"
        r"|what you will do)")
    role_anchor = None
    for i in range((title_anchor + 1) if title_anchor is not None else 0,
                   len(cleaned)):
        if role_heading.fullmatch(cleaned[i]):
            role_anchor = i
            break
    if role_anchor is not None:
        before = (title_anchor + 1) if title_anchor is not None else 0
        order = (list(range(role_anchor + 1, len(paras)))
                 + list(range(before, role_anchor + 1))
                 + list(range(0, before)))
    elif title_anchor is not None:
        order = (list(range(title_anchor + 1, len(paras)))
                 + list(range(0, title_anchor + 1)))
    for idx in order:
        para = paras[idx]
        if para.lstrip().startswith(("-", "•", "|")):
            continue
        line = _clean(unescape_md(re.sub(r"[#>*_`]+", " ", para)))
        if not line or len(line) < 90:
            continue
        low = line.lower()
        # A paragraph that is just the job title restated adds nothing.
        if tlow and (low.startswith(tlow[:60]) or tlow.startswith(low[:60])) \
                and len(line) < len(tlow) + 80:
            continue
        if any(b in low for b in _SUMMARY_SKIP):
            continue
        letters = sum(c.isalpha() for c in line)
        if letters < len(line) * 0.6:  # tables / nav walls, not prose
            continue
        if "." not in line and "," not in line:  # keyword list, not a sentence
            continue
        head = [c for c in line[:24] if c.isalpha()]
        if head and sum(c.isupper() for c in head) > len(head) * 0.7:
            continue  # SHOUTING section header, not prose
        words = [w for w in re.findall(r"[A-Za-z][\w'-]*", line) if len(w) > 2]
        if words and sum(w[0].isupper() for w in words) > len(words) * 0.6:
            continue  # Title Case Nav Menu / category list, not prose
        return _clip_sentence(line)
    # Fallback: some postings are written entirely as labeled bullet sections
    # with no prose paragraph (e.g. Insearch's POSITION / ATTRACTIVE FACTORS
    # format). Excerpt the first substantive bullets verbatim, joined with
    # semicolons -- still the posting's own words, never paraphrased.
    items = []
    for idx in order:
        for raw in paras[idx].splitlines():
            raw = raw.strip()
            if not raw.startswith(("-", "•")):
                continue
            line = _clean(unescape_md(
                re.sub(r"[#>*_`]+", " ", raw.lstrip("-• \t"))))
            if len(line) < 40:  # nav item / fragment, not a JD bullet
                continue
            low = line.lower()
            if any(b in low for b in _SUMMARY_SKIP):
                continue
            letters = sum(c.isalpha() for c in line)
            if letters < len(line) * 0.6:
                continue
            words = [w for w in re.findall(r"[A-Za-z][\w'-]*", line)
                     if len(w) > 2]
            if words and sum(w[0].isupper() for w in words) > len(words) * 0.6:
                continue
            items.append(line)
            if sum(len(i) for i in items) >= 120:
                return _clip_sentence("; ".join(items))
    if items:
        return _clip_sentence("; ".join(items))
    return None


# "equity" in a DEI statement is not a compensation benefit.
_DEI_RE = re.compile(
    r"diversity[,\s]+equity[,\s]+(?:and\s+)?inclusion|equity\s+and\s+inclusion"
    r"|racial\s+equity|pay\s+equity|equity[,\s]+diversity", re.I)

_BENEFIT_PATTERNS = [
    ("Bonus", r"(?:performance|annual|discretionary|quarterly|year[- ]end|"
              r"retention|sign[- ]?(?:ing|on))[\s-]*bonus"
              r"|bonus\s+(?:eligib|potential|structure|opportunit|target|plan)"
              r"|\+\s*(?:a\s+)?(?:\w+\s+)?bonus|plus\s+bonus|with\s+bonus"
              r"|bonus\s*\(|and\s+bonus\b"),
    ("Equity", r"\bequity\b|\bstock\s+options?\b|\brsus?\b"),
    ("401(k)", r"401\s*\(?\s*k\s*\)?"),
    ("Health coverage", r"(?:medical|health)\s*[,/&]?\s*(?:dental|vision|"
                        r"insurance|benefits|coverage)"
                        r"|dental\s*(?:,|and|&)\s*vision|healthcare\s+coverage"
                        r"|fully\s+(?:paid|covered)\s+(?:medical|health)"),
    ("Paid time off", r"paid\s+time\s+off|\bpto\b|paid\s+vacation"
                      r"|vacation\s+(?:days|time|policy)|unlimited\s+vacation"),
    ("Parental leave", r"parental\s+leave|maternity|paternity|family\s+leave"),
    ("Wellness", r"wellness\s+(?:allowance|stipend|benefit|program|"
                 r"reimbursement)|gym\s+(?:membership|stipend)"
                 r"|fitness\s+(?:stipend|reimbursement)"),
    ("Meals", r"daily\s+meals|meals\s+provided|catered\s+(?:lunch|meals)"
              r"|free\s+(?:lunch|meals)"),
    ("Profit sharing", r"profit[\s-]shar"),
    ("Overtime pay", r"paid\s+overtime|overtime\s+(?:pay|eligible|compensation)"),
]

def extract_benefits(text):
    """Benefit tags detected verbatim in the posting text. Nothing inferred."""
    if not text:
        return []
    t = _DEI_RE.sub(" ", text)
    return [tag for tag, pat in _BENEFIT_PATTERNS if re.search(pat, t, re.I)]


# --------------------------------------------------------------------------- #
# Date helpers
# --------------------------------------------------------------------------- #
def rel_date(text, base_iso):
    """Convert 'N days/weeks/months ago' (relative to base date) to ISO."""
    try:
        base = date.fromisoformat(base_iso)
    except ValueError:
        return None
    low = text.lower()
    if "yesterday" in low:
        return (base - timedelta(days=1)).isoformat()
    if "today" in low or "just now" in low:
        return base.isoformat()
    m = re.search(r"(\d+)\s+(day|week|month|year)s?\s+ago", low)
    if not m:
        return None
    n = int(m.group(1))
    mult = {"day": 1, "week": 7, "month": 30, "year": 365}[m.group(2)]
    return (base - timedelta(days=n * mult)).isoformat()


def parse_longdate(s):
    """'May 31, 2026' or '29th June, 2026' -> ISO."""
    s = s.strip()
    s = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", s)  # drop ordinal suffix
    for fmt in ("%B %d, %Y", "%d %B, %Y", "%b %d, %Y", "%d %b, %Y"):
        try:
            from datetime import datetime
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_dotdate(s):
    """'29.6.26' (DD.M.YY) -> ISO."""
    m = re.match(r"\s*(\d{1,2})\.(\d{1,2})\.(\d{2,4})\s*$", s)
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Small text utils
# --------------------------------------------------------------------------- #
def unescape_md(s):
    return re.sub(r"\\([\\`*_{}\[\]()#+\-.!|>#])", r"\1", s).strip()

def slugish(url):
    tail = url.rstrip("/").split("/")[-1]
    tail = re.sub(r"[?#].*$", "", tail)
    return re.sub(r"[^a-zA-Z0-9]+", "-", tail).strip("-").lower()[:60]

def _clean(s):
    """Normalize non-breaking spaces / stray whitespace in a display string."""
    if not s:
        return s
    return re.sub(r"\s+", " ", s.replace(" ", " ").replace("﻿", "")).strip()

def build_role(rid, title, source, apply_url, location="", remote="Onsite",
               category=None, org_type="", comp=(None, None),
               seniority=None, date_posted=None):
    title = _clean(title)
    # The taxonomy verdict for this title. Parsers pass `category` (from their
    # own classify() call, which already had the description context), but the
    # ACTION and CORE flags come from the title and are needed by scope_gate().
    verdict = classify_role(title)
    if category is None:
        category = verdict["category"] if verdict else None
    role = {
        "id": rid,
        "title": title,
        "org_type": _clean(org_type) or "",
        "category": category,
        "seniority": seniority if seniority is not None else seniority_of(title),
        "comp_low": comp[0],
        "comp_high": comp[1],
        "location": _clean(location),
        "remote": remote,
    }
    if date_posted:
        role["date_posted"] = date_posted
    role["apply_url"] = apply_url
    role["source"] = source
    if verdict:
        # Private keys: consumed by scope_gate(), stripped before roles.json.
        role["_conditional"] = verdict["action"] == CON
        role["_core"] = verdict["core"]
    return role


# Private, in-flight keys. Never written to roles.json.
_PRIVATE_KEYS = ("_detail_md", "_no_detail", "_conditional", "_core",
                 "_signals", "_excl", "_scoped", "_why", "_expired")


def strip_private(role):
    for k in _PRIVATE_KEYS:
        role.pop(k, None)
    return role


# --------------------------------------------------------------------------- #
# SOURCE PARSERS
# Each returns a list[dict]; raises on hard failure (caught in main()).
# --------------------------------------------------------------------------- #
def parse_bloom(run_date):
    """Bloom Talent -- recruiterflow. Listing has title/location/url; comp lives
    on the detail page, so we fetch details for included roles only."""
    md = scrape("https://recruiterflow.com/bloomtalent/jobs", wait=4000)
    roles = []
    # Each card: [Apply](.../jobs/NN)[**Title**](.../jobs/NN) \n Location \n Full time \n [Hybrid|Remote]
    blocks = re.split(r"\n\* \* \*\n", md)
    seen_ids = set()
    for blk in blocks:
        m = re.search(r"\*\*(.+?)\*\*\]\((https://recruiterflow\.com/bloomtalent/jobs/(\d+))\)",
                      blk)
        if not m:
            continue
        title = unescape_md(m.group(1))
        url = m.group(2)
        jid = m.group(3)
        if jid in seen_ids:
            continue
        cat = classify(title)
        if not cat:
            continue
        seen_ids.add(jid)
        # Location + remote from the lines after the title link.
        after = blk.split(m.group(0), 1)[-1]
        lines = [ln.strip() for ln in after.splitlines() if ln.strip()]
        location = ""
        remote = "Onsite"
        for ln in lines:
            if ln.lower() in ("full time", "part time", "contract"):
                continue
            if ln.lower() in ("hybrid", "remote"):
                remote = ln.capitalize()
                continue
            if not location and not ln.lower().startswith("apply"):
                location = ln
        if location.lower().startswith("remote"):
            remote = "Remote"
        # Detail page for comp (honest -- comp is only published there).
        comp = (None, None)
        det = None
        try:
            det = scrape(url, wait=3000)
            comp = extract_comp(det)
        except Exception:
            pass
        r = build_role(f"bloom-{jid}", title, "Bloom Talent", url,
                       location=location, remote=remote,
                       category=cat, comp=comp,
                       seniority="Senior" if cat != "Chief of Staff" else "Lead")
        if det:
            r["_detail_md"] = det
        roles.append(r)
    return roles


def parse_career_group(run_date):
    """Career Group -- careergroupcompanies.com/find-work. Comp published inline
    (salary or hourly). Hourly figures are stored with comp_period='hr'."""
    md = scrape("https://www.careergroupcompanies.com/find-work", wait=4000)
    roles = []
    # Cards are markdown links: [NEW\ ... **Title** ... DD.M.YY](.../job-posting/ID)
    pat = re.compile(
        r"\[(?:NEW\\?\s*)?(.*?)\]\((https://www\.careergroupcompanies\.com/job-posting/(\d+))\)",
        re.S,
    )
    for m in pat.finditer(md):
        inner = m.group(1)
        url = m.group(2)
        pid = m.group(3)
        tm = re.search(r"\*\*(.+?)\*\*", inner, re.S)
        if not tm:
            continue
        title = unescape_md(re.sub(r"\s+", " ", tm.group(1)))
        cat = classify(title, context=inner.replace("\\", " "))
        if not cat:
            continue
        body = unescape_md(inner).replace("\\", " ")
        # location: first "City, ST" after the title.
        loc = ""
        lm = re.search(r"\b([A-Z][A-Za-z .'-]+,\s*[A-Z]{2})\b", body)
        if lm:
            loc = lm.group(1).strip()
        # remote: "Remote  No/Yes"
        remote = "Onsite"
        rm = re.search(r"Remote\s+(Yes|No)", body, re.I)
        if rm and rm.group(1).lower() == "yes":
            remote = "Remote"
        # Comp. A Career Group card has a dedicated salary slot and its ONLY
        # money figures are that slot (verified across the whole board
        # 2026-07-13), so field=True: the slot IS the label. The card often
        # prints just the LOW end ("$100,000") where the detail page publishes
        # the full range ("Base Salary: $100,000 - $125,000") -- enrich() widens
        # it from the detail page later. Hourly-paid roles keep their $/hr.
        card = inner.replace("\\", " ")
        comp = extract_comp(card, field=True)
        period = None
        if comp[0] is None:
            hlo, hhi = extract_comp_hourly(card, field=True)
            if hlo is not None:
                comp, period = (hlo, hhi), "hr"
        # date: trailing DD.M.YY just before the url
        dm = re.search(r"(\d{1,2}\.\d{1,2}\.\d{2,4})\s*$", inner.strip())
        dp = parse_dotdate(dm.group(1)) if dm else None
        r = build_role(f"cgc-{pid}", title, "Career Group", url,
                       location=loc, remote=remote, category=cat,
                       comp=comp, date_posted=dp)
        if period:
            r["comp_period"] = period
        roles.append(r)
    return roles


def parse_burke(run_date):
    """Burke & Co -- Loxo. Listing lacks comp; fetch detail for included roles."""
    md = scrape("https://app.loxo.co/burke-co-1", wait=4500)
    roles = []
    # [Title - Org - City (Remote)](https://app.loxo.co/job/TOKEN)\n\nN ... ago\n...
    pat = re.compile(r"\[([^\]]+)\]\((https://app\.loxo\.co/job/([A-Za-z0-9]+))\)")
    matches = list(pat.finditer(md))
    for i, m in enumerate(matches):
        raw = unescape_md(m.group(1))
        url = m.group(2)
        token = m.group(3)
        seg = md[m.end(): matches[i + 1].start() if i + 1 < len(matches) else len(md)]
        # Title embeds " - Org - City (Onsite)". Split it apart: role / org / city.
        remote = "Onsite"
        title_nr = raw
        rmt = re.search(r"\((Onsite|Hybrid|Remote)\)\s*$", raw, re.I)
        if rmt:
            remote = rmt.group(1).capitalize()
            title_nr = raw[:rmt.start()].strip()
        parts = [p.strip() for p in re.split(r"\s+-\s+", title_nr) if p.strip()]
        title = parts[0] if parts else title_nr
        org = parts[1] if len(parts) >= 3 else ""
        cat = classify(raw, context=seg)  # classify on full raw (has more signal)
        if not cat:
            continue
        # Full location from the block ("City, State, United States"); fall back
        # to the city fragment in the title.
        loc = ""
        lm = re.search(r"([A-Z][A-Za-z .'-]+,\s*[A-Za-z .'-]+,\s*United States)", seg)
        if lm:
            loc = re.sub(r",\s*United States$", "", lm.group(1)).strip()
        elif len(parts) >= 2:
            loc = parts[-1]
        dp = None
        dm = re.search(r"(\d+\s+(?:day|week|month|year)s?\s+ago|yesterday|today)", seg, re.I)
        if dm:
            dp = rel_date(dm.group(1), run_date)
        comp = (None, None)
        det = None
        try:
            det = scrape(url, wait=3500)
            comp = extract_comp(det)
        except Exception:
            pass
        r = build_role(f"burke-{token[-10:]}", title, "Burke & Co", url,
                       location=loc, remote=remote, category=cat,
                       org_type=org, comp=comp, date_posted=dp)
        if det:
            r["_detail_md"] = det
        roles.append(r)
    return roles


def parse_aux(run_date):
    """Aux Talent -- /jobs. '### Title / ##### Location / [View/Apply](url)'.
    Comp inconsistent on detail pages -> fetch, parse where present."""
    md = scrape("https://auxtalent.com/jobs", wait=3500)
    roles = []
    pat = re.compile(
        r"###\s+(.+?)\n+#####\s+(.+?)\n+\[View / Apply\]\((https://auxtalent\.com/jobs/[^)]+)\)",
        re.S,
    )
    for m in pat.finditer(md):
        title = unescape_md(m.group(1))
        loc = unescape_md(m.group(2))
        url = m.group(3)
        cat = classify(title)
        if not cat:
            continue
        remote = "Remote" if loc.strip().lower() == "remote" else "Onsite"
        comp = (None, None)
        det = None
        try:
            det = scrape(url, wait=3000)
            comp = extract_comp(det)
        except Exception:
            pass
        r = build_role(f"aux-{slugish(url)}", title, "Aux Talent", url,
                       location=loc, remote=remote, category=cat, comp=comp)
        if det:
            r["_detail_md"] = det
        roles.append(r)
    return roles


def parse_tack(run_date):
    """Tack Advisors -- Bullhorn OSCP portal renders full detail inline
    (title, location, date, COMPENSATION)."""
    # The plugin's anchors sometimes emit a doubled hash route
    # ("#/jobs/jobs/159", seen 2026-07-08) which renders the BOARD, not the
    # job. Accept both forms but always store the canonical "#/jobs/<id>"
    # URL -- that one opens the specific posting.
    hdr = re.compile(
        r"######\s+\[(.+?)\]\(https://www\.tackadvisors\.co/wp-content/plugins/"
        r"bullhorn-oscp/\\?#/jobs/(?:jobs/)?(\d+)\)",
        re.S,
    )
    # The Bullhorn widget is a JS SPA that intermittently misses the render
    # window on /career-portal (a nav-only page parses as 0 jobs, seen
    # 2026-07-08). Retry with longer waits, then fall back to the plugin's
    # own URL, before accepting an empty board.
    roles = []
    matches = []
    for url_, wait_ in (
            ("https://www.tackadvisors.co/career-portal", 4500),
            ("https://www.tackadvisors.co/career-portal", 8000),
            ("https://www.tackadvisors.co/wp-content/plugins/bullhorn-oscp/#/jobs",
             8000)):
        md = scrape(url_, wait=wait_)
        matches = list(hdr.finditer(md))
        if matches:
            break
    for i, m in enumerate(matches):
        title = unescape_md(m.group(1))
        jnum = m.group(2)
        url = ("https://www.tackadvisors.co/wp-content/plugins/"
               f"bullhorn-oscp/#/jobs/{jnum}")
        seg = md[m.end(): matches[i + 1].start() if i + 1 < len(matches) else len(md)]
        cat = classify(title)
        if not cat:
            continue
        lines = [ln.strip() for ln in seg.splitlines() if ln.strip()]
        loc = lines[0] if lines else ""
        # date like "May 31, 2026"
        dp = None
        dm = re.search(r"([A-Z][a-z]+\s+\d{1,2},\s+\d{4})", seg)
        if dm:
            dp = parse_longdate(dm.group(1))
        remote = "Onsite"
        if re.search(r"\bhybrid\b", seg, re.I):
            remote = "Hybrid"
        elif re.search(r"\bfully remote\b|\bremote\b", seg, re.I) and "onsite" not in seg.lower():
            remote = "Remote"
        comp = extract_comp(seg)
        roles.append(build_role(f"tack-{jnum}", title, "Tack Advisors", url,
                                location=loc, remote=remote, category=cat,
                                comp=comp, date_posted=dp))
    return roles


def parse_csuite(run_date):
    """C-Suite Assistants -- Top Echelon portal. '[Title](url)\nLocation\n
    ...\n$X - $Y / yr\ndescription'."""
    base = ("https://careers.topechelon.com/portals/"
            "4384ddd4-53cf-4f9f-be2f-180d5e77ccf9/jobs")
    md = scrape(base, wait=4500)
    roles = []
    pat = re.compile(
        r"\[([^\]]+)\]\((https://careers\.topechelon\.com/portals/[^/]+/jobs/"
        r"([0-9a-f-]{8,}))\)",
        re.S,
    )
    matches = list(pat.finditer(md))
    for i, m in enumerate(matches):
        title = unescape_md(m.group(1))
        url = m.group(2)
        uid = m.group(3)
        seg = md[m.end(): matches[i + 1].start() if i + 1 < len(matches) else len(md)]
        cat = classify(title, context=seg)
        if not cat:
            continue
        lines = [ln.strip() for ln in seg.splitlines() if ln.strip()]
        loc = lines[0] if lines else ""
        loc = re.sub(r"\s*Featured\s*$", "", loc).strip()
        remote = "Onsite"
        if re.search(r"full remote|remote available", seg, re.I):
            remote = "Remote"
        elif re.search(r"hybrid", seg, re.I):
            remote = "Hybrid"
        elif re.search(r"on-?site", seg, re.I):
            remote = "Onsite"
        comp = extract_comp(seg)
        roles.append(build_role(f"csuite-{uid[:8]}", title, "C-Suite Assistants",
                                url, location=loc, remote=remote, category=cat,
                                comp=comp))
    return roles


def parse_insearch(run_date):
    """Groupe Insearch -- /current-jobs. Comp never published -> always null.
    Stop before the 'Recent Placements' section (those have no apply link)."""
    md = scrape("https://insearchsf.com/current-jobs", wait=3500)
    md = re.split(r"##\s+\*?\*?Recent Placements", md)[0]
    roles = []
    pat = re.compile(
        r"####\s+\[(.+?)\]\((https://insearchsf\.com/jobs/[^)]+)\)(.*?)"
        r"(?=####\s+\[|$)",
        re.S,
    )
    for m in pat.finditer(md):
        title = unescape_md(m.group(1))
        url = m.group(2)
        seg = m.group(3)
        cat = classify(title, context=seg)
        if not cat:
            continue
        lines = [ln.strip() for ln in seg.splitlines() if ln.strip()
                 and not ln.strip().lower().startswith("[apply")
                 and ln.strip().lower() not in ("full time", "part time")]
        org = lines[0] if lines else ""
        loc = ""
        for ln in lines[1:]:
            if ln.lower().startswith("posted"):
                continue
            loc = ln
            break
        dp = None
        pm = re.search(r"posted\s+(.+?ago)", seg, re.I)
        if pm:
            dp = rel_date(pm.group(1), run_date)
        remote = "Remote" if loc.strip().lower() == "remote" else "Onsite"
        roles.append(build_role(f"insearch-{slugish(url)}", title,
                                "Groupe Insearch", url, location=loc,
                                remote=remote, category=cat, org_type=org,
                                comp=(None, None), date_posted=dp))
    return roles


def parse_hire(run_date):
    """The Hire Standard -- JobAdder board. '## [Title](url "View Job")' with a
    date header and a description blurb that sometimes states salary."""
    md = scrape("https://clientapps.jobadder.com/58431/the-hire-standard", wait=5000)
    roles = []
    pat = re.compile(
        r"##\s+\[(.+?)\]\((https://clientapps\.jobadder\.com/58431/the-hire-standard/"
        r"(\d+)/[^)]*?)\s*(?:\"View Job\")?\)(.*?)(?=##\s+\[|\n2026 \|)",
        re.S,
    )
    for m in pat.finditer(md):
        title = unescape_md(m.group(1))
        url = m.group(2).strip()
        jid = m.group(3)
        seg = m.group(4)
        cat = classify(title, context=seg)
        if not cat:
            continue
        # date header: "### 29th June, 2026"
        dp = None
        dm = re.search(r"###\s+([0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,\s+\d{4})", seg)
        if dm:
            dp = parse_longdate(dm.group(1))
        # location: a bullet like "- Napa, CA"
        loc = ""
        for ln in seg.splitlines():
            ln = ln.strip().lstrip("-").strip()
            if re.match(r"^[A-Z][A-Za-z .'-]+,\s*[A-Z]{2}$", ln):
                loc = ln
                break
        remote = "Remote" if loc.strip().lower().startswith("remote") else "Onsite"
        comp = extract_comp(seg)
        roles.append(build_role(f"hire-{jid}", title, "The Hire Standard", url,
                                location=loc, remote=remote, category=cat,
                                comp=comp, date_posted=dp))
    return roles


def parse_capeople(run_date):
    """CA People Search -- /current-openings. Loose text wall, no per-job URLs;
    apply_url falls back to the openings page. Comp published inline as
    '**Salary:** $Xk - $Yk'."""
    page = "https://capeoplesearch.com/current-openings"
    md = scrape(page, wait=3500)
    roles = []
    # Split into blocks by a title-ish line, then look for Position/Location/Salary.
    # Focus on blocks that mention Executive Assistant / Chief of Staff.
    for m in re.finditer(
            r"\*\*Position:\*\*\s*(.+?)\n.*?\*\*Location:\*\*\s*(.+?)\n"
            r"(?:.*?\*\*Salary:\*\*\s*(.+?)\n)?",
            md, re.S):
        title = unescape_md(re.sub(r"\s+", " ", m.group(1)))
        loc = unescape_md(re.sub(r"\s+", " ", m.group(2)))
        sal = m.group(3) or ""
        cat = classify(title)
        if not cat:
            continue
        remote = "Onsite"
        if re.search(r"hybrid|days onsite|days in", loc, re.I):
            remote = "Hybrid"
        elif re.search(r"remote", loc, re.I):
            remote = "Remote"
        loc_clean = re.sub(r"\s*\(.*?\)\s*", "", loc).strip()
        # `sal` is the posting's own "**Salary:**" line -- an isolated comp
        # field, so field=True.
        comp = extract_comp(sal, field=True)
        period = None
        if comp[0] is None:
            hlo, hhi = extract_comp_hourly(sal, field=True)
            if hlo is not None:
                comp, period = (hlo, hhi), "hr"
        rid = "capeople-" + re.sub(r"[^a-z0-9]+", "-",
                                   title.lower()).strip("-")[:40]
        r = build_role(rid, title, "CA People Search", page,
                       location=loc_clean, remote=remote,
                       category=cat, comp=comp)
        if period:
            r["comp_period"] = period
        # apply_url is a shared openings page: the first paragraph there
        # belongs to a DIFFERENT job, so never enrich from it.
        r["_no_detail"] = True
        roles.append(r)
    return roles


def parse_truex(run_date):
    """Truex Metier -- truexmetier.com/jobs embeds a LinkedIn jobs widget.

    The widget renders title, location, work mode and posted date. It USED to
    render comp too ("$150K/yr - $180K/yr"); as of 2026-07-13 it prints zero
    "$" characters, which is why all four Truex roles were reaching the board
    with null comp. Comp (and the JD) are still published on LinkedIn itself,
    so enrich() rescues them through fetch_linkedin() -- firecrawl refuses
    linkedin.com, but LinkedIn's public guest endpoint answers a plain GET."""
    md = scrape("https://www.truexmetier.com/jobs", wait=5000)
    roles = []
    pat = re.compile(
        r"\[([^\]]+)\]\((https://www\.linkedin\.com/jobs/view/(\d+)/?)\)")
    matches = [m for m in pat.finditer(md)
               if m.group(1).strip().lower() != "apply now"
               and "sk-job-picture" not in m.group(1)]
    seen = set()
    for i, m in enumerate(matches):
        title = unescape_md(m.group(1))
        url = m.group(2)
        jid = m.group(3)
        if jid in seen:
            continue
        seen.add(jid)
        seg = md[m.end(): matches[i + 1].start() if i + 1 < len(matches)
                 else m.end() + 600]
        cat = classify(title, context=seg)
        if not cat:
            continue
        lines = [ln.strip() for ln in seg.splitlines()
                 if ln.strip() and not ln.strip().startswith(("[", "!"))]
        loc = lines[0] if lines else ""
        remote = "Onsite"
        if re.search(r"\bhybrid\b", seg, re.I):
            remote = "Hybrid"
        elif re.search(r"\bremote\b", seg, re.I):
            remote = "Remote"
        comp = extract_comp(seg.replace("/yr", " "))
        dp = None
        dm = re.search(r"(\d+\s+(?:day|week|month)s?\s+ago|yesterday|today)",
                       seg, re.I)
        if dm:
            dp = rel_date(dm.group(1), run_date)
        r = build_role(f"truex-{jid}", title, "Truex Metier", url,
                       location=loc, remote=remote, category=cat, comp=comp,
                       date_posted=dp)
        # NOT _no_detail any more: the widget stopped printing comp, but
        # LinkedIn's public guest endpoint still publishes the employer's own
        # pay range. enrich() fetches it via fetch_linkedin().
        benefits = extract_benefits(seg)  # board prints e.g. "+ Bonus"
        if benefits:
            r["benefits"] = benefits
        roles.append(r)
    return roles


# =========================================================================== #
# PRIORITY-1 SOURCES  (added 2026-07-14, "New Sources" sheet)
#
# The board was 92% Executive Assistant because every source it had was an
# executive-support recruiting agency. These are the sources where Chief of
# Staff and Executive Operations roles actually live.
# =========================================================================== #

# Roles outside the US: the board is a US board, every existing role is US, and
# a EUR/GBP figure cannot be compared to a $100k floor. Salary currency already
# filters most of it; this catches the ones posted in USD from abroad.
_NON_US = re.compile(
    r"\b(?:united kingdom|england|scotland|ireland|london|dublin|germany|berlin"
    r"|munich|france|paris|spain|madrid|barcelona|portugal|lisbon|netherlands"
    r"|amsterdam|belgium|switzerland|zurich|sweden|stockholm|denmark|copenhagen"
    r"|norway|oslo|finland|helsinki|poland|warsaw|lithuania|kaunas|vilnius"
    r"|estonia|latvia|czech|prague|austria|vienna|italy|rome|milan|greece"
    r"|romania|bulgaria|hungary|budapest|ukraine|israel|tel aviv|india|bangalore"
    r"|bengaluru|mumbai|delhi|hyderabad|pune|singapore|japan|tokyo|china|beijing"
    r"|shanghai|hong kong|korea|seoul|australia|sydney|melbourne|new zealand"
    r"|canada|toronto|vancouver|montreal|ottawa|mexico|brazil|sao paulo"
    r"|argentina|colombia|chile|uae|dubai|abu dhabi|saudi|qatar|nigeria|kenya"
    r"|south africa|egypt|turkey|istanbul|philippines|manila|vietnam|indonesia"
    r"|jakarta|thailand|bangkok|malaysia|taiwan|pakistan|bangladesh|europe|emea"
    r"|apac|latam)\b",
    re.I)

_US_HINT = re.compile(
    r",\s*(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI"
    r"|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA"
    r"|WA|WV|WI|WY|DC)\b|\b(?:united states|usa|u\.s\.a?\.?|remote)\b"
    r"|,\s*(?:alabama|alaska|arizona|arkansas|california|colorado|connecticut"
    r"|delaware|florida|georgia|hawaii|idaho|illinois|indiana|iowa|kansas"
    r"|kentucky|louisiana|maine|maryland|massachusetts|michigan|minnesota"
    r"|mississippi|missouri|montana|nebraska|nevada|new hampshire|new jersey"
    r"|new mexico|new york|north carolina|north dakota|ohio|oklahoma|oregon"
    r"|pennsylvania|rhode island|south carolina|south dakota|tennessee|texas"
    r"|utah|vermont|virginia|washington|west virginia|wisconsin|wyoming"
    r"|district of columbia)\b",
    re.I)


def is_us_location(loc):
    """US-only board. A blank location is allowed (many postings omit it)."""
    if not loc or not loc.strip():
        return True
    # A location such as "India - Remote, India" contains the word "Remote".
    # Country evidence must win over that generic work-mode hint.
    if _NON_US.search(loc):
        return False
    if _US_HINT.search(loc):
        return True
    return True


def _iso_from_epoch(ts):
    try:
        return date.fromtimestamp(int(ts)).isoformat()
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# CONSIDER  (jobs.a16z.com, jobs.sequoiacap.com, jobs.bvp.com, jobs.lsvp.com)
#
# One parser, four boards -- the leverage the sheet was pointing at. Consider
# renders client-side and answers its own board's XHR:
#
#   POST /api-boards/search-jobs
#   headers: x-csrf-token (read from window.serverInitialData on /jobs)
#   body:    {"meta":{"size":100},"board":{...},"query":{"titlePrefix":"..."}}
#
# `titlePrefix` is really a phrase-contains match on the title ("executive
# assistant" returns "Founding Executive Assistant"), so a compact seed list
# covers the taxonomy without pulling the whole 15,000-job board.
#
# COMP HONESTY, and this one matters:
#   salary.isOriginal == True   -> the EMPLOYER published this range. Usable.
#   salary.isOriginal == False  -> CONSIDER ESTIMATED IT. The employer published
#                                  nothing.
# Verified 2026-07-13: HappyRobot's "Chief of Staff" carries salary
# 135000-210000 isOriginal=False, and its actual Ashby posting prints no dollar
# figure at all. Publishing that would be exactly the fabrication rule 2 forbids.
# We read isOriginal=True only, and a False row is treated as NO COMP.
# --------------------------------------------------------------------------- #
CONSIDER_BOARDS = [
    ("a16z", "https://jobs.a16z.com"),
    ("Sequoia", "https://jobs.sequoiacap.com"),
    ("Bessemer", "https://jobs.bvp.com"),
    ("Lightspeed", "https://jobs.lsvp.com"),
]

# Seeds are phrases, not the full 130-title taxonomy: one query per phrase, and
# each phrase's own result set is then run through classify_role() anyway. Kept
# specific enough that no seed overflows the 100-row page (a bare "operations"
# returns 816 rows on a16z alone and would need paging for no benefit).
TITLE_SEEDS = [
    "chief of staff",
    "executive assistant",
    "executive business partner",
    "administrative business partner",
    "office of the ceo",
    "founder's office",
    "business operations",
    "strategy and operations",
    "strategic operations",
    "corporate operations",
    "executive operations",
    "company operations",
    "strategic initiatives",
    "special projects",
    "head of operations",
    "director of operations",
    "vp of operations",
    "chief operating officer",
    "chief administrative officer",
    "operating partner",
    "portfolio operations",
    "value creation",
    "business manager",
    "executive coordinator",
]

_CSRF_RE = re.compile(r'"csrfToken":"([^"]+)"')
_BOARD_RE = re.compile(r'"board":\{"id":"([^"]+)","isParent":(true|false)\}')


def _consider_session(base):
    """Read the board id + CSRF token the board's own JS uses."""
    html = http_get(base + "/jobs")
    if is_soft_404(html):
        raise RuntimeError(f"{base}/jobs returned a not-found body")
    m = _CSRF_RE.search(html)
    b = _BOARD_RE.search(html)
    if not m or not b:
        raise RuntimeError(f"could not read the Consider board config at {base}")
    return {"id": b.group(1), "isParent": b.group(2) == "true"}, m.group(1)


def _consider_salary(job):
    """(comp, period) from a Consider salary block -- EMPLOYER-PUBLISHED ONLY."""
    s = job.get("salary") or {}
    if not s.get("isOriginal"):
        return (None, None), None      # Consider's own estimate. Not published.
    if (s.get("currency") or {}).get("value") != "USD":
        return (None, None), None
    lo, hi = s.get("minValue"), s.get("maxValue")
    if lo is None and hi is None:
        return (None, None), None
    lo = lo if lo is not None else hi
    hi = hi if hi is not None else lo
    period = (s.get("period") or {}).get("value")
    if period == "year":
        if not (_sane(int(lo)) and _sane(int(hi))):
            return (None, None), None
        return (int(lo), int(hi)), None
    if period == "hour":
        if not (_sane_hr(lo) and _sane_hr(hi)):
            return (None, None), None
        return (lo, hi), "hr"
    return (None, None), None          # monthly / weekly / unknown -> not usable


def make_consider_parser(label, base):
    def parse(run_date):
        board, csrf = _consider_session(base)
        api = base + "/api-boards/search-jobs"
        headers = {"x-csrf-token": csrf, "Referer": base + "/jobs",
                   "Accept": "application/json"}
        roles, seen = [], set()
        for seed in TITLE_SEEDS:
            try:
                res = http_json(api, data={
                    "meta": {"size": 100},
                    "board": board,
                    "query": {"titlePrefix": seed},
                }, headers=headers)
            except Exception as e:
                print(f"[warn] Consider/{label}: seed {seed!r} failed -- {e}",
                      file=sys.stderr)
                continue
            jobs = res.get("jobs") or []
            if (res.get("total") or 0) > len(jobs):
                print(f"[warn] Consider/{label}: seed {seed!r} has "
                      f"{res['total']} hits, page holds {len(jobs)}")
            for j in jobs:
                jid = j.get("jobId") or j.get("url")
                if not jid or jid in seen:
                    continue
                seen.add(jid)
                title = j.get("title") or ""
                loc = (j.get("locations") or [""])[0] or ""
                if not is_us_location(loc):
                    continue
                cat = classify(title)
                if not cat:
                    continue
                comp, period = _consider_salary(j)
                remote = "Onsite"
                if j.get("remote"):
                    remote = "Remote"
                elif j.get("hybrid"):
                    remote = "Hybrid"
                dp = None
                ts = j.get("timeStamp") or ""
                if re.match(r"\d{4}-\d{2}-\d{2}", ts):
                    dp = ts[:10]
                url = j.get("applyUrl") or j.get("url")
                if not url:
                    continue
                r = build_role(
                    f"consider-{label.lower()}-{slugish(str(jid))[:24]}",
                    title, f"{label} Portfolio", url,
                    location=loc, remote=remote, category=cat,
                    org_type=j.get("companyName") or "",
                    comp=comp, date_posted=dp)
                if period:
                    r["comp_period"] = period
                roles.append(r)
        return roles
    return parse


# --------------------------------------------------------------------------- #
# GETRO  (jobs.generalcatalyst.com, jobs.accel.com, jobs.insightpartners.com)
#
# One parser, three boards. Public search API, no auth:
#   POST https://api.getro.com/api/v2/collections/<id>/search/jobs
#   body {"hitsPerPage":100,"page":0,"filters":{"q":"..."},"query":"..."}
#
# Collection ids read off each board's own XHR (stable): GC 222, Accel 8672,
# Insight 246.
#
# COMP: compensation_amount_{min,max}_cents -- in CENTS. USD + year|hour only.
# null amounts = the employer published nothing (compensation_public is `true`
# even on rows with no figure, so it is NOT a usable signal -- ignore it).
# --------------------------------------------------------------------------- #
GETRO_BOARDS = [
    ("General Catalyst", 222, "https://jobs.generalcatalyst.com"),
    ("Accel", 8672, "https://jobs.accel.com"),
    ("Insight Partners", 246, "https://jobs.insightpartners.com"),
]


def _getro_salary(job):
    """(comp, period) from a Getro row. Cents -> dollars. USD only."""
    if (job.get("compensation_currency") or "").upper() != "USD":
        return (None, None), None
    lo_c = job.get("compensation_amount_min_cents")
    hi_c = job.get("compensation_amount_max_cents")
    if lo_c is None and hi_c is None:
        return (None, None), None
    lo_c = lo_c if lo_c is not None else hi_c
    hi_c = hi_c if hi_c is not None else lo_c
    lo, hi = lo_c / 100.0, hi_c / 100.0
    period = job.get("compensation_period")
    if period == "year":
        if not (_sane(int(lo)) and _sane(int(hi))):
            return (None, None), None
        return (int(lo), int(hi)), None
    if period == "hour":
        if not (_sane_hr(lo) and _sane_hr(hi)):
            return (None, None), None
        return (round(lo, 2), round(hi, 2)), "hr"
    return (None, None), None          # month / period_not_defined -> unusable


def make_getro_parser(label, cid, origin):
    def parse(run_date):
        api = f"https://api.getro.com/api/v2/collections/{cid}/search/jobs"
        headers = {"Origin": origin, "Referer": origin + "/",
                   "Accept": "application/json"}
        roles, seen = [], set()
        for seed in TITLE_SEEDS:
            try:
                res = http_json(api, data={
                    "hitsPerPage": 100, "page": 0,
                    "filters": {"q": seed}, "query": seed,
                }, headers=headers)
            except Exception as e:
                print(f"[warn] Getro/{label}: seed {seed!r} failed -- {e}",
                      file=sys.stderr)
                continue
            for j in (res.get("results") or {}).get("jobs") or []:
                jid = j.get("id")
                if jid is None or jid in seen:
                    continue
                seen.add(jid)
                title = j.get("title") or ""
                # Getro's `q` is a full-text search, so a seed matches jobs whose
                # DESCRIPTION mentions the phrase. The title still has to earn
                # its place in the taxonomy.
                cat = classify(title)
                if not cat:
                    continue
                loc = (j.get("locations") or [""])[0] or ""
                if not is_us_location(loc):
                    continue
                comp, period = _getro_salary(j)
                wm = j.get("work_mode") or ""
                remote = {"remote": "Remote", "hybrid": "Hybrid"}.get(
                    wm, "Onsite")
                url = j.get("url")
                if not url:
                    continue
                org = (j.get("organization") or {}).get("name") or ""
                r = build_role(f"getro-{cid}-{jid}", title,
                               f"{label} Portfolio", url,
                               location=loc, remote=remote, category=cat,
                               org_type=org, comp=comp,
                               date_posted=_iso_from_epoch(j.get("created_at")))
                if period:
                    r["comp_period"] = period
                roles.append(r)
        return roles
    return parse


# --------------------------------------------------------------------------- #
# CHIEF OF STAFF NETWORK  (chiefofstaff.network/jobs)
#
# The single best source for real Chief of Staff roles. Webflow CMS, fully
# server-rendered, 4 pages (?4b2fa278_page=N). Everything we need is on the
# CARD -- company, title, workplace, location, posted date, and the salary where
# the employer published one. For roles that clear the pay floor, we fetch one
# tightly scoped description block from the detail page.
#
# The DETAIL pages are a trap and we do not read comp from them: each one
# carries a "related jobs" aside (`aside_job-info`) printing OTHER companies'
# salaries. The SignalCore posting publishes no salary of its own, yet its page
# renders "$256k - $320k" (Handshake) and "$90k - $160k" (Tact). A card with no
# salary means no published salary, and the role is dropped.
# --------------------------------------------------------------------------- #
_COSN_CARD = re.compile(
    r'<a href="(/jobs/[^"]+)" class="card is-jobs[^"]*"(.*?)</a>', re.S)
_COSN_FIELD = re.compile(
    r'fs-list-field="(company|title|location|type|workplace)"[^>]*>([^<]*)<')
# The salary slot is the card's only BARE <div> whose text starts with "$"
# (every other meta item is an fs-list-field div). When the employer published
# no salary, Webflow renders the slot `w-condition-invisible` with an empty
# `w-dyn-bind-empty` child and there is no such div at all.
_COSN_SALARY = re.compile(r'<div>(\$[^<]{1,40})</div>')
_COSN_DATE = re.compile(r'job-date="(\d{4}-\d{2}-\d{2})"')
_COSN_DESC = re.compile(
    r'<div class="blog-rte w-richtext">(.*?)</div>'
    r'<div class="spacer-medium"></div><div class="button-group max-full"',
    re.S)


def _cosn_description(html):
    """Return only the posting's own JD, never its recommended-jobs rail."""
    m = _COSN_DESC.search(html or "")
    return _html_to_text(m.group(1)) if m else ""


def parse_cos_network(run_date):
    base = "https://www.chiefofstaff.network"
    roles, seen = [], set()
    for page in range(1, 7):                 # 4 pages today; stop when empty
        url = f"{base}/jobs" if page == 1 else f"{base}/jobs?4b2fa278_page={page}"
        html = http_get(url)
        if is_soft_404(html):
            break
        cards = list(_COSN_CARD.finditer(html))
        if not cards:
            break
        for m in cards:
            href, body = m.group(1), m.group(2)
            if href in seen:
                continue
            seen.add(href)
            f = dict(_COSN_FIELD.findall(body))
            title = unescape_md(_clean(f.get("title", "")))
            if not title:
                continue
            cat = classify(title)
            if not cat:
                continue
            loc = _clean(f.get("location", ""))
            if not is_us_location(loc):
                continue
            workplace = (f.get("workplace") or "").strip().lower()
            remote = ("Remote" if "remote" in workplace
                      else "Hybrid" if "hybrid" in workplace else "Onsite")
            # The salary slot. Webflow renders it `w-condition-invisible` with a
            # `w-dyn-bind-empty` child when the employer published nothing.
            comp = (None, None)
            period = None
            sm = _COSN_SALARY.search(body)
            if sm:
                comp = extract_comp(sm.group(1), field=True)
                if comp[0] is None:
                    hlo, hhi = extract_comp_hourly(sm.group(1), field=True)
                    if hlo is not None:
                        comp, period = (hlo, hhi), "hr"
            dm = _COSN_DATE.search(body)
            r = build_role(f"cosn-{slugish(href)}", title,
                           "Chief of Staff Network", base + href,
                           location=loc, remote=remote, category=cat,
                           org_type=_clean(f.get("company", "")), comp=comp,
                           date_posted=dm.group(1) if dm else None)
            if period:
                r["comp_period"] = period
            # Salary remains card-only. For qualifying roles, extract the JD
            # from the posting's bounded rich-text block; never parse the rest
            # of the page, whose recommended-jobs rail has unrelated salaries.
            if (comp_midpoint(r) or 0) >= PAY_FLOOR:
                try:
                    det = _cosn_description(http_get(base + href))
                    if det:
                        r["_detail_md"] = det
                except Exception as exc:
                    print(f"[warn] Chief of Staff Network detail failed -- {exc}",
                          file=sys.stderr)
            r["_no_detail"] = True
            roles.append(r)
    return roles


# --------------------------------------------------------------------------- #
# POCKETBOOK AGENCY
#
# The URL in the sheet (pocketbookagency.com/jobs/) is stale: the board moved to
# careers.pocketbookagency.com (Next.js, server-rendered). Two streams:
#   ?rtype=Corporate  <- the only one we read
#   ?rtype=Domestic   <- private household / estate staffing. Out of scope by
#                        policy, so we never even fetch it.
# Detail page /job/<id> carries the title, city, posted date and the JD, which
# is where comp lives ("Compensation & Benefits: Up to $170K DOE").
# --------------------------------------------------------------------------- #
def parse_pocketbook(run_date):
    base = "https://careers.pocketbookagency.com"
    listing = http_get(base + "/?rtype=Corporate")
    if is_soft_404(listing):
        raise RuntimeError("Pocketbook corporate board returned a not-found body")
    ids = sorted(set(re.findall(r'/job/(\d+)', listing)))
    roles = []
    for jid in ids:
        url = f"{base}/job/{jid}"
        try:
            html = http_get(url)
        except Exception as e:
            print(f"[warn] Pocketbook: job {jid} failed -- {e}", file=sys.stderr)
            continue
        if is_soft_404(html):
            continue
        body = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
        body = re.sub(r"<style.*?</style>", " ", body, flags=re.S)
        text = _html_to_text(body)
        m = re.search(r"^\s*(.+?)\s*/\s*in\s+(.+?)\s*$", text.split("\n")[0]) \
            or re.search(r"^\s*(.+?)\s+in\s+(.+?)\s*$", text.split("\n")[0])
        title = _clean(m.group(1)) if m else ""
        loc = _clean(m.group(2)) if m else ""
        if not title:
            continue
        cat = classify(title, context=text)
        if not cat:
            continue
        dp = None
        dm = re.search(r"POSTED ON\s+([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})", text)
        if dm:
            dp = parse_longdate(dm.group(1))
        remote = "Onsite"
        if re.search(r"\bhybrid\b", text, re.I):
            remote = "Hybrid"
        elif re.search(r"\bfully remote\b|\bremote\b", text, re.I):
            remote = "Remote"
        comp = extract_comp(text)
        period = None
        if comp[0] is None:
            hlo, hhi = extract_comp_hourly(text)
            if hlo is not None:
                comp, period = (hlo, hhi), "hr"
        r = build_role(f"pocketbook-{jid}", title, "Pocketbook Agency", url,
                       location=loc, remote=remote, category=cat, comp=comp,
                       date_posted=dp)
        if period:
            r["comp_period"] = period
        r["_detail_md"] = text
        roles.append(r)
    return roles


# --------------------------------------------------------------------------- #
# BEACON HILL  (jobs.beaconhillstaffing.com -> bhsg.com/jobs, WordPress)
#
# WP REST, post type `job_listing`, rest_base `job-listings`. One search request
# per taxonomy seed; the row carries everything:
#   meta._job_location, meta._filled, meta._remote_position
#   content.rendered = the JD (this job's only -- no related-jobs sidebar),
#                      which is where salary is printed.
# --------------------------------------------------------------------------- #
def parse_beacon_hill(run_date):
    api = "https://bhsg.com/jobs/wp-json/wp/v2/job-listings"
    roles, seen = [], set()
    for seed in TITLE_SEEDS:
        q = urllib.parse.quote(seed)
        try:
            rows = http_json(f"{api}?search={q}&per_page=50&_embed=0")
        except Exception as e:
            print(f"[warn] Beacon Hill: seed {seed!r} failed -- {e}",
                  file=sys.stderr)
            continue
        if not isinstance(rows, list):
            continue
        for it in rows:
            jid = it.get("id")
            if jid in seen:
                continue
            seen.add(jid)
            meta = it.get("meta") or {}
            if meta.get("_filled"):
                continue
            title = _clean(unescape_md(_html_to_text(
                (it.get("title") or {}).get("rendered", ""))))
            det = _html_to_text((it.get("content") or {}).get("rendered", ""))
            cat = classify(title, context=det)
            if not cat:
                continue
            loc = _clean(meta.get("_job_location") or "")
            if not is_us_location(loc):
                continue
            remote = "Remote" if meta.get("_remote_position") else "Onsite"
            if re.search(r"\bhybrid\b", det[:1500], re.I):
                remote = "Hybrid"
            comp = extract_comp(det)
            period = None
            if comp[0] is None:
                hlo, hhi = extract_comp_hourly(det)
                if hlo is not None:
                    comp, period = (hlo, hhi), "hr"
            dp = (it.get("date") or "")[:10] or None
            r = build_role(f"beacon-{jid}", title, "Beacon Hill",
                           it.get("link") or "",
                           location=loc, remote=remote, category=cat,
                           org_type=_clean(meta.get("_company_name") or ""),
                           comp=comp, date_posted=dp)
            if period:
                r["comp_period"] = period
            r["_detail_md"] = det
            roles.append(r)
    return roles


# --------------------------------------------------------------------------- #
# LASALLE NETWORK  (thelasallenetwork.com, WordPress, post type `ce_job`)
#
# robots.txt disallows `/job-search/*?` and `/*?ce_job=*` -- the query-string
# search pages. We do not touch those. The WP REST collection (`/wp-json/`) is
# not disallowed, and it is a better feed anyway: 196 jobs in two requests.
#
# THE TRAP: content.rendered carries a related-jobs block, so the raw content of
# an Executive Assistant paying $25-$30/hr also contains "$125,000 - $145,000"
# from some other posting. Extracting comp from that body would attach another
# job's pay to this one -- the exact fabrication this board refuses to do.
# LaSalle embeds a JSON-LD JobPosting inside content.rendered whose
# `description` is THIS job's description and nothing else. That is what we read.
# (It needs json.loads(strict=False): the blob carries raw control characters.)
# --------------------------------------------------------------------------- #
_LASALLE_LD = re.compile(
    r'type="application/ld\+json"[^>]*>(.*?)</script>', re.S)


def _lasalle_posting(content_html):
    """The job's own JSON-LD JobPosting, or None."""
    m = _LASALLE_LD.search(content_html or "")
    if not m:
        return None
    try:
        o = json.loads(html_unescape(m.group(1)), strict=False)
    except Exception:
        return None
    if isinstance(o, dict) and o.get("@type") == "JobPosting":
        return o
    return None


def parse_lasalle(run_date):
    api = "https://www.thelasallenetwork.com/wp-json/wp/v2/ce_job"
    roles = []
    for page in (1, 2, 3):
        try:
            rows = http_json(f"{api}?per_page=100&page={page}")
        except Exception:
            break                      # past the last page WP returns a 400
        if not isinstance(rows, list) or not rows:
            break
        for it in rows:
            title = _clean(unescape_md(_html_to_text(
                (it.get("title") or {}).get("rendered", ""))))
            content = (it.get("content") or {}).get("rendered", "")
            post = _lasalle_posting(content)
            det = _html_to_text((post or {}).get("description") or "")
            cat = classify(title, context=det)
            if not cat:
                continue
            addr = ((post or {}).get("jobLocation") or {}).get("address") or {}
            loc = ", ".join(x for x in (addr.get("addressLocality"),
                                        addr.get("addressRegion")) if x)
            if not is_us_location(loc):
                continue
            remote = "Onsite"
            if re.search(r"\bhybrid\b", det[:1200], re.I):
                remote = "Hybrid"
            elif re.search(r"\bfully remote\b|\bremote\b", det[:1200], re.I):
                remote = "Remote"
            # Comp is read from the JD ONLY -- never from content.rendered.
            comp = extract_comp(det)
            period = None
            if comp[0] is None:
                hlo, hhi = extract_comp_hourly(det)
                if hlo is not None:
                    comp, period = (hlo, hhi), "hr"
            r = build_role(f"lasalle-{it.get('id')}", title, "LaSalle Network",
                           it.get("link") or "",
                           location=loc, remote=remote, category=cat,
                           comp=comp, date_posted=(it.get("date") or "")[:10])
            if period:
                r["comp_period"] = period
            r["_detail_md"] = det
            # apply_url is the live posting; the JD is already in hand, so the
            # enrichment pass must not spend a fetch re-reading it (and must not
            # re-parse the page, whose sidebar carries other jobs' salaries).
            r["_no_detail"] = True
            r["summary"] = extract_summary(det, title=title)
            r["benefits"] = extract_benefits(det)
            roles.append(r)
    return roles


SOURCES = [
    ("Bloom Talent", parse_bloom),
    ("Career Group", parse_career_group),
    ("Burke & Co", parse_burke),
    ("Aux Talent", parse_aux),
    ("Tack Advisors", parse_tack),
    ("C-Suite Assistants", parse_csuite),
    ("Groupe Insearch", parse_insearch),
    ("The Hire Standard", parse_hire),
    ("CA People Search", parse_capeople),
    ("Truex Metier", parse_truex),
    # ---- priority-1 additions, 2026-07-14 ----
    ("Chief of Staff Network", parse_cos_network),
    ("Pocketbook Agency", parse_pocketbook),
    ("Beacon Hill", parse_beacon_hill),
    ("LaSalle Network", parse_lasalle),
] + [
    (f"{label} Portfolio", make_consider_parser(label, base))
    for label, base in CONSIDER_BOARDS
] + [
    (f"{label} Portfolio", make_getro_parser(label, cid, origin))
    for label, cid, origin in GETRO_BOARDS
]


# --------------------------------------------------------------------------- #
# Dedupe + merge + write
# --------------------------------------------------------------------------- #
def dedupe_url(url):
    """The identity of an apply link, for dedupe only.

    The QUERY STRING is dropped. The VC portfolio boards all point at the same
    employer ATS page but each stamps its own tracking parameter, so the very
    same Databricks Chief of Staff posting arrives as
        jobs.lever.co/databricks/<id>?lever-source[]=jobs.a16z.com
        jobs.lever.co/databricks/<id>?lever-source[]=jobs.lsvp.com
    and would land on the board twice. Every source in this file identifies a
    job by PATH (or, for Tack, by fragment), never by query, so dropping the
    query is safe. The fragment is kept: Tack's Bullhorn portal routes on
    "#/jobs/<id>".
    """
    u = (url or "").strip().lower().rstrip("/")
    if not u:
        return ""
    frag = ""
    if "#" in u:
        u, frag = u.split("#", 1)
        frag = "#" + frag
    u = u.split("?", 1)[0]
    return u.rstrip("/") + frag


def _identity_text(value):
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _identity_location(value):
    """Normalize city-level location differences across portfolio boards."""
    loc = _identity_text((value or "").split(",", 1)[0])
    loc = re.sub(r"\b(?:remote|hybrid|onsite)\b", " ", loc)
    loc = re.sub(r"\s+", " ", loc).strip(" -")
    return {"new york city": "new york", "sf": "san francisco"}.get(loc, loc)


def _identity_company(role):
    org = _identity_text(role.get("org_type"))
    source = _identity_text(role.get("source"))
    if not org:
        return ""
    # Recruiter-owned boards sometimes expose the staffing firm's own name as
    # _company_name; that is not the confidential client company and cannot
    # safely identify two generic "Executive Assistant" searches as one job.
    if source and source in org and ("staff" in org or "talent" in org):
        return ""
    return org


def _identity_key(role):
    company = _identity_company(role)
    title = _identity_text(role.get("title"))
    location = _identity_location(role.get("location"))
    if not (company and title and location):
        return None
    return company, title, location


def _role_quality(role):
    """Prefer the direct-employer and then the most complete duplicate row."""
    host = urllib.parse.urlsplit(role.get("apply_url") or "").netloc.lower()
    direct = int("chiefofstaff.network" not in host)
    return (direct,
            int(bool(role.get("date_posted"))),
            int(bool(role.get("summary"))),
            len(role.get("benefits") or []),
            len(role.get("location") or ""))


def _keep_best(roles, key_fn):
    out, positions = [], {}
    for role in roles:
        key = key_fn(role)
        if not key:
            out.append(role)
            continue
        if key not in positions:
            positions[key] = len(out)
            out.append(role)
            continue
        pos = positions[key]
        if _role_quality(role) > _role_quality(out[pos]):
            out[pos] = role
    return out


def dedupe(roles):
    """Collapse exact apply links, then normalized company/title/city matches."""
    by_url = _keep_best(roles, lambda r: dedupe_url(r.get("apply_url")))
    return _keep_best(by_url, _identity_key)


# --------------------------------------------------------------------------- #
# SCOPE GATE -- the "Filtering Rules" sheet, applied to the description.
#
# "A matching title is not enough for broad operations roles. Validate the
#  actual scope." Runs AFTER enrich(), which is when the description exists.
#
#   * CONDITIONAL titles (Operations Lead, General Manager, Administrative
#     Director, Special Assistant to the CEO, ...) need >= 2 of the 7 inclusion
#     signals. No description -> no validation -> not published. We do not guess
#     at scope any more than we guess at pay.
#   * BROAD titles (Executive Operations / Director-VP of Operations / COO) are
#     dropped when the description shows an excluded functional or industry
#     scope (>= 2 hits). LaSalle's "Director of Operations" -- a $160k-$175k
#     manufacturing plant role -- dies here.
#   * CORE Executive Assistant / Chief of Staff titles are never scope-scanned.
# --------------------------------------------------------------------------- #
def needs_scope_check(role):
    """True when this role's title alone is not enough to publish it."""
    return (not role.get("_core", True)) or role.get("_conditional", False)


def scope_verdict(role, text):
    """Record the scope verdict for a role from its description text.

    Stored on the role (and cached) rather than recomputed at gate time, so a
    role that passed on Monday cannot silently fail on Tuesday just because the
    run reused the cache instead of re-fetching the description.
    """
    role["_signals"] = count_signals(text)
    role["_excl"] = excluded_by_description(text)
    role["_scoped"] = True
    return role


def scope_gate(roles):
    """Return (kept, dropped). Dropped roles carry a `_why`."""
    kept, dropped = [], []
    for r in roles:
        if not needs_scope_check(r):
            kept.append(r)
            continue
        if not r.get("_scoped"):
            # No description was ever obtained, so the scope could not be
            # validated. The sheet's rule is description-first; an unvalidated
            # broad title is not published.
            r["_why"] = "scope never validated (no description available)"
            dropped.append(r)
            print(f"[scope ] drop {r['id']:<28} {r['title'][:38]:<38} "
                  f"-- no description, scope unvalidated")
            continue
        if not r.get("_core", True) and r.get("_excl"):
            r["_why"] = "excluded scope: " + r["_excl"]
            dropped.append(r)
            print(f"[scope ] drop {r['id']:<28} {r['title'][:38]:<38} "
                  f"-- {r['_excl']} role, not executive operations")
            continue
        if r.get("_conditional"):
            n = r.get("_signals") or 0
            if n < 2:
                r["_why"] = f"conditional title, {n}/2 inclusion signals"
                dropped.append(r)
                print(f"[cond  ] drop {r['id']:<28} {r['title'][:38]:<38} "
                      f"-- ambiguous title, {n}/2 inclusion signals")
                continue
        kept.append(r)
    return kept, dropped


def prefilter_floor(roles):
    """Drop roles that ALREADY publish a comp that cannot clear the floor.

    Purely a runtime optimization for the 7am run: the new VC portfolio boards
    hand us the salary in the search response, so hundreds of roles are known to
    fail the floor before a single detail page is fetched. Enriching them would
    be a wasted fetch each.

    It is only ever safe for comp that can no longer CHANGE in enrich():
      * a two-ended published range -- _widen() explicitly refuses to touch one,
      * an hourly rate -- _widen() skips comp_period="hr".
    A SINGLE published figure is left alone, because _widen() can still upgrade
    it to the source's fuller range (Career Group prints "$100,000" on the card
    where the posting says "$100,000 - $125,000"), which can only ever RAISE the
    midpoint. Dropping those here would re-introduce the exact silent-loss bug
    the no-regression check exists to catch.
    """
    kept, dropped = [], []
    for r in roles:
        lo, hi = r.get("comp_low"), r.get("comp_high")
        settled = lo is not None and (r.get("comp_period") == "hr" or lo != hi)
        if settled and (comp_midpoint(r) or 0) < PAY_FLOOR:
            dropped.append(r)
            continue
        kept.append(r)
    return kept, dropped


def load_existing_note():
    try:
        with open(ROLES_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        note = data.get("_note")
        # Preserve the stored note, but upgrade one written before the
        # summary/benefits/comp_period fields or the $100k PAY FLOOR existed, so
        # the schema and the board promise stay documented inside the data.
        if (note and "summary" in note and "comp_period" in note
                and "PAY FLOOR" in note):
            return note
    except Exception:
        pass
    return DEFAULT_NOTE


def load_prev_by_url():
    """Previous run's roles keyed by apply_url, for enrichment carry-over."""
    try:
        with open(ROLES_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        out = {}
        for r in data.get("roles", []):
            url = (r.get("apply_url") or "").strip().lower().rstrip("/")
            if url:
                out[url] = r
        return out
    except Exception:
        return {}


# The employer ATSes the VC portfolio boards link out to. All of them serve the
# job description in the HTML (Ashby and Greenhouse embed it as JSON, Lever
# renders it), so a plain GET is enough -- and it is roughly 10x faster than
# driving firecrawl's browser. The VC boards add ~100 apply links to the run; at
# firecrawl speed that alone would blow the 7am window.
_PLAIN_ATS = re.compile(
    r"//(?:jobs\.ashbyhq\.com|(?:job-boards|boards)\.greenhouse\.io"
    r"|jobs\.lever\.co|apply\.workable\.com|jobs\.workable\.com"
    r"|[a-z0-9-]+\.pinpointhq\.com|jobs\.jobvite\.com|careers\.smartrecruiters\.com"
    r"|www\.comeet\.com|recruiting\.paylocity\.com)/", re.I)


def fetch_detail(url):
    """Fetch a job detail page as text.

    Plain HTTP for the employer ATSes the new VC boards link out to; firecrawl's
    browser for everything else (the ten original agency boards, several of which
    are JS-rendered SPAs). A plain fetch that comes back as a soft-404 or an empty
    shell falls through to firecrawl rather than yielding a wrong answer.
    """
    if _PLAIN_ATS.search(url or ""):
        try:
            html = http_get(url)
            if not is_soft_404(html):
                text = _html_to_text(
                    re.sub(r"<(script|style).*?</\1>", " ", html, flags=re.S | re.I))
                if len(text) > 400:
                    return text
        except Exception:
            pass
    return scrape(url, wait=3500)


def _looks_like_board(md, own_url):
    """True when a 'detail' page is actually a multi-job board listing.

    ATSes (Loxo at least) redirect an EXPIRED job link to the agency's full
    board; parsing that page would attach another job's summary/comp to this
    role. Real detail pages in this network carry 0 job links; the redirect
    board carries a dozen-plus.
    """
    own = own_url.rstrip("/").lower()
    links = {u.rstrip("/").lower()
             for u in re.findall(r"\]\((https?://[^)\s]+)\)", md)}
    return sum(1 for u in links
               if re.search(r"/jobs?/[^/]+$", u) and u != own) >= 4


# --------------------------------------------------------------------------- #
# Detail-page cache
#
# The $100k floor DROPS every role whose comp the source does not publish, so
# those roles vanish from roles.json and the roles.json carry-over can no longer
# remember that we already checked them. Without a cache the daily 7am run would
# re-fetch the same "comp is genuinely not published" pages (all six Groupe
# Insearch roles, both C-Suite ones) every single morning. This remembers the
# verdict. A NO-COMP verdict is re-checked after NO_COMP_TTL_DAYS, so a firm
# that starts publishing pay gets picked up.
# --------------------------------------------------------------------------- #
CACHE_PATH = os.path.join(HERE, "partials", "detail_cache.json")
NO_COMP_TTL_DAYS = 7      # re-check a "no comp published" page weekly
CACHE_PRUNE_DAYS = 45     # forget entries not seen in this long


def load_cache():
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_cache(cache, run_date):
    try:
        cutoff = (date.fromisoformat(run_date)
                  - timedelta(days=CACHE_PRUNE_DAYS)).isoformat()
        pruned = {u: v for u, v in cache.items()
                  if (v.get("checked") or "") >= cutoff}
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as fh:
            json.dump(pruned, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
    except Exception as e:
        print(f"[warn] could not write detail cache: {e}", file=sys.stderr)


def _cache_fresh(entry, run_date):
    """A cached NO-COMP verdict expires after NO_COMP_TTL_DAYS. A cached comp
    figure stays good while the role is live (the board is rebuilt daily)."""
    if not entry or not entry.get("checked"):
        return False
    if entry.get("comp_low") is not None:
        return True
    try:
        age = (date.fromisoformat(run_date)
               - date.fromisoformat(entry["checked"])).days
    except ValueError:
        return False
    return 0 <= age < NO_COMP_TTL_DAYS


def _widen(r, dlo, dhi):
    """Upgrade a SINGLE published figure to the fuller range the SOURCE
    publishes, when that range starts at the same figure.

    Career Group's board card prints only the low end ("$100,000") while the
    posting itself publishes "Base Salary: $100,000 - $125,000". Both numbers
    come from the source; the range is the fuller truth, so we take it. The
    guard (the range's low must EQUAL the figure we already have) keeps this
    from ever pulling in an unrelated number.

    This must run on the CARRY-OVER paths too, not just the fresh-fetch path.
    The listing parser re-derives $100,000-$100,000 from the card on EVERY run,
    so if only the fetch path widened, a cached run would silently NARROW the
    role back to $100k-$100k and the board would flap between two different
    published figures day to day.
    """
    if r.get("comp_period") == "hr" or r.get("comp_low") is None:
        return
    if r["comp_low"] != r.get("comp_high"):
        return                              # already a range; leave it alone
    if dlo is None or dhi is None or dlo == dhi:
        return
    if dlo == r["comp_low"] and _sane(dhi):
        r["comp_high"] = dhi


def _widen_from_detail(r, det):
    dlo, dhi = extract_comp(det)
    _widen(r, dlo, dhi)


def _cache_entry(r, run_date):
    """What we remember about a detail page: its comp, its text, and -- since the
    taxonomy release -- its SCOPE verdict, so a broad or conditional role that
    was validated once is not re-litigated (or silently dropped) on a cached run.
    """
    return {
        "checked": run_date,
        "comp_low": r.get("comp_low"),
        "comp_high": r.get("comp_high"),
        "comp_period": r.get("comp_period"),
        "summary": r.get("summary"),
        "benefits": r.get("benefits") or [],
        "signals": r.get("_signals"),
        "excl": r.get("_excl"),
    }


def _restore_scope(r, entry):
    """Re-apply a cached scope verdict to a role we did not re-fetch."""
    if entry and "signals" in entry:
        r["_signals"] = entry.get("signals") or 0
        r["_excl"] = entry.get("excl")
        r["_scoped"] = True


def enrich(roles, run_date):
    """Fill summary + benefits + comp from each role's detail page.

    Detail markdown already stashed by a parser is reused; otherwise the page is
    fetched once. Three layers keep the daily run cheap and polite:
      1. detail markdown handed over by the source parser (no extra fetch),
      2. the previous run's roles.json row (carry-over by apply_url),
      3. partials/detail_cache.json -- remembers pages whose source publishes NO
         comp, so floored-out roles are not re-fetched every morning (TTL 7d).
    REFRESH_FULL=1 bypasses 2 and 3 and re-fetches everything.

    LinkedIn-hosted roles (Truex Metier) go through fetch_linkedin() instead of
    firecrawl, which refuses linkedin.com.
    """
    full = os.environ.get("REFRESH_FULL") == "1"
    prev = load_prev_by_url()
    cache = {} if full else load_cache()
    # An apply_url shared by several roles is a board page, not a job detail
    # page (e.g. CA People Search) -- nothing role-specific to fetch there.
    url_counts = Counter((r.get("apply_url") or "").strip().lower().rstrip("/")
                         for r in roles)
    fetched = 0
    # ORDER MATTERS, because MAX_DETAIL_FETCHES is a hard cap. A role whose
    # summary we fail to fetch just loses its summary; a BROAD or CONDITIONAL
    # role whose description we fail to fetch is DROPPED (its scope can never be
    # validated). So the roles that need a description to survive go first, and
    # the merely-nice-to-have summaries take whatever budget is left.
    for r in sorted(roles, key=lambda x: 0 if needs_scope_check(x) else 1):
        det = r.pop("_detail_md", None)
        no_detail = r.pop("_no_detail", False)
        url = (r.get("apply_url") or "").strip().lower().rstrip("/")
        is_li = "linkedin.com/jobs/view/" in url
        p = None if full else prev.get(url)
        cached = p is not None and "benefits" in p
        ce = None if full else cache.get(url)
        ce_fresh = _cache_fresh(ce, run_date)
        if ce_fresh and ce.get("expired"):
            r["_expired"] = True
            r.setdefault("summary", None)
            r.setdefault("benefits", [])
            continue

        # Re-fetch even when cached if comp is still unknown, so extractor
        # improvements rescue previously missed salaries on later runs -- but
        # only once a cached no-comp verdict has aged out.
        comp_retry = (r.get("comp_low") is None
                      and (p is None or p.get("comp_low") is None)
                      and not ce_fresh)
        # Older cache entries may be structurally complete but still have no
        # description. Retry those once the fetch cache has aged out so parser
        # improvements can backfill summaries instead of preserving blanks.
        summary_retry = (r.get("summary") is None
                         and (p is None or not p.get("summary"))
                         and not ce_fresh)
        # A broad / conditional title CANNOT be published without a description
        # to validate its scope against. If neither the parser nor the cache has
        # one, spend the fetch: dropping the role because the fetcher was lazy
        # would be the same bug as dropping it because the comp extractor was.
        scope_retry = (needs_scope_check(r) and det is None
                       and not (ce and "signals" in ce))

        if (det is None and (not cached or comp_retry or scope_retry or summary_retry)
                and not no_detail
                and url and url_counts[url] == 1
                and fetched < MAX_DETAIL_FETCHES):
            if is_li:
                # LinkedIn: read ONLY the posting's own pay-range div and its
                # JD. Never the /jobs/view page (its sidebar carries OTHER
                # companies' salaries).
                try:
                    comp_text, desc = fetch_linkedin(r["apply_url"])
                    fetched += 1
                except Exception as e:
                    print(f"[li  ] {r['id']}: LinkedIn fetch failed -- {e}",
                          file=sys.stderr)
                    comp_text, desc = None, None
                if comp_text and r.get("comp_low") is None:
                    lo, hi = extract_comp(comp_text, field=True)
                    if lo is not None:
                        r["comp_low"], r["comp_high"] = lo, hi
                    else:
                        hlo, hhi = extract_comp_hourly(comp_text, field=True)
                        if hlo is not None:
                            r["comp_low"], r["comp_high"] = hlo, hhi
                            r["comp_period"] = "hr"
                if desc:
                    if r.get("summary") is None:
                        r["summary"] = extract_summary(
                            desc, title=r.get("title", ""))
                    if not r.get("benefits"):
                        r["benefits"] = extract_benefits(desc)
                    scope_verdict(r, desc)
                if url:
                    cache[url] = _cache_entry(r, run_date)
                r.setdefault("summary", None)
                r.setdefault("benefits", [])
                continue

            try:
                det = fetch_detail(r["apply_url"])
                fetched += 1
            except Exception:
                det = None
            if det and (is_soft_404(det)
                        or _looks_like_board(det, r["apply_url"])):
                # A dead posting can return a friendly 200 page or redirect to
                # the employer's full board. Neither is a live role, and neither
                # may donate text to this card.
                print(f"[exp ] {r['id']}: detail page is expired or redirects "
                      f"to the employer board")
                r["_expired"] = True
                if url:
                    cache[url] = {"checked": run_date, "expired": True}
                det = None

        if det:
            if r.get("comp_low") is None:
                r["comp_low"], r["comp_high"] = extract_comp(det)
                if r["comp_low"] is None:
                    hlo, hhi = extract_comp_hourly(det)
                    if hlo is not None:
                        r["comp_low"], r["comp_high"] = hlo, hhi
                        r["comp_period"] = "hr"
            else:
                _widen_from_detail(r, det)
            if r.get("summary") is None:
                r["summary"] = extract_summary(det, title=r.get("title", ""))
            if not r.get("benefits"):
                r["benefits"] = extract_benefits(det)
            scope_verdict(r, det)
            if url:
                cache[url] = _cache_entry(r, run_date)
        elif cached:
            # Fill, never clobber: a parser may have set these from the board.
            if r.get("summary") is None:
                r["summary"] = p.get("summary")
            if not r.get("benefits"):
                r["benefits"] = p.get("benefits") or []
            if r.get("comp_low") is None and p.get("comp_low") is not None:
                r["comp_low"] = p["comp_low"]
                r["comp_high"] = p["comp_high"]
                if p.get("comp_period"):
                    r["comp_period"] = p["comp_period"]
            _restore_scope(r, ce)
            if url and ce:
                # Keep a still-valid cache entry alive: it holds the SCOPE
                # verdict, and CACHE_PRUNE_DAYS would otherwise forget it and
                # silently drop a broad role that has been on the board for
                # weeks.
                cache[url] = dict(ce, checked=run_date)
        elif ce_fresh:
            if r.get("summary") is None:
                r["summary"] = ce.get("summary")
            if not r.get("benefits"):
                r["benefits"] = ce.get("benefits") or []
            if r.get("comp_low") is None and ce.get("comp_low") is not None:
                r["comp_low"] = ce["comp_low"]
                r["comp_high"] = ce["comp_high"]
                if ce.get("comp_period"):
                    r["comp_period"] = ce["comp_period"]
            _restore_scope(r, ce)
            if url:
                cache[url] = dict(ce, checked=run_date)
        else:
            r.setdefault("summary", None)
            r.setdefault("benefits", [])

        # WIDENING, applied on EVERY path (fetch, roles.json carry-over, cache).
        # The listing parser re-derives the card's single figure ("$100,000") on
        # every run, so if only the fetch path widened, the next cached run would
        # NARROW the role back to $100k-$100k and the published range would flap
        # day to day. detail_cache is the detail-page-derived record and is the
        # authority here; last run's roles.json row is the fallback.
        for src in (cache.get(url), p):
            if src and src.get("comp_period") != "hr":
                _widen(r, src.get("comp_low"), src.get("comp_high"))

    save_cache(cache, run_date)
    print(f"[enr ] enrichment: {fetched} detail pages fetched, "
          f"{sum(1 for r in roles if r.get('summary'))} summaries, "
          f"{sum(1 for r in roles if r.get('benefits'))} with benefits")


def load_manual():
    """Curated roles from sources that cannot be automated (LinkedIn feeds, per-role
    PDFs, low-volume firms). Merged into every run so they are not lost. Edit
    partials/manual.json by hand as these fill/expire."""
    path = os.path.join(HERE, "partials", "manual.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data.get("roles", data if isinstance(data, list) else [])
    except Exception:
        return []


# --------------------------------------------------------------------------- #
# THE $100k PAY FLOOR  (added 2026-07-13 -- the board's public promise)
#
# RULE 1  Floor test = MIDPOINT of the published range >= $100,000, where
#         midpoint = (comp_low + comp_high) / 2. A single published figure IS
#         the midpoint. $90k-$120k (mid $105k) stays; $75k-$105k (mid $90k) goes.
# RULE 2  No published comp -> the role is NOT published. There are no
#         "comp not listed" rows. But a role is only ever dropped for this
#         AFTER a genuine extraction attempt: the listing pass, the detail page,
#         and (for LinkedIn-hosted roles) LinkedIn's own guest endpoint.
# RULE 3  Hourly roles are annualized (rate x 2080) for the floor test ONLY.
#         The board keeps displaying the verbatim $/hr with comp_period="hr".
# RULE 4  Comp honesty outranks board size. Nothing is estimated, inferred or
#         interpolated to clear the floor. A smaller honest board is correct.
# --------------------------------------------------------------------------- #
def annualize(value, role):
    """A comp figure expressed in annual dollars, for the floor test only."""
    if value is None:
        return None
    if role.get("comp_period") == "hr":
        return int(round(value * HOURS_PER_YEAR))
    return int(value)


def comp_midpoint(role):
    """Annualized midpoint of a role's PUBLISHED comp, or None if none published."""
    lo = annualize(role.get("comp_low"), role)
    hi = annualize(role.get("comp_high"), role)
    if lo is None and hi is None:
        return None
    if lo is None:
        return float(hi)
    if hi is None:
        return float(lo)
    return (lo + hi) / 2.0


def apply_pay_floor(roles):
    """Return (kept, dropped_no_comp, dropped_below_floor)."""
    kept, no_comp, below = [], [], []
    for r in roles:
        mid = comp_midpoint(r)
        if mid is None:
            no_comp.append(r)
            print(f"[nocomp] drop {r['id']:<26} {r['source']:<20} "
                  f"{r['title'][:40]} -- source publishes no figure")
            continue
        if mid < PAY_FLOOR:
            below.append(r)
            unit = "/hr" if r.get("comp_period") == "hr" else ""
            print(f"[<100k ] drop {r['id']:<26} {r['source']:<20} "
                  f"${r['comp_low']}-${r['comp_high']}{unit} "
                  f"(midpoint ${mid:,.0f})")
            continue
        kept.append(r)
    return kept, no_comp, below


def assert_floor(roles):
    """Hard proof of the board promise. Raises if the board would ever lie."""
    bad_null = [r["id"] for r in roles if comp_midpoint(r) is None]
    bad_low = [(r["id"], comp_midpoint(r)) for r in roles
               if comp_midpoint(r) is not None and comp_midpoint(r) < PAY_FLOOR]
    if bad_null or bad_low:
        raise AssertionError(
            f"BOARD PROMISE VIOLATED -- null comp: {bad_null}; "
            f"below floor: {bad_low}")
    if not roles:
        print("\n[ASSERT] board is empty")
        return True
    mids = [comp_midpoint(r) for r in roles]
    print(f"\n[ASSERT] PASS: {len(roles)}/{len(roles)} roles have a published "
          f"comp figure and a midpoint >= ${PAY_FLOOR:,}. "
          f"0 null-comp, 0 below floor. "
          f"Lowest midpoint on the board = ${min(mids):,.0f}.")
    return True


def main():
    run_date = (sys.argv[1] if len(sys.argv) > 1 else
                os.environ.get("REFRESH_DATE") or date.today().isoformat())
    try:
        date.fromisoformat(run_date)
    except ValueError:
        print(f"Invalid date '{run_date}', expected YYYY-MM-DD", file=sys.stderr)
        return 2

    print(f"=== Exec Ops Brief refresh :: run date {run_date} ===\n")
    all_roles = []
    per_source = {}
    for name, fn in SOURCES:
        try:
            roles = fn(run_date)
            per_source[name] = ("ok", len(roles))
            all_roles.extend(roles)
            comp_n = sum(1 for r in roles if r["comp_low"] is not None)
            print(f"[ ok ] {name:<22} {len(roles):>3} roles "
                  f"({comp_n} with real comp)")
        except Exception as e:
            per_source[name] = ("FAIL", str(e))
            print(f"[FAIL] {name:<22} skipped -- {e}", file=sys.stderr)

    manual = load_manual()
    if manual:
        all_roles.extend(manual)
        print(f"[man ] {'manual.json (curated)':<22} {len(manual):>3} roles merged")

    merged = dedupe(all_roles)
    pre_floor = len(merged)

    # Cheap floor pass FIRST: the VC boards publish comp in the search response,
    # so hundreds of roles are already known to fail the floor and enriching them
    # would burn a detail fetch each. Only ever drops comp that enrich() cannot
    # change (see prefilter_floor).
    merged, dropped_early = prefilter_floor(merged)
    if dropped_early:
        print(f"[pre  ] {len(dropped_early)} roles publish a comp below the "
              f"floor; dropped before enrichment (no fetch spent)")

    enrich(merged, run_date)

    # A source aggregator can briefly retain a role after its employer removes
    # the direct posting. Confirmed dead/redirected destinations are not live.
    dropped_expired = [r for r in merged if r.get("_expired")]
    if dropped_expired:
        merged = [r for r in merged if not r.get("_expired")]
        print(f"[exp ] dropped {len(dropped_expired)} confirmed expired roles")

    # The taxonomy's description-first rules (conditional titles, excluded
    # functional/industry scope). Needs the description, so it runs after enrich.
    merged, dropped_scope = scope_gate(merged)

    merged, dropped_nocomp, dropped_floor = apply_pay_floor(merged)
    dropped_floor = dropped_early + dropped_floor
    total = len(merged)
    for r in merged:
        strip_private(r)

    print("\n--- Summary ---")
    for name, (status, info) in per_source.items():
        print(f"  {name:<24} {status:<5} {info}")
    print(f"\n  Roles found (deduped)         : {pre_floor}")
    print(f"  Dropped -- scope / conditional: {len(dropped_scope)}")
    print(f"  Dropped -- no published comp  : {len(dropped_nocomp)}")
    print(f"  Dropped -- midpoint < $100k   : {len(dropped_floor)}")
    print(f"  Dropped -- expired posting    : {len(dropped_expired)}")
    print(f"  BOARD (all >= $100k midpoint) : {total}")

    cats = Counter(r["category"] for r in merged)
    print("\n--- Category mix (the point of the taxonomy release) ---")
    for cat in VISIBLE_CATEGORIES:
        print(f"  {cat:<28} {cats.get(cat, 0):>3}")
    other = {c: n for c, n in cats.items() if c not in VISIBLE_CATEGORIES}
    for cat, n in sorted(other.items()):
        print(f"  {str(cat):<28} {n:>3}   (legacy category)")

    # The promise, asserted -- not assumed.
    assert_floor(merged)

    ok_sources = sum(1 for s, _ in per_source.values() if s == "ok")
    if total < MIN_SAFE_TOTAL:
        print(f"\n!! Only {total} roles (< {MIN_SAFE_TOTAL} safety floor). "
              f"REFUSING to overwrite roles.json to avoid wiping good data.",
              file=sys.stderr)
        return 1

    payload = {
        "_note": load_existing_note(),
        "updated": run_date,
        "count": total,
        "roles": merged,
    }
    with open(ROLES_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"\nWrote {total} roles from {ok_sources}/{len(SOURCES)} live sources "
          f"-> {ROLES_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
