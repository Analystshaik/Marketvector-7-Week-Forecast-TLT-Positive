# TLT Weekly Actionable Trade Dashboard

This is the GitHub + Streamlit Community Cloud deployment package.

Latest Weekly features included:
- Weekly true-follower fallback
- 0-7 week follower windows
- 200-week SMA distance
- Overextended stocks hidden by default with toggle to show
- MA200 Entry column hidden
- Weekly resistance target
- Potential upside percentage


## 1. Build the slim cloud database

Double-click:

`BUILD_CLOUD_DATABASE.bat`

It reads:

`C:\MarketVector\Database\ibkr_market_data.sqlite`

and creates:

`data\streamlit_market_data.sqlite`

The extractor copies only the symbols and tables required by this dashboard, plus 8 years of filtered OHLC history. Eight years comfortably covers the Weekly 200-week SMA and resistance calculations.

## 2. Verify the database

Confirm this file exists:

`data\streamlit_market_data.sqlite`

## 3. Git LFS

From this folder:

```bash
git init
git lfs install
git lfs track "*.sqlite"
git add .gitattributes
git add .
git commit -m "Initial Daily dashboard cloud deployment"
git branch -M main
```

Verify:

```bash
git lfs ls-files
```

You should see:

`data/streamlit_market_data.sqlite`

## 4. GitHub

For a new repository:

```bash
git init
git branch -M main
git remote add origin https://github.com/Analystshaik/Marketvector-7-Week-Forecast-TLT-Positive.git
git push -u origin main
```

If the repository already exists and contains files, reconcile it before pushing.

## 5. Streamlit Community Cloud

- Repository: your GitHub repo
- Branch: `main`
- Main file path: `app.py`

The cloud database path is already configured as:

`data/streamlit_market_data.sqlite`

---

# 6. Daily GitHub Update Workflow

Use this section for the normal day-to-day refresh of the cloud deployment.

## Recommended daily sequence

1. Refresh the local core database first.
2. Run `BUILD_CLOUD_DATABASE.bat` to rebuild `data\streamlit_market_data.sqlite`.
3. Run `DAILY_GITHUB_UPDATE.bat`.
4. The script pulls the latest remote changes, stages only the known deployment files, commits them, and pushes to `main`.
5. Streamlit Community Cloud should then detect the new commit and redeploy.

## Files normally eligible for a daily push

The update script intentionally limits itself to these deployment files when they exist:

- `app.py`
- `actionable_engine.py`
- `db.py`
- `config.yaml`
- `requirements.txt`
- `runtime.txt`
- `build_cloud_database.py`
- `BUILD_CLOUD_DATABASE.bat`
- `README.md`
- `.gitignore`
- `.gitattributes`
- `data\streamlit_market_data.sqlite`

This is safer than routinely using `git add .`, because it reduces the chance of pushing local backups, logs, caches, virtual environments, unrelated databases, or temporary files.

## Important Git LFS rule

Always run Git/Git LFS commands from the project root folder containing `.git`.

The cloud database should remain under Git LFS:

```bash
git lfs install
git lfs track "*.sqlite"
git lfs ls-files
```

You should see:

`data/streamlit_market_data.sqlite`

## One-click daily update

Place `DAILY_GITHUB_UPDATE.bat` in the project root next to `app.py`.

It will:

- verify that it is running from a Git repository;
- initialize Git LFS;
- pull/rebase from `origin/main`;
- stage only the known deployment files;
- skip the commit when nothing changed;
- create a daily refresh commit;
- push to GitHub;
- show the Git LFS files at the end.

## Fully automated build + push

For the simplest daily workflow, use `BUILD_AND_PUSH_DAILY.bat`.

That script first runs `BUILD_CLOUD_DATABASE.bat`. If the cloud database build fails, it stops and does **not** push anything. If the build succeeds, it calls `DAILY_GITHUB_UPDATE.bat`.

Daily usage then becomes:

```text
1. Update the core market database.
2. Double-click BUILD_AND_PUSH_DAILY.bat.
3. Verify the console reports SUCCESS.
```

## Safety notes

- Do not push `C:\MarketVector\Database\ibkr_market_data.sqlite` to GitHub.
- Push only the slim cloud database: `data\streamlit_market_data.sqlite`.
- Keep SQLite files under Git LFS.
- If `git pull --rebase` reports a conflict, resolve it before pushing.
- Avoid force-pushing as part of the normal daily workflow.
- Periodically verify the GitHub repository and Streamlit Cloud are using branch `main`.

