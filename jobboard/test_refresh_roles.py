#!/usr/bin/env python3
"""
Unit tests for refresh_roles.py.

    python -m pytest test_refresh_roles.py -q
    python test_refresh_roles.py            # no pytest? runs standalone

Nothing here touches the network. Every fixture is a VERBATIM fragment of a real
posting that this scraper has met in the wild, so a regression in the extractor
shows up as a failing test rather than as a wrong salary on the live board.

Three things are being defended:

  1. COMP HONESTY. A figure is published or it is not. "100-200 employees" is not
     a salary; a gym stipend is not a salary; a $50-100M fund is not a salary;
     Consider's own estimate is not a salary. Every one of these has been live on
     someone's board at some point, which is why each has a test.
  2. THE $100k FLOOR ON THE MIDPOINT. Not on the bottom of the range. See the
     note in REFRESH_README.md: the midpoint rule is Adrienne's decision of
     2026-07-13 and it SUPERSEDES the strict-floor wording in the taxonomy xlsx.
  3. THE TAXONOMY. Chief of Staff must beat Executive Assistant when the title
     leads with it; functional ops (Sales/People/Clinical/Manufacturing) must
     stay off an executive-operations board; ambiguous titles must earn their
     place with >= 2 inclusion signals.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import refresh_roles as R  # noqa: E402


# =========================================================================== #
# 1. COMP EXTRACTION -- the formats
# =========================================================================== #
def test_comp_dollar_k_range():
    assert R.extract_comp("$120K-$140K") == (120000, 140000)


def test_comp_bloom_no_dollar_no_label():
    # Bloom Talent writes it exactly like this. The "k" governs BOTH ends and the
    # trailing "+ DOE" blocks any trailing-label match. Requiring a label here
    # once deleted all 8 Bloom salaries.
    assert R.extract_comp("150-180K+ DOE") == (150000, 180000)


def test_comp_long_form_per_year():
    assert R.extract_comp("120,000-140,000 per year") == (120000, 140000)


def test_comp_up_to():
    # Pocketbook: "Compensation & Benefits: Up to $170K DOE, full benefits..."
    assert R.extract_comp(
        "Compensation & Benefits: Up to $170K DOE, full benefits package"
    ) == (170000, 170000)


def test_comp_unit_on_both_ends():
    assert R.extract_comp("$130,000.00/yr - $150,000.00/yr") == (130000, 150000)


def test_comp_em_dash_range():
    assert R.extract_comp("$160,000 — $175,000") == (160000, 175000)


def test_comp_en_dash_range():
    assert R.extract_comp("$160,000 – $175,000") == (160000, 175000)


def test_comp_to_range():
    # LaSalle: "Compensation: $160,000 to $175,000 + eligibility to earn bonus"
    assert R.extract_comp(
        "Compensation: $160,000 to $175,000 + eligibility to earn bonus"
    ) == (160000, 175000)


def test_comp_tack_compensation_block_survives_per_week():
    # The disqualify lookback must not cross a newline: "4 days per week" is a
    # SCHEDULE on the line above, not a pay period.
    txt = ("San Francisco, CA (hybrid, 4 days per week)\n\n"
           "COMPENSATION\n$150K - $180K base")
    assert R.extract_comp(txt) == (150000, 180000)


def test_comp_hourly_verbatim():
    assert R.extract_comp_hourly("$44.50/hr to $50/hr") == (44.5, 50.0)


def test_comp_hourly_single():
    assert R.extract_comp_hourly("$60/hour") == (60.0, 60.0)


def test_hourly_is_not_returned_as_salary():
    assert R.extract_comp("$25-$35/hour depending on experience") == (None, None)


# =========================================================================== #
# 2. COMP EXTRACTION -- the traps (things that look like money and are not)
# =========================================================================== #
def test_trap_employee_count():
    # "100-200 employees" is not a $100k-$200k salary.
    assert R.extract_comp("A growth-stage company of 100-200 employees") \
        == (None, None)


def test_trap_fund_size():
    assert R.extract_comp("manages a $50-100M portfolio") == (None, None)


def test_trap_aum():
    assert R.extract_comp("a $250M AUM family office") == (None, None)


def test_trap_gym_stipend():
    # Groupe Insearch publishes NO salary, but does publish this. It must never
    # become someone's compensation.
    assert R.extract_comp("Gym reimbursement $750/yr") == (None, None)


def test_trap_commuter_benefit():
    assert R.extract_comp("Commuter benefits $475/mo") == (None, None)


def test_trap_base64_placeholder():
    # This one was LIVE: "<Base64-Image-Removed> base" became a $64,000 offer.
    assert R.extract_comp("<Base64-Image-Removed> base") == (None, None)


def test_trap_competitive_only():
    assert R.extract_comp(
        "Competitive compensation and bonus structure") == (None, None)


def test_trap_commensurate_only():
    assert R.extract_comp(
        "Salary commensurate with experience") == (None, None)


def test_trap_doe_alone():
    assert R.extract_comp("Compensation: DOE") == (None, None)


def test_trap_401k_is_not_a_salary():
    assert R.extract_comp("401(k) with company match") == (None, None)


def test_trap_lone_unanchored_figure():
    # A bare $150,000 in a JD could be a budget, a fund, a revenue target.
    assert R.extract_comp(
        "You will own a $150,000 marketing budget") == (None, None)


# =========================================================================== #
# 3. THE $100k FLOOR -- on the MIDPOINT
# =========================================================================== #
def _role(lo, hi, period=None):
    r = {"id": "t", "title": "t", "source": "t", "comp_low": lo, "comp_high": hi}
    if period:
        r["comp_period"] = period
    return r


def test_floor_is_the_midpoint_not_the_bottom():
    # $90k-$120k has a midpoint of $105k and STAYS. The taxonomy xlsx says the
    # bottom of the range must clear $100k, which would drop this; Adrienne chose
    # the midpoint on 2026-07-13 and that decision supersedes the doc.
    kept, no_comp, below = R.apply_pay_floor([_role(90000, 120000)])
    assert len(kept) == 1 and not below


def test_floor_drops_a_low_midpoint():
    # $75k-$105k -> midpoint $90k -> dropped.
    kept, no_comp, below = R.apply_pay_floor([_role(75000, 105000)])
    assert not kept and len(below) == 1


def test_floor_single_figure_is_the_midpoint():
    kept, _, below = R.apply_pay_floor([_role(100000, 100000)])
    assert len(kept) == 1 and not below


def test_floor_no_comp_is_excluded():
    kept, no_comp, _ = R.apply_pay_floor([_role(None, None)])
    assert not kept and len(no_comp) == 1


def test_floor_hourly_is_annualized_for_the_test_only():
    # $60/hr x 2080 = $124,800 -> clears. And the stored figure stays $60/hr.
    r = _role(60.0, 60.0, "hr")
    kept, _, below = R.apply_pay_floor([r])
    assert len(kept) == 1 and not below
    assert kept[0]["comp_low"] == 60.0 and kept[0]["comp_period"] == "hr"


def test_floor_hourly_below_floor_is_dropped():
    # $44.50-$50/hr -> midpoint $47.25 x 2080 = $98,280 -> under the floor.
    kept, _, below = R.apply_pay_floor([_role(44.5, 50.0, "hr")])
    assert not kept and len(below) == 1


def test_assert_floor_raises_on_a_liar():
    try:
        R.assert_floor([_role(50000, 60000)])
    except AssertionError:
        return
    raise AssertionError("assert_floor did not catch a below-floor role")


def test_prefilter_never_drops_a_widenable_single_figure():
    # Career Group's card prints only "$90,000" where the posting publishes
    # "$90,000 - $125,000" (midpoint $107.5k). enrich() widens it, so the cheap
    # pre-floor pass must leave a SINGLE figure alone even though 90k < 100k.
    kept, dropped = R.prefilter_floor([_role(90000, 90000)])
    assert len(kept) == 1 and not dropped


def test_prefilter_drops_a_settled_range():
    kept, dropped = R.prefilter_floor([_role(70000, 90000)])
    assert not kept and len(dropped) == 1


# =========================================================================== #
# 4. THE TAXONOMY
# =========================================================================== #
def _cat(title):
    v = R.classify_role(title)
    return v["category"] if v else None


def test_core_titles():
    assert _cat("Executive Assistant") == R.CAT_EA
    assert _cat("Chief of Staff") == R.CAT_COS
    assert _cat("Chief Operating Officer") == R.CAT_COO
    assert _cat("Director of Operations") == R.CAT_DVP
    assert _cat("Business Operations Manager") == R.CAT_XOPS


def test_chief_of_staff_beats_executive_assistant_when_it_leads():
    assert _cat("Chief of Staff/Strategic Executive Assistant to the CEO") \
        == R.CAT_COS


def test_executive_assistant_wins_when_it_leads():
    assert _cat("Executive Assistant to the CEO (with Chief of Staff duties)") \
        == R.CAT_EA


def test_longest_match_wins_within_a_position():
    # "Director of Business Operations" is Executive Operations, not Director/VP.
    assert _cat("Director of Business Operations") == R.CAT_XOPS


def test_abbreviations_normalize():
    assert _cat("Sr. EA to the Founder") == R.CAT_EA
    assert _cat("CoS to the CEO") == R.CAT_COS
    assert _cat("VP, Strategy & Ops") == R.CAT_XOPS


def test_ea_with_an_operations_mandate_is_exec_ops():
    assert _cat("Executive Assistant to Founder & Operations") == R.CAT_XOPS


def test_functional_ops_are_excluded_on_the_title():
    for t in ("Revenue Operations Manager", "Director of People Operations",
              "Sales Operations Lead", "Marketing Operations Manager",
              "Customer Operations Lead", "Product Operations Manager",
              "Clinical Operations Director", "IT Operations Manager",
              "Warehouse Operations Manager", "Supply Chain Operations Lead"):
        assert _cat(t) is None, t


def test_functional_ops_are_excluded_when_domain_is_not_adjacent():
    for t in ("Sales Strategy and Operations Manager",
              "Finance and Business Operations Lead",
              "Business Operations Lead, Commercial Launch Sales",
              "Product Strategy and Operations Manager"):
        assert _cat(t) is None, t


def test_out_of_scope_titles():
    for t in ("Senior Software Engineer", "Staff Accountant", "Recruiter",
              "Receptionist", "Office Manager"):
        assert _cat(t) is None, t


def test_household_roles_stay_excluded():
    assert _cat("Nanny / Personal Assistant") is None
    assert _cat("Estate Manager") is None
    assert R.classify_role(
        "Personal Assistant", context="support the family's home") is None


def test_an_ea_to_an_hr_exec_is_still_an_ea():
    # The People-Ops exclusion must never fire on a core EA title.
    assert _cat("Executive Assistant to Chief People Officer") == R.CAT_EA


def test_conditional_titles_are_flagged():
    for t in ("General Manager", "Managing Director", "Operations Lead",
              "Administrative Director", "Special Assistant to the CEO",
              "Senior Operations Analyst"):
        v = R.classify_role(t)
        assert v and v["action"] == R.CON, t


def test_core_flag():
    assert R.classify_role("Chief of Staff")["core"] is True
    assert R.classify_role("Executive Assistant")["core"] is True
    assert R.classify_role("Director of Operations")["core"] is False


# =========================================================================== #
# 5. THE FILTERING RULES -- signals and description-level exclusions
# =========================================================================== #
def test_inclusion_signals_counted():
    jd = ("This role reports directly to the CEO and owns cross-functional "
          "initiatives across multiple departments. You will run our OKRs and "
          "weekly leadership meetings, own quarterly planning, and prepare "
          "board materials.")
    assert R.count_signals(jd) >= 4


def test_no_signals_in_a_scheduling_jd():
    jd = ("Manage a complex calendar, book travel, submit expense reports, and "
          "greet visitors at the front desk.")
    assert R.count_signals(jd) == 0


def test_manufacturing_director_of_operations_is_excluded_by_description():
    # LaSalle, live 2026-07-13, $160k-$175k -- clears the floor, matches the
    # taxonomy title, and is a plant job.
    jd = ("The Director of Operations is responsible for leading all aspects of "
          "manufacturing and operational performance within a high-volume "
          "production environment. This role provides leadership across "
          "production, maintenance, warehousing, safety and quality.")
    assert R.excluded_by_description(jd) is not None


def test_one_stray_mention_does_not_exclude():
    # A single word in a company boilerplate paragraph is not a functional scope.
    jd = ("We are a software company serving manufacturing customers. The Head "
          "of Operations will report to the CEO and own company-wide planning.")
    assert R.excluded_by_description(jd) is None


def test_scope_gate_drops_an_unvalidated_conditional_title():
    r = R.build_role("t1", "General Manager", "S", "https://x/1")
    kept, dropped = R.scope_gate([r])
    assert not kept and dropped[0]["_why"].startswith("scope never validated")


def test_scope_gate_keeps_a_conditional_title_with_two_signals():
    r = R.build_role("t2", "General Manager", "S", "https://x/2")
    R.scope_verdict(r, "Reports directly to the CEO. Owns cross-functional "
                       "initiatives across multiple departments.")
    kept, dropped = R.scope_gate([r])
    assert len(kept) == 1 and not dropped


def test_scope_gate_drops_a_conditional_title_with_one_signal():
    r = R.build_role("t3", "Operations Lead", "S", "https://x/3")
    R.scope_verdict(r, "Reports directly to the CEO and manages the calendar.")
    kept, dropped = R.scope_gate([r])
    assert not kept and "1/2" in dropped[0]["_why"]


def test_scope_gate_never_scans_a_core_ea_title():
    # No description at all, and it still publishes: an EA title is unambiguous.
    r = R.build_role("t4", "Executive Assistant to the CEO", "S", "https://x/4")
    kept, dropped = R.scope_gate([r])
    assert len(kept) == 1 and not dropped


# =========================================================================== #
# 6. NEW SOURCE FORMATS  (one test per source, on its real payload shape)
# =========================================================================== #
def test_consider_salary_employer_published():
    job = {"salary": {"period": {"value": "year"}, "minValue": 180000,
                      "maxValue": 210000, "currency": {"value": "USD"},
                      "isOriginal": True}}
    assert R._consider_salary(job) == ((180000, 210000), None)


def test_consider_salary_estimate_is_not_a_salary():
    # THE Consider trap. isOriginal=False means CONSIDER estimated the range;
    # the employer published nothing. HappyRobot's Chief of Staff carries
    # 135000-210000 isOriginal=False and its Ashby posting prints no figure.
    job = {"salary": {"period": {"value": "year"}, "minValue": 135000,
                      "maxValue": 210000, "currency": {"value": "USD"},
                      "isOriginal": False}}
    assert R._consider_salary(job) == ((None, None), None)


def test_consider_salary_non_usd_is_dropped():
    job = {"salary": {"period": {"value": "year"}, "minValue": 8542,
                      "maxValue": 10675, "currency": {"value": "EUR"},
                      "isOriginal": True}}
    assert R._consider_salary(job) == ((None, None), None)


def test_consider_salary_hourly():
    job = {"salary": {"period": {"value": "hour"}, "minValue": 60,
                      "maxValue": 75, "currency": {"value": "USD"},
                      "isOriginal": True}}
    assert R._consider_salary(job) == ((60, 75), "hr")


def test_consider_no_salary_block():
    assert R._consider_salary({}) == ((None, None), None)


def test_getro_salary_is_in_cents():
    job = {"compensation_currency": "USD", "compensation_period": "year",
           "compensation_amount_min_cents": 17500000,
           "compensation_amount_max_cents": 25000000}
    assert R._getro_salary(job) == ((175000, 250000), None)


def test_getro_null_amounts_are_no_comp():
    # compensation_public is `true` even on rows with no figure, so it is not a
    # usable signal. The amounts are.
    job = {"compensation_currency": None, "compensation_public": True,
           "compensation_period": "period_not_defined",
           "compensation_amount_min_cents": None,
           "compensation_amount_max_cents": None}
    assert R._getro_salary(job) == ((None, None), None)


def test_getro_monthly_is_not_usable():
    job = {"compensation_currency": "EUR", "compensation_period": "month",
           "compensation_amount_min_cents": 854200,
           "compensation_amount_max_cents": 1067500}
    assert R._getro_salary(job) == ((None, None), None)


def test_linkedin_job_id_accepts_numeric_and_slugged_urls():
    numeric = R._LI_ID_RE.search("https://www.linkedin.com/jobs/view/4439351339/")
    slugged = R._LI_ID_RE.search(
        "https://www.linkedin.com/jobs/view/director-of-operations-at-theranica-4435178398")
    assert numeric and numeric.group(1) == "4439351339"
    assert slugged and slugged.group(1) == "4435178398"


def test_non_us_country_beats_remote_location_hint():
    assert not R.is_us_location("India - Remote, India")
    assert not R.is_us_location("Remote, Canada")
    assert R.is_us_location("Remote - United States")


def test_dedupe_normalizes_portfolio_company_title_and_city():
    a = R.build_role("a", "Chief of Staff, CEO", "Chief of Staff Network",
                     "https://www.chiefofstaff.network/jobs/handshake",
                     location="San Francisco, CA", org_type="Handshake",
                     comp=(256000, 320000))
    b = R.build_role("b", "Chief of Staff, CEO", "Lightspeed Portfolio",
                     "https://jobs.ashbyhq.com/handshake/abc",
                     location="San Francisco, California, United States",
                     org_type="Handshake", comp=(256000, 320000))
    kept = R.dedupe([a, b])
    assert len(kept) == 1
    assert kept[0]["id"] == "b"


def test_dedupe_does_not_merge_confidential_agency_searches():
    a = R.build_role("a", "Executive Assistant", "Beacon Hill",
                     "https://bhsg.com/jobs/1", location="New York, New York",
                     org_type="Beacon Hill Staffing Group",
                     comp=(110000, 120000))
    b = R.build_role("b", "Executive Assistant", "Beacon Hill",
                     "https://bhsg.com/jobs/2", location="New York, New York",
                     org_type="Beacon Hill Staffing Group",
                     comp=(140000, 150000))
    assert len(R.dedupe([a, b])) == 2


def test_cos_network_card_salary():
    # The card's salary slot, verbatim from the Selective Insurance card.
    body = ('<div class="jobs-meta"><div class="job-meta-item">'
            '<div class="icon-wrap is-job"><div class="flex w-embed"></div>'
            '</div><div>$300k - $350k</div></div>')
    m = R._COSN_SALARY.search(body)
    assert m and R.extract_comp(m.group(1), field=True) == (300000, 350000)


def test_cos_network_empty_salary_slot_yields_nothing():
    # SignalCore: Webflow renders the empty slot `w-condition-invisible` with a
    # `w-dyn-bind-empty` child. No salary means no salary -- and the DETAIL page
    # is a trap, printing other companies' pay in its related-jobs aside.
    body = ('<div class="jobs-meta"><div class="job-meta-item '
            'w-condition-invisible"><div class="icon-wrap is-job"></div>'
            '<div class="w-dyn-bind-empty"></div></div>'
            '<div class="job-meta-item"><div fs-list-field="location">'
            'Bay Area</div></div>')
    assert R._COSN_SALARY.search(body) is None


def test_cos_network_card_fields():
    body = ('<div fs-list-field="company" class="c">SignalCore</div>'
            '<h2 fs-list-field="title" class="t">Chief of Staff / Business '
            'Operations Lead</h2>'
            '<div fs-list-field="workplace" class="w">Hybrid</div>'
            '<div fs-list-field="location">Bay Area</div>')
    f = dict(R._COSN_FIELD.findall(body))
    assert f["title"] == "Chief of Staff / Business Operations Lead"
    assert f["company"] == "SignalCore"
    assert f["workplace"] == "Hybrid"
    assert R.classify_role(f["title"])["category"] == R.CAT_COS


def test_cos_network_description_is_scoped_to_posting():
    html = (
        '<div class="blog-rte w-richtext">'
        '<h2>The Role</h2><p>Partner with the CEO to run strategic planning, '
        'operating cadence, and cross-functional execution across the company.</p>'
        '</div><div class="spacer-medium"></div>'
        '<div class="button-group max-full"><a>Apply</a></div>'
        '<h2>Other Recommended Jobs</h2><div>$256k - $320k</div>'
    )
    desc = R._cosn_description(html)
    assert "strategic planning" in desc
    assert "Other Recommended Jobs" not in desc
    assert "$256k" not in desc


def test_extract_summary_prefers_explicit_role_section():
    text = """
