from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
import pandas as pd

DEFAULT_SOURCE_DB = r"C:\MarketVector\Database\ibkr_market_data.sqlite"
DEFAULT_OUTPUT_DB = r"data\streamlit_market_data.sqlite"
SOURCE_TABLE = "relationship_bars_day"

DAILY_TABLES = [
    "tlt_expected_moves_day",
    "tlt_movement_leadlag_day",
    "tlt_movement_events_day",
]

WEEKLY_TABLES = [
    "tlt_expected_moves_week",
    "tlt_movement_leadlag_week",
    "tlt_movement_events_week",
]


def table_exists(con, table):
    return bool(con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    ).fetchone())


def get_columns(con, table):
    return [r[1] for r in con.execute(f'PRAGMA table_info("{table}")').fetchall()]


def copy_table(src, dst, table):
    if not table_exists(src, table):
        print(f"[WARN] Missing table: {table}")
        return 0
    df = pd.read_sql_query(f'SELECT * FROM "{table}"', src)
    df.to_sql(table, dst, if_exists="replace", index=False)
    print(f"[OK] {table}: {len(df):,} rows")
    return len(df)


def get_dashboard_symbols(src, include_daily, include_weekly):
    symbols = {"TLT"}
    tables = []

    if include_daily:
        tables += ["tlt_expected_moves_day", "tlt_movement_leadlag_day"]
    if include_weekly:
        tables += ["tlt_expected_moves_week", "tlt_movement_leadlag_week"]

    for table in tables:
        if not table_exists(src, table):
            continue

        cols = get_columns(src, table)
        key = "ticker" if "ticker" in cols else ("symbol" if "symbol" in cols else None)
        if not key:
            continue

        rows = src.execute(
            f'SELECT DISTINCT "{key}" FROM "{table}" WHERE "{key}" IS NOT NULL'
        ).fetchall()

        for row in rows:
            s = str(row[0]).strip().upper()
            if s:
                symbols.add(s)

    return sorted(symbols)


def copy_filtered_bars(src, dst, symbols, history_years=8):
    if not table_exists(src, SOURCE_TABLE):
        raise RuntimeError(f"Required table missing: {SOURCE_TABLE}")

    cols = get_columns(src, SOURCE_TABLE)
    symbol_col = "symbol" if "symbol" in cols else "ticker"
    date_col = "bar_date" if "bar_date" in cols else "date"

    placeholders = ",".join(["?"] * len(symbols))
    sql = (
        f'SELECT * FROM "{SOURCE_TABLE}" '
        f'WHERE UPPER(TRIM("{symbol_col}")) IN ({placeholders})'
    )

    df = pd.read_sql_query(sql, src, params=symbols)

    if not df.empty:
        raw = df[date_col].astype(str).str.replace(r"\.0$", "", regex=True)
        parsed = pd.to_datetime(raw, format="%Y%m%d", errors="coerce")
        bad = parsed.isna()
        if bad.any():
            parsed.loc[bad] = pd.to_datetime(raw.loc[bad], errors="coerce")

        if parsed.notna().any():
            cutoff = parsed.max() - pd.DateOffset(years=int(history_years))
            df = df.loc[parsed >= cutoff].copy()

    df.to_sql(SOURCE_TABLE, dst, if_exists="replace", index=False)

    dst.execute(
        f'CREATE INDEX IF NOT EXISTS idx_relbars_symbol '
        f'ON "{SOURCE_TABLE}"("{symbol_col}")'
    )
    dst.execute(
        f'CREATE INDEX IF NOT EXISTS idx_relbars_symbol_date '
        f'ON "{SOURCE_TABLE}"("{symbol_col}", "{date_col}")'
    )

    print(
        f"[OK] {SOURCE_TABLE}: {len(df):,} rows "
        f"for {len(symbols):,} symbols"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Build a slim SQLite database for the TLT Streamlit dashboards."
    )
    parser.add_argument("--source", default=DEFAULT_SOURCE_DB)
    parser.add_argument("--output", default=DEFAULT_OUTPUT_DB)
    parser.add_argument("--daily", action="store_true")
    parser.add_argument("--weekly", action="store_true")
    parser.add_argument("--history-years", type=int, default=8)
    args = parser.parse_args()

    if not args.daily and not args.weekly:
        args.daily = True
        args.weekly = True

    source = Path(args.source)
    output = Path(args.output)

    if not source.exists():
        raise FileNotFoundError(f"Source database not found: {source}")

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    print(f"Source: {source}")
    print(f"Output: {output}")

    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(output))

    try:
        symbols = get_dashboard_symbols(src, args.daily, args.weekly)
        print(f"Required symbols: {len(symbols):,}")

        copy_filtered_bars(
            src,
            dst,
            symbols=symbols,
            history_years=args.history_years,
        )

        if args.daily:
            for table in DAILY_TABLES:
                copy_table(src, dst, table)

        if args.weekly:
            for table in WEEKLY_TABLES:
                copy_table(src, dst, table)

        dst.commit()
        dst.execute("VACUUM")
        dst.commit()

    finally:
        src.close()
        dst.close()

    size_mb = output.stat().st_size / (1024 * 1024)
    print()
    print("Cloud database created successfully.")
    print(f"File: {output}")
    print(f"Size: {size_mb:,.1f} MB")


if __name__ == "__main__":
    main()
