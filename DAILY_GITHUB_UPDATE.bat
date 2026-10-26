@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo TLT Weekly Dashboard - Daily GitHub Update
echo ============================================================
echo.

REM ------------------------------------------------------------
REM Verify Git repository
REM ------------------------------------------------------------
if not exist ".git" (
    echo ERROR: This folder is not a Git repository.
    echo Run this BAT file from the project root folder.
    pause
    exit /b 1
)

echo Git remote:
git remote -v
echo.

REM ------------------------------------------------------------
REM Initialize Git LFS only.
REM Do NOT run "git lfs track" every day because it can modify
REM .gitattributes and make the working tree dirty.
REM ------------------------------------------------------------
echo Initializing Git LFS...
git lfs install

if errorlevel 1 (
    echo.
    echo ERROR: Git LFS initialization failed.
    pause
    exit /b 1
)

REM ------------------------------------------------------------
REM Verify the cloud database exists
REM ------------------------------------------------------------
if not exist "data\streamlit_market_data.sqlite" (
    echo.
    echo ERROR: data\streamlit_market_data.sqlite was not found.
    echo Run BUILD_CLOUD_DATABASE.bat first.
    pause
    exit /b 1
)

REM ------------------------------------------------------------
REM Stage only known deployment files
REM ------------------------------------------------------------
echo.
echo Staging deployment files...
echo.

if exist "app.py" git add "app.py"
if exist "actionable_engine.py" git add "actionable_engine.py"
if exist "db.py" git add "db.py"
if exist "config.yaml" git add "config.yaml"
if exist "requirements.txt" git add "requirements.txt"
if exist "runtime.txt" git add "runtime.txt"
if exist "build_cloud_database.py" git add "build_cloud_database.py"
if exist "BUILD_CLOUD_DATABASE.bat" git add "BUILD_CLOUD_DATABASE.bat"
if exist "DAILY_GITHUB_UPDATE.bat" git add "DAILY_GITHUB_UPDATE.bat"
if exist "BUILD_AND_PUSH_DAILY.bat" git add "BUILD_AND_PUSH_DAILY.bat"
if exist "README.md" git add "README.md"
if exist ".gitignore" git add ".gitignore"
if exist ".gitattributes" git add ".gitattributes"
git add "data\streamlit_market_data.sqlite"

echo.
echo ============================================================
echo STAGED CHANGES
echo ============================================================
git status --short
echo.

REM ------------------------------------------------------------
REM Commit local changes BEFORE pull/rebase.
REM This prevents "cannot pull with rebase: unstaged changes".
REM ------------------------------------------------------------
git diff --cached --quiet

if errorlevel 1 (
    echo Creating local commit...
    git commit -m "Daily cloud refresh"

    if errorlevel 1 (
        echo.
        echo ERROR: Git commit failed.
        pause
        exit /b 1
    )
) else (
    echo No local deployment changes to commit.
)

REM ------------------------------------------------------------
REM Now the working tree should be clean.
REM Pull/rebase any remote changes.
REM ------------------------------------------------------------
echo.
echo ============================================================
echo PULLING LATEST GITHUB CHANGES
echo ============================================================
echo.

git pull --rebase origin main

if errorlevel 1 (
    echo.
    echo ============================================================
    echo ERROR: Git pull/rebase failed
    echo ============================================================
    echo.
    echo A remote/local conflict may exist.
    echo.
    echo To cancel the rebase:
    echo     git rebase --abort
    echo.
    echo Then review:
    echo     git status
    echo.
    pause
    exit /b 1
)

REM ------------------------------------------------------------
REM Push
REM ------------------------------------------------------------
echo.
echo ============================================================
echo PUSHING TO GITHUB
echo ============================================================
echo.

git push origin main

if errorlevel 1 (
    echo.
    echo ============================================================
    echo ERROR: GitHub push failed
    echo ============================================================
    echo.
    echo Run:
    echo     git status
    echo.
    echo and review the message above.
    pause
    exit /b 1
)

REM ------------------------------------------------------------
REM Final status
REM ------------------------------------------------------------
echo.
echo ============================================================
echo SUCCESS
echo ============================================================
echo.
echo GitHub has been updated successfully.
echo Streamlit Cloud should detect the new commit and redeploy.
echo.

echo Git LFS files:
git lfs ls-files
echo.

echo Final Git status:
git status --short
echo.

pause
endlocal
