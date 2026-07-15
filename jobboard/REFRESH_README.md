# Exec Ops Brief — Job Board Auto-Refresh

`refresh_roles.py` turns the static `roles.json` snapshot into a live-ish feed.
On each run it rebuilds the board from recruiting agencies, direct job boards,
and VC portfolio feeds; applies the taxonomy and filtering rules preserved in
the private source workbook and embedded in `refresh_roles.py`; dedupes; enriches;
and rewrites `roles.json`.

## How to run

```powershell
# From execops-brief-assets/jobboard
python refresh_roles.py 2026-07-14    # deterministic ISO run date
$env:REFRESH_DATE='2026-07-14'
python refresh_roles.py
Remove-Item Env:REFRESH_DATE
python refresh_roles.py               # defaults to today's date
```

Optional env var `REFRESH_SCRATCH` sets where the temporary firecrawl markdown
files are written (defaults to the system temp dir).

**Requirements:** the `firecrawl` CLI must be installed and configured on PATH
(`firecrawl scrape <url> --wait-for <ms> -o <file>`). Python 3.9+ (stdlib only —
no pip installs). A run reads 21 live source feeds and may fetch up to 200
per-role detail pages in addition to board/API requests. On 2026-07-14, a forced
full backfill took about 14.5 minutes and warm incremental passes took about
6-8 minutes.

The run date is passed in (arg or env) rather than read from the clock inside
the data pipeline, so `updated` is deterministic and testable.

Set `REFRESH_FULL=1` only when extractor changes require every eligible detail
page to be fetched again. Normal scheduled runs reuse the previous snapshot and
`partials/detail_cache.json`.

## Verified snapshot (2026-07-14)

This section is a dated verification record; daily counts will change.

- 221 published roles across 22 represented source labels.
- Category mix: 129 Executive Assistant, 65 Chief of Staff,
  22 Executive Operations, and 5 Director / VP of Operations.
- The grouped Exec Ops filter returns 27 strategic-operations roles.
- 219 of 221 roles have a summary (99.1%).
- The two deliberate summary exceptions are CA People Search's shared board URL
  and a Dali Associates PDF whose font extraction corrupts its text.
- Every role has employer-published compensation and a midpoint of at least
  $100,000; the hard floor assertion passed.
- The highest current range is $187,000-$429,000 for Chief of Staff, VP of
  Strategy and Operations at Nimble Storage.
- The final refresh removed 9 confirmed expired postings.
- `python -m pytest -q`: 81 passed.

## What it does

1. Scrapes each source board to markdown and parses out qualifying roles.
2. **Inclusion filter** (`classify()`): keeps Executive Assistant (to
   CEO/CTO/Founder/Partner/exec), Chief of Staff, Strategic EA, EA/Operations
   hybrids, and Business/Exec Operations. Drops household/family Personal
   Assistants, HNW/estate/principal private-service roles, standalone Office
   Managers, receptionists, recruiters, accountants, and other non-exec admin.
   Household detection reads the job description too, not just the title.
3. **Comp honesty:** captures a salary range **only** where the source prints
   it. Nothing is estimated or inferred. Sanity-bounded to $40k–$600k. Where a
   posting publishes an **hourly** rate instead of a salary (contract/temp
   roles), the enrichment pass stores the verbatim $/hr figures with
   `comp_period: "hr"`; the widget renders them as "$44.50 - $50/hr". Hourly
   comp is annualized (x2080) ONLY to apply the pay floor and the widget's
   min-comp filter — the displayed figure is always what the posting printed.
4. **The $100k pay floor** (see below) — the board's public promise, enforced
   in code. Roles that fail it are dropped.
5. **Dedupe:** by `apply_url` and by `(title, org_type, location)`.
6. Writes `{ _note, updated, count, roles:[...] }` with the schema
   (`id, title, org_type, category, seniority, comp_low, comp_high,
   location, remote, date_posted, apply_url, source, summary, benefits`,
   plus `comp_period: "hr"` on hourly-paid roles only). The
   `_note` is read from the current `roles.json` and preserved.
7. Prints a per-source success/fail log, the drop log, board counts, and the
   floor assertion.

