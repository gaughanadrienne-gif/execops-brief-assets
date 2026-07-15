# Changelog

## 2026-07-14

### Deployment record

The following commits were deployed to `main`:

- `8b5af13 Daily roles refresh`
- `0d80059 Expand job board sources and role taxonomy`
- `f24cba5 Fix strategic role filters and card metadata`
- `56129bd Update compensation tools with validated benchmarks`

### Job board: source and taxonomy expansion

- Added the role taxonomy and filtering rules from
  `jobboard/reference/EOB_Job_Board_Role_Taxonomy_and_New_Sources.xlsx`.
- Replaced the old broad `Exec Ops` data bucket with five defined categories:
  Executive Assistant, Chief of Staff, Executive Operations,
  Director / VP of Operations, and COO / Operating Executive.
- Added description-first validation for broad and conditional operations
  titles so manufacturing, clinical, revenue, and other functional-operations
  roles do not enter the executive-operations board merely because their titles
  contain "operations."
- Added 11 priority source feeds:
  Chief of Staff Network, Pocketbook Agency, Beacon Hill, LaSalle Network,
  a16z, Sequoia, Bessemer, Lightspeed, General Catalyst, Accel, and
  Insight Partners.
- Added shared parsers for Consider portfolio boards and Getro portfolio boards,
  including USD/US-location checks and cross-board URL deduplication.
- Kept Consider salary estimates out of the board unless
  `salary.isOriginal` proves the employer published the figure.
- Kept Groupe Insearch out of the published board because its individual
  postings still do not publish compensation. Its 2022 guide remains suitable
  only as labeled market context, not as job-level pay.

### Job board: compensation and data integrity

- Preserved the user-approved pay rule: a role qualifies when the midpoint of
  its employer-published range is at least $100,000. The workbook's stricter
  low-end rule does not apply.
- Continued to exclude every role without a published compensation figure.
- Annualized hourly pay only for the floor test and filter; the UI continues to
  display the employer's hourly figure.
- Added a hard assertion that refuses to publish null compensation or a
  midpoint below $100,000.
- Scoped Chief of Staff Network compensation to its listing cards. Detail pages
  are read only for the posting's bounded description block, never for salary,
  because their recommended-jobs rail contains unrelated compensation.

### Job board: widget and content quality

- Changed the main Executive Operations option to display as
  **Exec Ops & Operations Leadership**.
- Made that option a group filter over Executive Operations,
  Director / VP of Operations, and COO / Operating Executive while retaining
  exact subcategory filtering.
- Added a truthful organization-line fallback: when `org_type` is absent, the
  card displays the recruiting/source name instead of a blank line. The source
  pill is suppressed when it would duplicate that fallback.
- Improved summary extraction to prefer explicit sections such as "The Role"
  and "The Opportunity" over ATS compensation or company boilerplate.
- Added blank-summary cache retries and ran a one-time full backfill followed by
  incremental passes.
- Expanded friendly-200/redirect detection and now remove confirmed expired
  postings immediately. Expired verdicts are cached so stale aggregator rows do
  not trigger a daily refetch.

### Verified job-board snapshot

This is a dated verification snapshot, not a permanent count:

| Metric | Verified value |
|---|---:|
| Data date | 2026-07-14 |
| Published roles | 221 |
| Source labels represented | 22 |
| Executive Assistant | 129 |
| Chief of Staff | 65 |
| Executive Operations | 22 |
| Director / VP of Operations | 5 |
| COO / Operating Executive | 0 |
| Grouped Exec Ops filter | 27 |
| Roles with summaries | 219 of 221 (99.1%) |
| Confirmed expired roles removed in final run | 9 |
| Highest published range | $187,000-$429,000 |
| Highest-range role | Chief of Staff, VP of Strategy and Operations at Nimble Storage |
| Live source parsers successful | 21 of 21 |
| Regression tests | 81 passed |

All 221 published roles passed the compensation assertion: a real published
figure, a midpoint of at least $100,000, no null compensation, and no
below-floor role.

The two intentional summary exceptions are:

- CA People Search: the source uses one shared openings page rather than a
  role-specific detail URL.
- Dali Associates: the source PDF has broken font/ligature extraction, so the
  scraper leaves the summary blank instead of publishing corrupted text.

### Automation and launch

- Verified Windows Task Scheduler task `ExecOpsBrief-RolesRefresh` is Ready and
  runs `jobboard/run_refresh.bat` daily at 7:00 a.m. Pacific.
- The batch file rebuilds `roles.json`, refuses to push after a failed or
  suspiciously small run, commits successful changes, pushes to GitHub Pages,

### Documentation audit

- Created this dated release record covering every July 14 deployment and the
  live-site launch.
- Updated the root README from its July 8 state to the current hosted assets,
  public verification URLs, and automated job-board deployment workflow.
- Updated `jobboard/REFRESH_README.md` to match the 200-page detail cap,
  grouped filter, safe Chief of Staff Network description behavior, current
  board scale, and installed scheduler.
- Removed references to the nonexistent `job-sources.md`.
- Corrected the scraper's comments and Career Group hourly-pay docstring.
- Corrected the persistent `roles.json` note so future refreshes describe the
  current source mix and do not claim that every role has a summary.
  and purges the jsDelivr copy.
- The updated widget embed was placed on the live roles page.
- A LinkedIn launch post directed readers to the board using the dated,
  verified claims "200+ active roles" and "salary ranges as high as $429K."

### Compensation tools

- Added `tools/compensation-data.json`, versioned 2026-07-14, so benchmark
  values retain their source, sample, measure, and selection notes.
- Updated the salary benchmarker to distinguish employer wages, projected
  starting pay, self-reported incumbent pay, and premium active postings rather
  than presenting them as interchangeable measures.
- Added explicit sample/confidence notes and source links to benchmark results.
- Updated the offer evaluator to compare base salary with a named observed
  benchmark, separate guaranteed cash from target cash, treat equity as an
  information-readiness question, and identify unresolved offer terms.
- Removed unsupported role, location, remote-work, and experience multipliers.
- Kept the previous inline offer-evaluator script inert as
  `type="text/plain"`; the active implementation is
  `tools/offer-evaluator-v2.js`.
