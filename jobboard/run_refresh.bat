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