## THE ROLE TAXONOMY (added 2026-07-14) — how the board stopped being an EA board

Spec: private source workbook dated 2026-07-13. The source workbook is not part
of this public deployment repository; all three sheets are implemented in
`refresh_roles.py`.

**The problem it fixes.** Every source the board had was an executive-support
recruiting agency, so the board was **92% Executive Assistant** (73 of 79 before
the pay floor; 58 of 64 after). It carried **3 Chief of Staff roles**. The point
of this release is real Chief of Staff and Executive Operations coverage.

### 1. Five visible categories (sheet: "Role Taxonomy", 130 titles)

`Executive Assistant` · `Chief of Staff` · `Executive Operations` ·
`Director / VP of Operations` · `COO / Operating Executive`

The old free-text bucket **`Exec Ops` is retired**; those roles now land in
`Executive Operations`, `Director / VP of Operations`, or
`COO / Operating Executive`. The widget labels the primary Executive
Operations option **Exec Ops & Operations Leadership** and treats it as a group
filter over all three categories. Exact Director/VP and COO subcategory options
remain available.

`classify_role()` matches a title against the taxonomy:

1. **Normalize** both sides — case, punctuation, `EA` → executive assistant,
   `CoS` → chief of staff, `Sr.` → senior, `&` → and, `Ops` → operations,
   `COO` → chief operating officer. The comma form is indexed too, so the
   sheet's "VP of Strategy and Operations" also matches the market's
   "VP, Strategy & Ops".
2. **Earliest match wins, then longest.** Earliest because the head of a title is
   the job: *"Chief of Staff / Strategic Executive Assistant to the CEO"* is a
   **Chief of Staff** role, though "Strategic Executive Assistant" is the longer
   phrase and a longest-match-only rule files it under EA. Conversely
   *"Executive Assistant to the CEO (with Chief of Staff duties)"* really is an
   **EA**, and it leads with it. Longest second, so "Director of Business
   Operations" beats "Director of Operations" and lands in Executive Operations.
3. **No taxonomy match → out.** This is the entire exclusion mechanism for the
   ~15,000 engineering / sales / support roles on the new VC boards. They simply
   do not match a title.

### 2. Description-first validation (sheet: "Filtering Rules")

*"A matching title is not enough for broad operations roles. Validate the actual
scope."* `scope_gate()` runs after `enrich()`, which is when the description
exists.

- **CORE** titles (the Executive Assistant / Chief of Staff families) are trusted
  on the title alone and are **never scope-scanned**. "Executive Assistant to the
  Chief People Officer" is an EA job, not an HR Ops job.
- **BROAD** titles (Executive Operations / Director-VP / COO) are dropped when
  the description shows an excluded functional or industry scope. Requires **two**
  distinct hits: one stray "manufacturing" in a company boilerplate paragraph is
  not the role's scope, two is. This is what kills LaSalle's *Director of
  Operations* — a $160k–$175k role that clears the floor, matches the taxonomy,
  and is a high-volume **plant** job.
- **CONDITIONAL** titles (General Manager, Managing Director, Operations Lead,
  Administrative Director, Special Assistant to the CEO, Senior Operations
  Analyst, …) must show **≥ 2 of the 7 inclusion signals** — executive reporting
  line, cross-functional ownership, operating cadence, strategic planning, exec
  decision support, special projects, systems/scale. **No description → not
  published.** We do not guess at scope any more than we guess at pay.

The scope verdict is **cached** (`partials/detail_cache.json`) alongside the comp
verdict, and a still-valid entry is touched on every run. Without that, a broad
role validated on Monday would be silently dropped on Tuesday, when the run
reuses the cache instead of re-fetching the description.

Title-level exclusions (`_EXCL_TITLE`) are immediate and cover the sheet's whole
list: People/HR/Talent, Sales/Revenue, Marketing/Growth, Customer/Support/Success,
Product, Clinical/Healthcare, Manufacturing/Plant/Production, Warehouse/Logistics,
Retail/Store/Restaurant, Field/Regional service, IT/Network/Cloud/Security,
Facilities/Workplace, Supply Chain/Procurement, Legal/Finance/Accounting, and
investment portfolio management (which is *not* portfolio-company operations).

