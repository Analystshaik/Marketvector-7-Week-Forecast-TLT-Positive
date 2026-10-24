from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, Iterable, Optional

import pandas as pd
import yaml


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def connect(db_path: str) -> sqlite3.Connection:
    p = Path(db_path)
    if not p.exists():
        raise FileNotFoundError(
            f"SQLite database not found: {db_path}\n"
            f"Update database.path in config.yaml."
        )
    con = sqlite3.connect(str(p))
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    return con


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


def table_columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in con.execute(f'PRAGMA table_info("{table}")').fetchall()]


def normalize_date_series(s: pd.Series) -> pd.Series:
    # Handles YYYYMMDD integers/strings, ISO dates, and datetime-like values.
    raw = s.astype(str).str.strip()
    compact = raw.str.replace(r"\.0$", "", regex=True)
    is_yyyymmdd = compact.str.fullmatch(r"\d{8}")
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    if is_yyyymmdd.any():
        out.loc[is_yyyymmdd] = pd.to_datetime(
            compact.loc[is_yyyymmdd], format="%Y%m%d", errors="coerce"
        )
    if (~is_yyyymmdd).any():
        out.loc[~is_yyyymmdd] = pd.to_datetime(
            raw.loc[~is_yyyymmdd], errors="coerce"
        )
    return out


def load_daily_bars(cfg: dict) -> pd.DataFrame:
    db_cfg = cfg["database"]
    c = cfg["columns"]
    table = db_cfg["source_table"]

    con = connect(db_cfg["path"])
    try:
        if not table_exists(con, table):
            raise RuntimeError(f"Source table does not exist: {table}")
        existing = set(table_columns(con, table))
        required = {c["symbol"], c["date"], c["close"]}
        missing = required - existing
        if missing:
            raise RuntimeError(
                f"Source table {table} is missing required columns: {sorted(missing)}"
            )

        select_cols = [c["symbol"], c["date"], c["close"]]
        for k in ("open", "high", "low"):
            if c.get(k) in existing and c[k] not in select_cols:
                select_cols.append(c[k])

        quoted = ", ".join(f'"{x}"' for x in select_cols)
        sql = f'SELECT {quoted} FROM "{table}"'
        df = pd.read_sql_query(sql, con)
    finally:
        con.close()

    rename = {
        c["symbol"]: "symbol",
        c["date"]: "bar_date",
        c["close"]: "close",
    }
    for k in ("open", "high", "low"):
        if c.get(k) in df.columns:
            rename[c[k]] = k
    df = df.rename(columns=rename)

    df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
    df["bar_date"] = normalize_date_series(df["bar_date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["symbol", "bar_date", "close"])
    df = df.sort_values(["symbol", "bar_date"]).drop_duplicates(
        ["symbol", "bar_date"], keep="last"
    )

    symbols = cfg.get("analysis", {}).get("symbols") or []
    ref = cfg["analysis"]["reference_symbol"].upper()
    if symbols:
        allowed = {str(x).upper() for x in symbols} | {ref}
        df = df[df["symbol"].isin(allowed)]

    return df


def replace_table(db_path: str, table: str, df: pd.DataFrame) -> None:
    if df is None:
        raise ValueError(f"Cannot write table {table}: DataFrame is None")

    if len(df.columns) == 0:
        raise ValueError(
            f"Cannot write table {table}: DataFrame has zero columns. "
            "The analyzer must return a schema-defined empty DataFrame."
        )

    con = connect(db_path)
    try:
        out = df.copy()
        for col in out.columns:
            if pd.api.types.is_datetime64_any_dtype(out[col]):
                out[col] = out[col].dt.strftime("%Y-%m-%d")
        out.to_sql(table, con, if_exists="replace", index=False)
        con.commit()
    finally:
        con.close()


def append_run_log(db_path: str, row: dict) -> None:
    con = connect(db_path)
    try:
        pd.DataFrame([row]).to_sql(
            "tlt_movement_analysis_runs", con, if_exists="append", index=False
        )
        con.commit()
    finally:
        con.close()


def read_table(db_path: str, table: str) -> pd.DataFrame:
    con = connect(db_path)
    try:
        if not table_exists(con, table):
            return pd.DataFrame()
        return pd.read_sql_query(f'SELECT * FROM "{table}"', con)
    finally:
        con.close()