Chief of Staff

Compensation

The base salary range reflects the minimum and maximum target for this position.

About Handshake

Handshake builds products that connect talent and employers around the world.

The Role

You will partner with the CEO to shape company strategy, drive operating
cadence, and lead the highest-priority cross-functional initiatives.

Responsibilities
"""
    summary = R.extract_summary(text, title="Chief of Staff")
    assert summary.startswith("You will partner with the CEO")
    assert "base salary range" not in summary

def test_lasalle_jsonld_is_scoped_to_its_own_job():
    # THE LaSalle trap: content.rendered carries a related-jobs block, so the raw
    # body of this $25-$30/hr EA also contains "$125,000 - $145,000" from another
    # posting. The embedded JSON-LD description is this job's and only this job's.
    content = (
        '<div class="related">Other jobs: $125,000 - $145,000</div>'
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"JobPosting",'
        '"title":"Executive Assistant","datePosted":"2026-07-12",'
        '"description":"<p>Compensation: $25-$30/hour. Support a senior '
        'partner.</p>",'
        '"jobLocation":{"@type":"Place","address":{"@type":"PostalAddress",'
        '"addressLocality":"New York","addressRegion":"New York"}}}'
        '</script>')
    post = R._lasalle_posting(content)
    assert post and post["title"] == "Executive Assistant"
    det = R._html_to_text(post["description"])
    assert R.extract_comp(det) == (None, None)          # it is hourly
    assert R.extract_comp_hourly(det) == (25.0, 30.0)   # ...and it is $25-$30/hr
    # and NOT the neighbouring job's $125k-$145k
    assert R.extract_comp(det)[0] != 125000


def test_lasalle_jsonld_tolerates_raw_control_characters():
    # The real blob carries them; json.loads(strict=True) refuses it.
    content = ('<script type="application/ld+json">'
               '{"@type":"JobPosting","title":"Head of Operations",'
               '"description":"Line one\nLine two"}</script>')
    assert R._lasalle_posting(content)["title"] == "Head of Operations"


def test_beacon_hill_salary_from_the_jd():
    jd = ("Our client is seeking a Chief of Staff. This hybrid opportunity is "
          "based in Boston, MA and pays $150,000-$180,000 annually.")
    assert R.extract_comp(jd) == (150000, 180000)


def test_beacon_hill_hourly_temp_role_stays_hourly():
    jd = ("...offers 25 hours per week, and pays $25-$35/hour depending on "
          "experience.")
    assert R.extract_comp(jd) == (None, None)
    assert R.extract_comp_hourly(jd) == (25.0, 35.0)


def test_pocketbook_up_to_figure():
    jd = ("Compensation & Benefits: Up to $170K DOE, full benefits package, "
          "equity, and additional perks are included.")
    assert R.extract_comp(jd) == (170000, 170000)


# =========================================================================== #
# 7. SOFT-404, DEDUPE, LOCATION
# =========================================================================== #
def test_soft_404_body_beats_the_status_code():
    # Recruiterflow answers 200 for a filled posting. Trusting the status was the
    # original bug.
    assert R.is_soft_404("<html><body>This job does not exist</body></html>")
    assert R.is_soft_404("Oops! We can't find that page")
    assert R.is_soft_404(
        "The job board you were viewing is no longer active.")
    assert R.is_soft_404(
        "Oops! The job you are looking for is no longer here.")
    assert R.is_soft_404(
        ("navigation " * 1000)
        + "The page has been removed, renamed, or is unavailable.")
    assert not R.is_soft_404(
        "<html><body>Chief of Staff at Acme. Reports to the CEO.</body></html>")


def test_dedupe_url_drops_the_tracking_query():
    # The same Lever posting, reached from two VC boards.
    a = "https://jobs.lever.co/databricks/abc?lever-source%5B%5D=jobs.a16z.com"
    b = "https://jobs.lever.co/databricks/abc?lever-source%5B%5D=jobs.lsvp.com"
    assert R.dedupe_url(a) == R.dedupe_url(b)


def test_dedupe_url_keeps_a_fragment():
    # Tack's Bullhorn portal routes on the fragment; stripping it would collapse
    # its whole board into one role.
    u1 = "https://x.co/plugins/bullhorn-oscp/#/jobs/159"
    u2 = "https://x.co/plugins/bullhorn-oscp/#/jobs/160"
    assert R.dedupe_url(u1) != R.dedupe_url(u2)


def test_dedupe_collapses_a_cross_listed_role():
    rs = [
        R.build_role("a", "Chief of Staff", "a16z Portfolio",
                     "https://jobs.lever.co/x/1?src=a16z",
                     org_type="Databricks", location="SF",
                     comp=(200000, 250000)),
        R.build_role("b", "Chief of Staff", "Lightspeed Portfolio",
                     "https://jobs.lever.co/x/1?src=lsvp",
                     org_type="Databricks", location="SF",
                     comp=(200000, 250000)),
    ]
    assert len(R.dedupe(rs)) == 1


def test_us_location_filter():
    assert R.is_us_location("New York, NY")
    assert R.is_us_location("San Francisco, California")
    assert R.is_us_location("Remote")
    assert R.is_us_location("")
    assert not R.is_us_location("London, UK")
    assert not R.is_us_location("Kaunas, Lithuania")
    assert not R.is_us_location("Munich")


def test_strip_private_keys():
    r = R.build_role("x", "General Manager", "S", "https://x/9")
    assert "_conditional" in r
    R.scope_verdict(r, "reports to the ceo, cross-functional")
    R.strip_private(r)
    for k in ("_conditional", "_core", "_signals", "_excl", "_scoped"):
        assert k not in r


# =========================================================================== #
def _main():
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in fns:
        try:
            fn()
        except Exception as e:
            failed += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main())