The household / private-service exclusion predates the xlsx and is still law.

## THE $100k PAY FLOOR (added 2026-07-13) — the board's promise

> ### ⚠ The MIDPOINT rule SUPERSEDES the xlsx. Do not "fix" it back.
>
> The "Filtering Rules" sheet says to *"include only when the **bottom** of the
> published annual base range is at least $100,000"* (so an $80K–$120K range
> would fail) and sets an **hourly floor of $50/hour**.
>
> **Adrienne was asked directly on 2026-07-13 and chose the MIDPOINT.** The code
> implements the midpoint, and that decision overrides the sheet's wording:
>
> - `$90k–$120k` → midpoint `$105k` → **STAYS** (the sheet's strict rule would
>   drop it).
> - `$75k–$105k` → midpoint `$90k` → **DROPPED**.
> - Hourly is annualized at 2,080h against the same $100k midpoint, which works
>   out to **$48.08/hr**, not the sheet's $50/hr.
>
> A future reader who "corrects" the code to match the doc will silently shrink
> the board. `test_floor_is_the_midpoint_not_the_bottom` in
> `test_refresh_roles.py` exists to stop exactly that.
>
> Everything else in the sheet's compensation block is implemented as written:
> **no published comp → excluded**, and *"do not infer salary from title alone."*


The site says the board is $100k+. Until 2026-07-13 nothing enforced that: 13
of 79 live roles published no comp at all and several published ranges whose
midpoint fell below $100k. `apply_pay_floor()` now makes the claim true.
**The rules, implemented exactly:**

1. **Floor test = MIDPOINT ≥ $100,000.** `midpoint = (comp_low + comp_high)/2`.
   Where only ONE figure is published, that figure IS the midpoint.
   `$90k–$120k` (mid $105k) **stays**. `$75k–$105k` (mid $90k) is **dropped**.
2. **No published comp → excluded.** But only after a genuine extraction
   attempt: the listing parse, then the detail page, then (for LinkedIn-hosted
   roles) LinkedIn's own guest endpoint. Dropping a role because the extractor
   is lazy is a bug, not a policy.
3. **Hourly roles** are annualized (rate × 2080) **for the floor test only**.
   They keep displaying the verbatim `$/hr` with `comp_period:"hr"`.
4. **Comp honesty outranks board size.** Nothing is ever estimated, inferred, or
   interpolated to clear the floor. A smaller honest board is the goal.

`assert_floor()` runs on every run and **raises** if any published role has null
comp or a midpoint under $100k, so the board can never silently start lying.
A run prints:

```
  Roles found (deduped)        : 81
  Dropped -- no published comp : 9
  Dropped -- midpoint < $100k  : 8
  BOARD (all >= $100k midpoint): 64

[ASSERT] PASS: 64/64 roles have a published comp figure and a midpoint
         >= $100,000. 0 null-comp, 0 below floor.
```

### Where the missing salaries actually were (investigated 2026-07-13)

13 live roles published no comp. Each one's detail page was fetched and read by
hand. The answer split cleanly:

- **Truex Metier (4) — RECOVERED.** Their site embeds a LinkedIn widget that
  used to print comp and now renders **zero** `$` characters, and firecrawl
  refuses `linkedin.com` outright ("we do not support this site"). But the comp
  is still published: LinkedIn's public guest endpoint
  `/jobs-guest/jobs/api/jobPosting/<id>` answers a plain `GET` and carries the
  employer's own range in a `compensation__salary` div. `fetch_linkedin()` reads
  **only that div**. All four came back ($120k–$140k up to $150k–$190k) and all
  four clear the floor. Note: the full `/jobs/view/<id>` page also carries the
  salaries of *similar jobs* in its sidebar, so scraping that page wholesale
  would attach another company's pay to the role. We never do.
- **Groupe Insearch (6) — genuinely not published.** Detail pages print perks
  only: "Competitive compensation and bonus structure", "Strong base
  compensation with annual performance bonus". The only dollar figures on the
  page are `Gym reimbursement $750/yr` and `Commuter benefits $475/mo`, which
  the disqualify rules explicitly refuse to read as salary.
- **C-Suite Assistants (2) — genuinely not published.** "Competitive Base
  Salery [sic], Discretionary Bonus, Comprehensive Health Benefits". No figure.
