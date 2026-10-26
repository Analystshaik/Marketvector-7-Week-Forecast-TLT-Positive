@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo TLT Weekly Dashboard - Build and Push
echo ============================================================
echo.

REM ------------------------------------------------------------
REM Step 1 - Build slim cloud database
REM ------------------------------------------------------------
echo ============================================================
echo STEP 1 - Build cloud database
echo ============================================================
echo.

if not exist "BUILD_CLOUD_DATABASE.bat" (
    echo ERROR: BUILD_CLOUD_DATABASE.bat was not found.
    pause
    exit /b 1
)

call BUILD_CLOUD_DATABASE.bat

if errorlevel 1 (
    echo.
    echo ERROR: Cloud database build failed.
    echo GitHub will NOT be updated.
    pause
    exit /b 1
)

if not exist "data\streamlit_market_data.sqlite" (
    echo.
    echo ERROR: data\streamlit_market_data.sqlite was not created.
    echo GitHub will NOT be updated.
    pause
    exit /b 1
)

REM ------------------------------------------------------------
REM Step 2 - Commit, sync, and push
REM ------------------------------------------------------------
echo.
echo ============================================================
echo STEP 2 - Push deployment files to GitHub
echo ============================================================
echo.

if not exist "DAILY_GITHUB_UPDATE.bat" (
    echo ERROR: DAILY_GITHUB_UPDATE.bat was not found.
    pause
    exit /b 1
)

call DAILY_GITHUB_UPDATE.bat

if errorlevel 1 (
    exit /b 1
)

endlocal
