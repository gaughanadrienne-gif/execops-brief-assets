# execops-brief-assets

Last updated: 2026-07-14

Public GitHub Pages asset repo for The Exec Ops Brief.

Live base URL:

```text
https://gaughanadrienne-gif.github.io/execops-brief-assets/
```

## Current Status

The repository is deployed from `main` through GitHub Pages. The July 14
feature release includes compensation-tools commit
`56129bd Update compensation tools with validated benchmarks` and job-board commit
`f24cba5 Fix strategic role filters and card metadata`. Its generated snapshot
contains 221 roles as of 2026-07-14. See [CHANGELOG.md](CHANGELOG.md) for the
complete July 14 release record.

## July 14 deployment

- Expanded the job board from executive-support agencies into Chief of Staff and
  strategic-operations sources using the workbook taxonomy.
- Enforced the published-compensation rule: every displayed role has a published
  range whose midpoint is at least $100,000.
- Grouped Executive Operations, Director/VP Operations, and COO/Operating
  Executive roles under the main Exec Ops filter.
- Backfilled role summaries, added a truthful source-name fallback when a
  recruiter/company field is unavailable, and removed confirmed expired roles.
- Rebuilt the salary benchmarker and offer evaluator around a versioned,
  source-linked compensation dataset with explicit sample and confidence notes.

## Hosted Assets

- Job board widget: `jobboard/roles-widget.html`
- Job data: `jobboard/roles.json`
- Salary tool: `tools/salary-benchmarker.html`
- Offer evaluator: `tools/offer-evaluator.html`
- Offer evaluator runtime: `tools/offer-evaluator-v2.js`
- Compensation dataset: `tools/compensation-data.json`
- First 90 days tool: `tools/first-90-days-tool.html`
- Readiness quiz: `tools/readiness-quiz.html`
- Site script layer: `eob-site-scripts.js`
- Imported article HTML: `import/`

## Deploy Workflow

From this folder:

```powershell
git status --short
git push
```

The job board also refreshes automatically through the Windows Task Scheduler
task `ExecOpsBrief-RolesRefresh`, which runs `jobboard/run_refresh.bat`
daily at 7:00 a.m. Pacific. The script only commits and pushes when the scraper
exits successfully.

After pushing, verify:

- `https://www.execopsbrief.com/roles`
- `https://www.execopsbrief.com/salary-benchmarker`
- `https://www.execopsbrief.com/offer-evaluator`
- `https://www.execopsbrief.com/first-90-days-tool`
- `https://www.execopsbrief.com/readiness-quiz`

For job-board-specific operation, policy, source, and verification details, see
[`jobboard/REFRESH_README.md`](jobboard/REFRESH_README.md).

