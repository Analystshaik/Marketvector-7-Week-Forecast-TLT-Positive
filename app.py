from __future__ import annotations

from pathlib import Path
import pandas as pd
import streamlit as st

from db import load_config, load_daily_bars, read_table
from actionable_engine import (
    aggregate_ohlc,
    classify_tlt_period_state,
    build_actionable_rows_period,
    build_fallback_followers_from_leadlag,
    stock_has_recent_bearish_reversal,
    build_weekly_resistance_snapshot,
    attach_weekly_resistance_target,
)

PAGE_TITLE = "TLT Weekly Actionable Trade Dashboard"
VERSION = "Client Dashboard Weekly v3.6.2"
TIMEFRAME = "WEEKLY"
EXPECTED_TABLE = "tlt_expected_moves_week"
UNIT = "week"
UNIT_PLURAL = "weeks"

st.set_page_config(page_title=PAGE_TITLE, page_icon="📈", layout="wide")
cfg = load_config()
db_path = cfg["database"]["path"]
ref = cfg["analysis"]["reference_symbol"].upper()

st.markdown("""
<style>
.block-container {padding-top:1.6rem;padding-bottom:2rem;max-width:1500px;}
h1 {font-size:2rem !important;margin-bottom:.1rem !important;}
.small-muted {color:#6b7280;font-size:.90rem;}
.state-card {padding:1.15rem 1.35rem;border-radius:14px;border:1px solid rgba(128,128,128,.25);margin:.5rem 0 1.2rem 0;}
.state-active {background:rgba(22,163,74,.10);border-left:7px solid #16a34a;}
.state-hold {background:rgba(220,38,38,.10);border-left:7px solid #dc2626;}
.state-neutral {background:rgba(234,179,8,.10);border-left:7px solid #eab308;}
.state-title {font-size:1.35rem;font-weight:750;margin-bottom:.25rem;}
.state-detail {font-size:.98rem;line-height:1.45;}
.section-title {font-size:1.2rem;font-weight:700;margin-top:.6rem;}
div[data-testid="stMetric"] {border:1px solid rgba(128,128,128,.18);padding:.65rem .8rem;border-radius:10px;}
</style>
""", unsafe_allow_html=True)

def style_client_table(df):
    if df.empty:
        return df
    def row_style(row):
        styles = [""] * len(row)
        idx = {c:i for i,c in enumerate(row.index)}
        action = str(row.get("Action",""))
        signal = str(row.get("Signal",""))
        confidence = str(row.get("Confidence",""))
        if "Action" in idx:
            if action == "ACTIONABLE NOW":
                styles[idx["Action"]] = "background-color: rgba(22,163,74,.22); font-weight:700;"
            elif action == "MOVE IN PROGRESS":
                styles[idx["Action"]] = "background-color: rgba(34,197,94,.14); font-weight:600;"
            elif action.startswith("WATCH"):
                styles[idx["Action"]] = "background-color: rgba(234,179,8,.18); font-weight:600;"
            elif action == "HOLD":
                styles[idx["Action"]] = "background-color: rgba(220,38,38,.20); font-weight:700;"
        if "Signal" in idx:
            if signal in ("Due now","Responding","Responded early"):
                styles[idx["Signal"]] = "background-color: rgba(22,163,74,.14);"
            elif signal == "Approaching":
                styles[idx["Signal"]] = "background-color: rgba(234,179,8,.14);"
        if "MA200 Entry" in idx:
            ma = str(row.get( ""))
            if ma == "TOO FAR ABOVE 200WMA":
                styles[idx["MA200 Entry"]] = "background-color: rgba(220,38,38,.22); font-weight:700;"
            elif ma == "GOOD ENTRY / SHORT SQUEEZE":
                styles[idx["MA200 Entry"]] = "background-color: rgba(22,163,74,.24); font-weight:700;"
            elif ma == "NORMAL":
                styles[idx["MA200 Entry"]] = "background-color: rgba(59,130,246,.10);"
        if "Potential Upside" in idx:
            upside = str(row.get("Potential Upside", ""))
            try:
                val = float(upside.replace("%", "").replace("+", ""))
            except Exception:
                val = None
            if val is not None:
                if val >= 15:
                    styles[idx["Potential Upside"]] = "background-color: rgba(22,163,74,.22); font-weight:700;"
                elif val >= 7.5:
                    styles[idx["Potential Upside"]] = "background-color: rgba(34,197,94,.12); font-weight:600;"
                elif val >= 0:
                    styles[idx["Potential Upside"]] = "background-color: rgba(234,179,8,.12);"
        if "Confidence" in idx:
            if confidence == "STRONG":
                styles[idx["Confidence"]] = "background-color: rgba(22,163,74,.20); font-weight:700;"
            elif confidence == "GOOD":
                styles[idx["Confidence"]] = "background-color: rgba(59,130,246,.14); font-weight:600;"
            else:
                styles[idx["Confidence"]] = "background-color: rgba(234,179,8,.12);"
        return styles
    return df.style.apply(row_style, axis=1)

