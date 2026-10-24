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