- **Career Group (1) — genuinely not published.** The detail page renders the
  salary field as a literal `-`.

So the "the salary is on the detail page" hypothesis was **right for 4 of 13 and
wrong for the other 9**. Those 9 are dropped, honestly. Insearch now contributes
**0 roles** to the board.

### Extractor rewrite (same change)

`extract_comp` / `extract_comp_hourly` went from "first regex hit in a label
window" to "enumerate every money figure, decide its period from the unit
printed beside it, reject disqualifying contexts, score, take the best".
Formats now handled: `$120K-$140K`, `120,000-140,000 per year`,
`up to $150,000`, `$130,000.00/yr - $150,000.00/yr`, `150-180K+ DOE`,
`200k base`, en/em-dash ranges, `$60/hour`, `$44/hr to $50/hr`.
"Competitive" and "commensurate with experience" yield nothing, by design.

The **honesty gate** is the core of it:

- **MARKED** (both kinds): the posting must mark the figure as money — a `$`, a
  `k` suffix, or an explicit annual unit. This is what stops
  `100-200 employees` becoming a $100k–$200k salary and `<Base64-Image-Removed>`
  becoming a $64,000 offer (that one was live).
- **ANCHORED** (lone figures only): a single figure must also sit next to a comp
  label or an annual unit. A bare `$150,000` in a JD could be a budget or a fund
  size.
- A two-ended, money-marked **range** needs no label. Requiring one deleted all
  8 Bloom Talent salaries in testing, because Bloom writes `150-180K+ DOE` with
  no `$`, no label, and a `+` that blocks a trailing-label match.
- The disqualify lookback is confined to the figure's **own line**. A flat
  character lookback crossed newlines and let Tack's
  `"...(hybrid, 4 days per week)\n\nCOMPENSATION\n$150K - $180K base"` be killed
  by "per week" — a *schedule*, not a pay period.

Career Group's board card prints only the LOW end (`$100,000`) where the posting
publishes the full range (`Base Salary: $100,000 - $125,000`). `_widen_from_detail()`
upgrades a single figure to the detail page's range **only when the range starts
at that same figure**, so it can never pull in an unrelated number.

### Rate limiting / caching (so the 7am run stays polite)

- `SCRAPE_MIN_INTERVAL` (0.8s) throttles every outbound fetch, firecrawl and
  LinkedIn alike.
- `MAX_DETAIL_FETCHES` (200) caps per-role detail fetches per run.
- `partials/detail_cache.json` (gitignored, machine-local) remembers the verdict
  for each detail page. It exists because floored-out roles vanish from
  `roles.json`, so the roles.json carry-over can no longer remember we already
  checked them; without it the daily run would re-fetch the same "no comp
  published" pages every morning. A **no-comp verdict is re-checked after 7 days**
  (`NO_COMP_TTL_DAYS`), so a firm that starts publishing pay gets picked up.
  `REFRESH_FULL=1` bypasses it entirely.

### If you touch the extractor, run the no-regression check

A scraper that quietly loses valid roles is worse than no floor at all. Before
committing, diff the new `roles.json` against the committed one and classify
**every** role that disappears as dropped-for-no-comp / dropped-for-floor /
source-404 / **UNEXPLAINED**. Any UNEXPLAINED drop is a bug.

Note that Recruiterflow (Bloom Talent) **soft-404s**: a filled posting keeps
returning **HTTP 200** with the body "This job does not exist". A status-code
check will tell you a dead role is still live. Check the body.

## Resilience / safety

- Every source parser is wrapped in `try/except`. A source that fails (site
  down, markup changed) is logged and skipped — it never aborts the run.
- If the post-floor board falls below `MIN_SAFE_TOTAL` (**30**; the expanded
  board currently runs above 200), the script
  **refuses to overwrite** `roles.json` and exits non-zero, so a broadly broken
  run (e.g. firecrawl offline) can't wipe a good board. `run_refresh.bat` only
  commits/pushes on a zero exit, so a refused run leaves the live board alone.
- Detail-page comp fetches (Bloom/Burke/Aux) are individually try/excepted; a
  failed detail fetch just yields `null` comp for that one role.

