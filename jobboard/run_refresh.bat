@echo off
REM ============================================================
REM  The Exec Ops Brief - daily roles board refresh
REM  Scrapes agencies, rebuilds roles.json, pushes to GitHub,
REM  purges the CDN. Scheduled via Task Scheduler (daily 7:00 AM,
REM  task name ExecOpsBrief-RolesRefresh).
REM  PATH is set explicitly so it works in the minimal task env.
REM ============================================================
setlocal
set REPO=C:\Users\Adrie\OneDrive\Businesses\Exec Ops Brief\Website\execops-brief-assets
set LOG=%REPO%\jobboard\refresh.log
REM -- ensure python, git, firecrawl (npm), and System32 (curl) are found --
set PATH=C:\Users\Adrie\AppData\Local\Programs\Python\Python314;C:\Users\Adrie\AppData\Local\Programs\Python\Python314\Scripts;C:\Program Files\Git\cmd;C:\Users\Adrie\AppData\Roaming\npm;C:\Windows\System32;%PATH%

echo ============================================== >> "%LOG%"
echo [%DATE% %TIME%] refresh start >> "%LOG%"

cd /d "%REPO%\jobboard"
python refresh_roles.py >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [%DATE% %TIME%] scraper returned nonzero -- NOT pushing >> "%LOG%"
  exit /b 1
)

cd /d "%REPO%"

REM -- Live Comp Explorer data, rebuilt from the board we just scraped.
REM    Kept here rather than on its own schedule so the figures can never be
REM    older than the roles.json they describe. build_comp_explorer.py imports
REM    salary_report.py as a module, re-asserts the $100k published-comp floor
REM    across every posting, and RAISES rather than writing if one fails, so a
REM    bad board cannot publish a figure. Its write is temp-file-then-replace,
REM    so a failed build leaves the last good data file intact. On failure we
REM    log and carry on: the tool then states on-page that the board has
REM    refreshed since the figures were computed, which is honest, whereas
REM    aborting the whole refresh over it would cost the roles push too.
REM    No CDN purge: the tool fetches this file from GitHub Pages, not jsDelivr.
set ANALYTICS=C:\Users\Adrie\OneDrive\Businesses\Exec Ops Brief\Analytics ^& SEO\Analytics
python "%ANALYTICS%\build_comp_explorer.py" --out "%REPO%\tools\comp-explorer-data.json" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [%DATE% %TIME%] comp explorer build failed -- keeping previous data file >> "%LOG%"
) else (
  git add tools/comp-explorer-data.json >> "%LOG%" 2>&1
)

REM -- Source health check. refresh_roles.py used to catch a dead source, print
REM    [FAIL] and do nothing else, so a source could die silently and stay dead
REM    while it fed /roles, the benchmarker's live row, /salary-data and the
REM    published salary report. This reads the ledger the run above just wrote
REM    and alarms on a newly failed source, sustained failure, sustained
REM    ZERO-YIELD (the case no try/except can see, where a parser runs clean
REM    against changed markup and returns nothing), a board-size cliff and a
REM    slow bleed. Thresholds are backtested against 25 real runs. It is silent
REM    when healthy and exits 0 on findings, so it can never fail this batch.
python "%REPO%\..\jobboard-private\check_source_health.py" >> "%LOG%" 2>&1

git add jobboard/roles.json >> "%LOG%" 2>&1
git commit -m "Daily roles refresh" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [%DATE% %TIME%] nothing to commit -- board unchanged >> "%LOG%"
) else (
  git push >> "%LOG%" 2>&1
  curl -s "https://purge.jsdelivr.net/gh/gaughanadrienne-gif/execops-brief-assets@main/jobboard/roles.json" >nul 2>&1
  echo [%DATE% %TIME%] pushed + purged CDN >> "%LOG%"
)
echo [%DATE% %TIME%] refresh done >> "%LOG%"
endlocal