st.title(PAGE_TITLE)
st.caption(VERSION + " · Expected moves + historical true followers")
st.caption("Overextended stocks are hidden by default. Use the toggle to show them.")

if not Path(db_path).exists():
    st.error(f"Database not found: {db_path}")
    st.stop()

bars = load_daily_bars(cfg)
tlt_daily = bars[bars["symbol"] == ref].copy()
tlt_period = aggregate_ohlc(tlt_daily, TIMEFRAME)
state = classify_tlt_period_state(tlt_period, TIMEFRAME, reversal_lookback=3, swing_lookback=3)
expected = read_table(db_path, EXPECTED_TABLE)

stock_reversals = {}
if not expected.empty and "ticker" in expected.columns:
    for ticker in sorted(set(expected["ticker"].dropna().astype(str).str.upper())):
        sb_daily = bars[bars["symbol"] == ticker].copy()
        sb_period = aggregate_ohlc(sb_daily, TIMEFRAME)
        has_rev, pattern, rev_date = stock_has_recent_bearish_reversal(sb_period, lookback=3)
        stock_reversals[ticker] = {"has_reversal":has_rev,"pattern":pattern,"date":rev_date}

actions = build_actionable_rows_period(expected, state, TIMEFRAME, max_lag=7, stock_reversals=stock_reversals)
# Add historically strong weekly followers that may be missing from the expected-move table.
leadlag_week = read_table(db_path, "tlt_movement_leadlag_week")
fallback = build_fallback_followers_from_leadlag(
    leadlag_week,
    "WEEKLY",
    min_hit_rate=0.40,
    min_score=45.0,
    max_lag=7,
)

if not fallback.empty:
    fb_actions = []
    fb_reversals = []
    for _, r in fallback.iterrows():
        ticker = str(r["ticker"]).upper()
        rev = stock_reversals.get(ticker, {})
        has_rev = bool(rev.get("has_reversal", False))
        if has_rev:
            pattern = rev.get("pattern") or "Bearish reversal"
            d = rev.get("date")
            label = f"{pattern} — {pd.Timestamp(d):%Y-%m-%d}" if d is not None and not pd.isna(d) else pattern
            fb_actions.append("HOLD")
            fb_reversals.append(label)
        else:
            fb_actions.append("WATCH / FOLLOWER")
            fb_reversals.append("")
    fallback["Action"] = fb_actions
    fallback["Stock Reversal"] = fb_reversals

    if actions is None or actions.empty:
        actions = fallback.copy()
    else:
        existing = set(actions["ticker"].astype(str).str.upper())
        add = fallback[~fallback["ticker"].astype(str).str.upper().isin(existing)].copy()
        if not add.empty:
            for c in actions.columns:
                if c not in add.columns:
                    add[c] = pd.NA
            for c in add.columns:
                if c not in actions.columns:
                    actions[c] = pd.NA
            add = add[actions.columns]
            actions = pd.concat([actions, add], ignore_index=True)


# Calculate weekly resistance targets AFTER forecast rows and historical fallback
# followers have been combined, so every displayed ticker gets a target calculation.
weekly_resistance_snapshot = build_weekly_resistance_snapshot(
    bars,
    lookback_weeks=104,
    pivot_left=2,
    pivot_right=2,
)
actions = attach_weekly_resistance_target(actions, weekly_resistance_snapshot)

css_class = "state-active" if state.state=="ACTIVE" else ("state-hold" if state.state=="HOLD" else "state-neutral")
rev_note = ""
if state.reversal_pattern and state.reversal_date is not None:
    rev_note = f"<br><b>Latest reversal:</b> {state.reversal_pattern} ({state.reversal_date:%Y-%m-%d})"

st.markdown(f"""
<div class="state-card {css_class}">
  <div class="state-title">{state.headline}</div>
  <div class="state-detail">{state.detail}{rev_note}</div>
</div>
""", unsafe_allow_html=True)

asof = state.asof_date.strftime("%Y-%m-%d") if state.asof_date is not None else "—"
m1,m2,m3,m4 = st.columns(4)
m1.metric("TLT As Of", asof)
m2.metric("TLT Close", f"{state.close:.2f}" if state.close is not None else "—")
m3.metric("Current Swing", f"{state.swing_return*100:+.2f}%" if state.swing_return is not None else "—")
m4.metric("Actionable Universe", int((actions["Action"]=="ACTIONABLE NOW").sum()) if not actions.empty else 0)