## Enrichment pass (added 2026-07-06)

After dedupe, `enrich()` visits every role's detail page (reusing pages the
parsers already fetched) and fills three things, all under the same honesty
rule as comp:

- **Comp rescue:** many firms only print salary on the detail page (e.g. The
  Hire Standard's "Perks & Benefits" section). If the listing pass got `null`,
  the detail text is re-parsed. With the LinkedIn rescue added 2026-07-13,
  real-comp coverage on the published board is 100% by construction: a role
  without a published figure is not published.
- **`summary`:** the first substantive descriptive paragraph of the posting,
  excerpted VERBATIM and clipped at a sentence boundary. The scan prefers
  explicit role-section headings such as "The Role" and "The Opportunity",
  then falls back to the job-title heading (ATS pages bury the JD under site
  chrome). It rejects nav walls, Title Case menu lists, ALL-CAPS headers, title
  restatements, and PDF ligature-damaged text. `null` when nothing publishable
  is found.
- **`benefits`:** tags (Bonus, Equity, 401(k), Health coverage, Paid time off,
  Parental leave, Wellness, Meals, Profit sharing, Overtime pay) detected only
  where the posting literally states them. DEI "equity" and "Bonus Points For"
  do NOT count.

Carry-over: previous-run results are reused by `apply_url`, so a scheduled run
only fetches detail pages for NEW roles. A cached role with a blank summary is
retried after its detail-cache entry expires, so extractor improvements can
backfill it. Set env `REFRESH_FULL=1` to force a re-fetch of everything (use
after improving the extractors). Roles whose
`apply_url` is a shared board page (CA People Search) are never enriched.
LinkedIn-hosted roles (Truex Metier) are enriched through `fetch_linkedin()`
rather than firecrawl, which refuses linkedin.com.

**Expired-link guard (added 2026-07-08):** some ATSes (Loxo) redirect an
expired job URL to the agency's full board. A fetched "detail" page carrying
4+ distinct job links is treated as such a redirect. Friendly HTTP-200 error
pages ("job no longer here", "job board no longer active") are treated the same
way. Another job's summary/comp is never attached to the role, and the confirmed
expired role is removed from the board immediately (logged as `[exp ]`). The
verdict is cached so a stale aggregator row does not trigger a daily re-fetch.

The widget fetches `roles.json` from **GitHub Pages** (same origin as the
widget, ~10 min cache, auto-fresh on push). The jsDelivr purge in
`run_refresh.bat` is kept for any other consumers but is no longer load-bearing.

## Sources implemented (all parse live today)

| Source | Board / ATS | Comp published? | Notes |
|---|---|---|---|
| Bloom Talent | recruiterflow.com/bloomtalent | On detail page | Comp parsed from each detail body (e.g. "150-180K DOE"). |
| Career Group | careergroupcompanies.com/find-work | Inline | Salary and hourly ranges parsed. Hourly figures retain `comp_period: "hr"`. |
| Burke & Co | Loxo (app.loxo.co/burke-co-1) | On detail page | Comp from "COMPENSATION: $X to $Y" on detail. Org/city parsed from title. |
| Aux Talent | auxtalent.com/jobs | On detail page (some) | Comp parsed where the detail page states it, else null. |
| Tack Advisors | Bullhorn OSCP (tackadvisors.co/career-portal) | Inline | Full detail rendered on the portal incl. COMPENSATION. Anchors may emit a doubled `#/jobs/jobs/N` route (renders the board); parser accepts both and stores the canonical `#/jobs/N`. Flaky SPA render: retried, then plugin URL fallback. |
| C-Suite Assistants | Top Echelon (careers.topechelon.com) | Inline (some) | "$X - $Y / yr" where present, else null. |
| Groupe Insearch | insearchsf.com/current-jobs | **Never** | Re-verified 2026-07-13: detail pages say "competitive compensation", no figure. Every Insearch role fails the floor's no-comp rule, so **0 of their roles reach the board**. |
| The Hire Standard | JobAdder (clientapps.jobadder.com/58431) | Sometimes in blurb | Comp parsed from the description blurb where stated. |
| CA People Search | capeoplesearch.com/current-openings | Inline | Low-volume; no per-job URLs, so `apply_url` points at the openings page (verified again 2026-07-08: still none). |
| Truex Metier | LinkedIn widget on truexmetier.com/jobs | Via LinkedIn guest API | The widget stopped printing comp (zero `$` on the page as of 2026-07-13) and firecrawl refuses linkedin.com. `fetch_linkedin()` reads the pay range from LinkedIn's public guest endpoint instead. All 4 roles recovered. |

### Priority-1 sources added 2026-07-14 (the "New Sources" sheet)

These do **not** go through firecrawl. Every one of them answers a plain
GET/POST, so they use `http_get()` / `http_json()` — throttled by the same
`SCRAPE_MIN_INTERVAL`, and every fetched page has its **body** checked by
`is_soft_404()` (a 200 is not proof of a live posting).

| Source | How it is read | Comp published? | Notes |
|---|---|---|---|
| **Chief of Staff Network** | Webflow CMS, `/jobs?4b2fa278_page=N`, server-rendered | Inline on the card, when the employer gave one | The best source for real Chief of Staff roles. Company, title, workplace, location, posted date **and salary** come from the card. For roles that clear the pay floor, the scraper also fetches only the posting's bounded `blog-rte` description block. It never parses salary from the detail page because the related-jobs rail prints OTHER companies' pay. A card with no salary means no salary, and the role is dropped. |
| **Pocketbook Agency** | `careers.pocketbookagency.com/?rtype=Corporate` (Next.js) | In the JD ("Up to $170K DOE") | The URL in the sheet (`pocketbookagency.com/jobs/`) is **stale** — the board moved. Only the **Corporate** stream is read; `?rtype=Domestic` is private household/estate staffing and is out of scope, so we never fetch it. |
| **Beacon Hill** | WordPress REST, `bhsg.com/jobs/wp-json/wp/v2/job-listings?search=…` | In the JD | One request per taxonomy seed. `meta._job_location`, `meta._filled` (filled postings skipped), `meta._remote_position`. `content.rendered` is this job's JD only — no sidebar. |
| **LaSalle Network** | WordPress REST, `/wp-json/wp/v2/ce_job` (196 jobs in 2 requests) | "Compensation: $X to $Y" in the JD | **robots.txt disallows `/job-search/*?` and `/*?ce_job=*`** — the query-string search pages. We do not touch them; `/wp-json/` is not disallowed and is a better feed anyway. **The trap:** `content.rendered` carries a related-jobs block, so an EA paying $25–$30/hr also contains "$125,000 - $145,000" from another posting. LaSalle embeds a **JSON-LD JobPosting** inside that content whose `description` is *this* job's and nothing else — that is what comp is read from. (Needs `json.loads(strict=False)`: the blob carries raw control characters.) |
| **Consider** → **a16z, Sequoia, Bessemer, Lightspeed** | `POST /api-boards/search-jobs` on each board's own host, with the `x-csrf-token` its JS reads from `window.serverInitialData` | Structured `salary` block | One parser, four boards. `titlePrefix` is really a phrase-contains match, so a compact seed list covers the taxonomy without pulling 15,000 rows. |
| **Getro** → **General Catalyst, Accel, Insight Partners** | `POST api.getro.com/api/v2/collections/<id>/search/jobs`, no auth | `compensation_amount_*_cents` | One parser, three boards. Collection ids (stable): GC **222**, Accel **8672**, Insight **246**. Comp is in **cents**; USD + year/hour only. `compensation_public` is `true` even on rows with no figure, so it is **not** a usable signal — the amounts are. |

#### The Consider honesty trap (`salary.isOriginal`) — the most important line in the new code

Consider returns a salary range on jobs where **the employer published nothing**:

- `isOriginal: true` → the **employer** published this range. Usable.
- `isOriginal: false` → **Consider estimated it.** Not published.

Verified 2026-07-13: HappyRobot's *Chief of Staff* comes back as
`135000–210000, isOriginal: false`, and its actual Ashby posting prints **zero
dollar figures**. Publishing that number would be precisely the fabrication rule
2 forbids. `_consider_salary()` reads `isOriginal: true` only; a `false` row is
treated as **no comp** and the role is dropped. `test_consider_salary_estimate_is_not_a_salary`
guards it.

#### Cross-board dedupe

The four Consider boards and three Getro boards list the same employer postings,
each stamping its own tracking parameter on the apply link
(`…?lever-source[]=jobs.a16z.com` vs `…?lever-source[]=jobs.lsvp.com`), so the
same Databricks Chief of Staff would land on the board four times. `dedupe_url()`
drops the **query string** (every source here identifies a job by path) but
**keeps the fragment**, because Tack's Bullhorn portal routes on `#/jobs/<id>`
and stripping it would collapse its whole board into one role.

URL normalization is the first pass. A second pass implements the workbook's
normalized **company + title + location** rule, reducing locations to a
city-level identity so San Francisco and San Francisco, CA, USA collapse.
When a role appears on Chief of Staff Network and a portfolio board, the direct
employer link wins. Confidential agency searches are deliberately exempt when
the only apparent company is the staffing firm itself.

#### US-only

The board is a US board and a EUR/GBP figure cannot be compared to a $100k floor.
The provider parsers require **USD** comp and drop roles whose location names a
non-US country (`is_us_location()`).

Country evidence wins over work-mode text: India - Remote, India is non-US;
the word Remote cannot turn it into a US role.

### Runtime

`prefilter_floor()` runs the floor **before** enrichment. The VC boards hand us
the salary in the search response, so hundreds of roles are known to fail the
floor before a single detail page is fetched, and enriching them would burn a
fetch each. It only ever drops comp that `enrich()` can no longer change — a
two-ended published range, or an hourly rate. A **single** published figure is
left alone, because `_widen()` can still upgrade it to the source's fuller range
(Career Group prints "$100,000" on the card where the posting says
"$100,000 - $125,000"), which can only ever *raise* the midpoint. Dropping those
here would re-introduce the exact silent-loss bug the no-regression check exists
to catch.

Chief of Staff Network is **salary-card-only**, not detail-free. Its cards
contain the employer-published salary. For roles that clear the floor, the
scraper fetches only the posting's bounded `blog-rte` description block.
It never parses compensation from the rest of the detail page because the
recommended-jobs rail contains other employers' salary figures.

Freshness is sourced rather than invented: every automated feed is rebuilt from
its current listings, soft-404 bodies are rejected, and the widget sorts dated
roles newest-first. Listings without a published date sort after the dated set
instead of masquerading as newly posted.

## Curated manual sources (partials/manual.json)

`partials/manual.json` holds hand-curated roles from sources that cannot be
automated (per-role PDFs, low-volume firms). It is **merged into every run
automatically** and its rows go through the same dedupe/enrich/floor pipeline.
Edit it by hand as those roles fill/expire. Currently: Dali Associates
(per-role PDF postings), The Larko Group, Premier Talent Partners.

## Sources NOT automated (flag for manual review)

These came from the earlier manual sourcing plan and are intentionally **not**
scraped here; check them by hand during Brief prep:

- **Palo Alto Staffing** — MapleDrive ATS, 0 open at last pull. Re-check
  manually when they have openings.
- **EA Search** — submit-resume only, no public board.
- **Whitman Associates, Mission Staffing** — live boards but low/occasional
  qualifying volume; candidates for a future parser if they prove consistent.
- **Watch list** (Tiger, Clarity, 80Twenty, Green Key) — no qualifying role at
  first pull; monitor manually.
- **Excluded on scope:** Society Staffing, Hire Society (estate/private
  service); Bloomfield & Co, Ruby Peak (no public board).

## Scheduling & deploy

This script only writes `roles.json` locally. It does **not** commit or push.
Deployment is handled by the wrapper:

- Windows Task Scheduler task `ExecOpsBrief-RolesRefresh` is installed and
  was verified **Ready** on 2026-07-14.
- It runs `run_refresh.bat` daily at **7:00 a.m. Pacific**.
- The batch file runs the scraper and stops without committing when it exits
  nonzero (including the suspiciously-small-board safety refusal).
- A successful changed snapshot is committed and pushed to
  **execops-brief-assets** so GitHub Pages serves it, then the jsDelivr copy is
  purged. An unchanged snapshot produces no commit.