if state.state=="HOLD":
    st.error(f"NEW POSITIVE TLT-FOLLOWER {TIMEFRAME} TRADES ARE ON HOLD.")
elif state.state=="NEUTRAL":
    st.warning(f"TLT is not in a confirmed positive {TIMEFRAME.lower()} swing.")

# Entry-quality visibility control.
show_overextended = st.toggle(
    "Show overextended stocks",
    value=False,
    help="Show stocks currently overextended above their 200-week moving average.",
)

if not show_overextended and actions is not None and not actions.empty and "MA200 Entry" in actions.columns:
    actions = actions[actions["MA200 Entry"] != "TOO FAR ABOVE 200WMA"].copy()

if actions.empty:
    st.info(f"No {TIMEFRAME.lower()} follower signals are currently available in `{EXPECTED_TABLE}`.")
    st.stop()

actions_display = actions.copy()

# Engine keeps the generic internal field name for compatibility.
if "200DMA Distance" in actions_display.columns and "200WMA Distance" not in actions_display.columns:
    actions_display = actions_display.rename(columns={"200DMA Distance": "200WMA Distance"})

display_cols = [
    "ticker",
    "Timing",
    "Expected",
    "Signal",
    "Confidence",
    "Action",
    "Stock Reversal",
    
    "200WMA Distance",
    "Weekly Target",
    "Potential Upside",
    "normal_lag",
]

# Graceful fallback in case an older analysis table has not yet been rebuilt.
for c in display_cols:
    if c not in actions_display.columns:
        actions_display[c] = "—"

display = actions_display[display_cols].copy()
display = display.rename(columns={"ticker":"Symbol"})

def _fill_expected(row):
    val = str(row.get("Expected", "") or "").strip()
    if val and val.lower() not in ("nan", "none"):
        return val
    lag = int(row.get("normal_lag", 0) or 0)
    if state.asof_date is None:
        return "Watch"
    projected = pd.Timestamp(state.asof_date) + pd.Timedelta(weeks=lag)
    if lag == 0:
        return f"This week — {projected:%Y-%m-%d}"
    unit = "week" if lag == 1 else "weeks"
    return f"in {lag} {unit} — {projected:%Y-%m-%d}"

display["Expected"] = display.apply(_fill_expected, axis=1)

now = display[display["Action"]=="ACTIONABLE NOW"].copy()
st.markdown('<div class="section-title">Actionable Now</div>', unsafe_allow_html=True)
if now.empty:
    st.caption("No stocks are due for a new move right now.")
else:
    st.dataframe(style_client_table(now.drop(columns=["normal_lag"])), width="stretch", hide_index=True, row_height=34)

def bucket(title, sub, mask):
    st.markdown(f"### {title}")
    st.caption(sub)
    d = display[mask].copy()
    if d.empty:
        st.caption("No current candidates.")
        return
    d = d.sort_values(["Action","Symbol"])
    cols = ["Symbol","Expected","Signal","Confidence","200WMA Distance","Weekly Target","Potential Upside","Action"]
    if d["normal_lag"].min() >= 2:
        cols.append("Stock Reversal")
    safe_cols = [c for c in cols if c in d.columns]
    st.dataframe(style_client_table(d[safe_cols]), width="stretch", hide_index=True, row_height=34)

bucket("In Sync", f"Normal response: same {UNIT}", display["normal_lag"]==0)
bucket("Near-Term Followers", f"Normal response: 1–2 {UNIT_PLURAL} after TLT", display["normal_lag"].between(1,2))
bucket("Mid-Lag Followers", f"Normal response: 3–4 {UNIT_PLURAL} after TLT", display["normal_lag"].between(3,4))
bucket("Extended Lag Followers", f"Normal response: 5–7 {UNIT_PLURAL} after TLT", display["normal_lag"].between(5,7))

st.markdown('<div class="section-title">Current TLT Follower Watch List</div>', unsafe_allow_html=True)
watch = display.sort_values(["normal_lag","Symbol"]).drop(columns=["normal_lag"])
st.dataframe(style_client_table(watch), width="stretch", hide_index=True, row_height=34)


# Weekly 200-week moving-average entry overlay:
# Red "TOO FAR ABOVE 200WMA" = overextended; avoid chasing.
# Green "GOOD ENTRY / SHORT SQUEEZE" = materially below 200DMA; potential squeeze/reversion entry.
