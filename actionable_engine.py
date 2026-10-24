from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class TLTState:
    state: str
    headline: str
    detail: str
    reversal_pattern: str | None
    reversal_date: pd.Timestamp | None
    asof_date: pd.Timestamp | None
    close: float | None
    swing_return: float | None


def _body(row):
    return abs(float(row["close"]) - float(row["open"]))


def _range(row):
    return max(float(row["high"]) - float(row["low"]), 1e-9)


def _upper_wick(row):
    return float(row["high"]) - max(float(row["open"]), float(row["close"]))


def _lower_wick(row):
    return min(float(row["open"]), float(row["close"])) - float(row["low"])


def _bull(row):
    return float(row["close"]) > float(row["open"])


def _bear(row):
    return float(row["close"]) < float(row["open"])


def bearish_engulfing(prev, cur):
    return (
        _bull(prev) and _bear(cur)
        and float(cur["open"]) >= float(prev["close"])
        and float(cur["close"]) <= float(prev["open"])
        and _body(cur) >= _body(prev)
    )


def shooting_star(prev, cur):
    body = max(_body(cur), 1e-9)
    rng = _range(cur)
    return (
        _upper_wick(cur) >= 2.0 * body
        and _lower_wick(cur) <= 0.75 * body
        and body / rng <= 0.40
        and float(cur["high"]) >= float(prev["high"])
    )


def dark_cloud_cover(prev, cur):
    if not (_bull(prev) and _bear(cur)):
        return False
    midpoint = (float(prev["open"]) + float(prev["close"])) / 2.0
    return (
        float(cur["open"]) >= float(prev["close"]) * 0.997
        and float(cur["close"]) < midpoint
        and float(cur["close"]) > float(prev["open"])
    )


def bearish_harami(prev, cur):
    return (
        _bull(prev) and _bear(cur)
        and float(cur["open"]) < float(prev["close"])
        and float(cur["close"]) > float(prev["open"])
        and _body(cur) <= _body(prev) * 0.75
    )


def evening_star(a, b, c):
    body_a = max(_body(a), 1e-9)
    body_b = _body(b)
    midpoint_a = (float(a["open"]) + float(a["close"])) / 2.0
    return (
        _bull(a)
        and body_b <= body_a * 0.60
        and _bear(c)
        and float(c["close"]) < midpoint_a
        and float(b["high"]) >= float(a["high"])
    )


def detect_bearish_reversals(tlt: pd.DataFrame, lookback: int = 3):
    if len(tlt) < 3:
        return []

    x = tlt.sort_values("bar_date").reset_index(drop=True).copy()
    results = []
    start = max(2, len(x) - max(lookback, 1))

    for i in range(start, len(x)):
        a = x.iloc[i - 2]
        p = x.iloc[i - 1]
        c = x.iloc[i]

        # Reversal patterns are only meaningful if TLT was rising into them.
        pre_start = max(0, i - 5)
        pre = x.iloc[pre_start:i]
        rising_into_signal = (
            len(pre) >= 2
            and float(pre.iloc[-1]["close"]) > float(pre.iloc[0]["close"])
        )
        if not rising_into_signal:
            continue

        patterns = []
        if bearish_engulfing(p, c):
            patterns.append("Bearish Engulfing")
        if shooting_star(p, c):
            patterns.append("Shooting Star")
        if dark_cloud_cover(p, c):
            patterns.append("Dark Cloud Cover")
        if bearish_harami(p, c):
            patterns.append("Bearish Harami")
        if evening_star(a, p, c):
            patterns.append("Evening Star")

        for pattern in patterns:
            results.append({
                "date": pd.Timestamp(c["bar_date"]),
                "pattern": pattern,
                "close": float(c["close"]),
            })
    return results


def classify_tlt_daily_state(tlt: pd.DataFrame, reversal_lookback: int = 3,
                             swing_lookback: int = 5) -> TLTState:
    if tlt is None or tlt.empty:
        return TLTState(
            "NO_DATA",
            "TLT status unavailable",
            "No TLT daily bars were found in the configured database.",
            None, None, None, None, None
        )

    x = tlt.sort_values("bar_date").reset_index(drop=True).copy()
    for c in ["open", "high", "low", "close"]:
        x[c] = pd.to_numeric(x[c], errors="coerce")
    x = x.dropna(subset=["bar_date", "close"])

    if len(x) < 6:
        last = x.iloc[-1]
        return TLTState(
            "NEUTRAL",
            "TLT daily state is not yet confirmed",
            "More daily history is required for the swing/reversal check.",
            None, None, pd.Timestamp(last["bar_date"]), float(last["close"]), None
        )

    last = x.iloc[-1]
    asof = pd.Timestamp(last["bar_date"])
    close = float(last["close"])

    lookback = min(int(swing_lookback), len(x) - 1)
    swing_return = close / float(x.iloc[-1 - lookback]["close"]) - 1.0

    # Short swing confirmation: positive 5-session movement plus upward short slope.
    x["ema5"] = x["close"].ewm(span=5, adjust=False).mean()
    ema_rising = float(x.iloc[-1]["ema5"]) > float(x.iloc[-3]["ema5"])
    upward_swing = swing_return > 0 and ema_rising

    reversals = detect_bearish_reversals(x, reversal_lookback)
    latest_rev = reversals[-1] if reversals else None

    # A recent bearish reversal overrides the positive setup.
    if latest_rev is not None:
        rev_date = pd.Timestamp(latest_rev["date"])
        bars_since = int((x["bar_date"] > rev_date).sum())

        # Require a fresh positive swing after the reversal before reactivating.
        post = x[x["bar_date"] > rev_date]
        fresh_positive_swing = (
            len(post) >= 3
            and float(post.iloc[-1]["close"]) > float(post.iloc[0]["close"])
            and float(post.iloc[-1]["ema5"]) > float(post.iloc[0]["ema5"])
        )

        if not fresh_positive_swing:
            return TLTState(
                "HOLD",
                "TLT positive trade is ON HOLD",
                f"{latest_rev['pattern']} detected on {rev_date:%Y-%m-%d}. "
                "No fresh confirmed daily upswing has re-established the positive setup yet.",
                latest_rev["pattern"], rev_date, asof, close, swing_return
            )

    if upward_swing:
        return TLTState(
            "ACTIVE",
            "TLT is in a DAILY UPWARD SWING",
            "No active confirmed bearish daily reversal is blocking the positive setup. "
            "Stocks moving in sync or within their normal 1–7 day lag window are actionable.",
            None, None, asof, close, swing_return
        )

    return TLTState(
        "NEUTRAL",
        "TLT positive setup is WAITING",
        "TLT does not currently meet the short daily upswing condition. "
        "New positive follower trades should wait for the next confirmed upswing.",
        None, None, asof, close, swing_return
    )


def confidence_label(score, hit_rate):
    score = float(score) if pd.notna(score) else 0.0
    hit_rate = float(hit_rate) if pd.notna(hit_rate) else 0.0
    if score >= 55 and hit_rate >= 0.50:
        return "STRONG"
    if score >= 48 and hit_rate >= 0.43:
        return "GOOD"
    return "WATCH"


def timing_label(lag):
    lag = int(lag)
    if lag == 0:
        return "IN SYNC"
    if 1 <= lag <= 3:
        return f"{lag}-DAY LAG"
    if 4 <= lag <= 7:
        return f"{lag}-DAY LAG"
    if 8 <= lag <= 10:
        return f"{lag}-DAY LAG"
    return f"{lag}-DAY LAG"


def action_label(row, tlt_state, stock_reversal=False):
    """
    Client-facing trade-state logic.

    Lag 0-3:
      Respect the overall TLT state. If TLT is on hold, these near-term setups are HOLD.

    Lag 4-15:
      Do NOT automatically mark HOLD just because TLT is currently on hold.
      These later-response setups remain WATCH unless the individual stock itself
      shows a bearish daily candlestick reversal.
    """
    status = str(row.get("status", "")).upper()
    lag = int(row.get("normal_lag", 0))

    if stock_reversal:
        return "HOLD"

    if lag <= 3:
        if tlt_state != "ACTIVE":
            return "HOLD"

        if status == "DUE":
            return "ACTIONABLE NOW"
        if status == "UPCOMING":
            return "WATCH / APPROACHING"
        if status in ("CONFIRMED", "EARLY_RESPONSE"):
            return "MOVE IN PROGRESS"
        if lag == 0:
            return "ACTIONABLE NOW"
        return "WATCH"

    # Mid-lag and extended-lag stocks remain alive unless their own chart reverses.
    if status == "DUE":
        return "WATCH / DUE"
    if status == "UPCOMING":
        return "WATCH / APPROACHING"
    if status in ("CONFIRMED", "EARLY_RESPONSE"):
        return "MOVE IN PROGRESS"
    return "WATCH"


def stock_has_recent_bearish_reversal(stock_bars: pd.DataFrame, lookback: int = 3):
    """
    Returns (bool, pattern, date) for the most recent bearish candlestick reversal
    on an individual stock.
    """
    if stock_bars is None or stock_bars.empty:
        return False, None, None

    needed = {"bar_date", "open", "high", "low", "close"}
    if not needed.issubset(stock_bars.columns):
        return False, None, None

    x = stock_bars.sort_values("bar_date").copy()
    revs = detect_bearish_reversals(x, lookback=lookback)
    if not revs:
        return False, None, None

    latest = revs[-1]
    return True, latest["pattern"], pd.Timestamp(latest["date"])


def add_trading_days(start_date, n):
    """
    Add N weekday trading days to start_date.
    Skips Saturday and Sunday.
    """
    if start_date is None or pd.isna(start_date):
        return pd.NaT

    d = pd.Timestamp(start_date).normalize()
    remaining = int(max(n, 0))

    while remaining > 0:
        d += pd.Timedelta(days=1)
        if d.weekday() < 5:
            remaining -= 1

    return d

def build_actionable_rows(expected: pd.DataFrame, state: TLTState, max_lag: int = 15, latest_market_date=None, stock_reversals=None):
    if expected is None or expected.empty:
        return pd.DataFrame()

    x = expected.copy()
    x["event_date"] = pd.to_datetime(x["event_date"], errors="coerce")
    x["expected_date"] = pd.to_datetime(x["expected_date"], errors="coerce")
    x["actual_response_date"] = pd.to_datetime(
        x.get("actual_response_date"), errors="coerce"
    )

    x = x[x["normal_lag"].between(0, max_lag)].copy()
    x = x[x["status"].isin(["DUE", "UPCOMING", "CONFIRMED", "EARLY_RESPONSE"])]

    if x.empty:
        return x

    # For a client-facing view keep only the most recent signal per ticker/lag,
    # then the best current row per ticker.
    x = x.sort_values(
        ["event_date", "score", "hit_rate"],
        ascending=[False, False, False]
    )
    x = x.drop_duplicates(["ticker", "normal_lag"], keep="first")

    priority = {"DUE": 0, "UPCOMING": 1, "CONFIRMED": 2, "EARLY_RESPONSE": 3}
    x["status_rank"] = x["status"].map(priority).fillna(9)
    x = x.sort_values(
        ["ticker", "status_rank", "score", "event_date"],
        ascending=[True, True, False, False]
    ).drop_duplicates("ticker", keep="first")

    x["Timing"] = x["normal_lag"].map(timing_label)
    x["Confidence"] = [
        confidence_label(s, h) for s, h in zip(x["score"], x["hit_rate"])
    ]
    stock_reversals = stock_reversals or {}

    actions = []
    reversal_labels = []
    for _, r in x.iterrows():
        ticker = str(r.get("ticker", "")).upper()
        rev = stock_reversals.get(ticker, {})
        has_rev = bool(rev.get("has_reversal", False))
        actions.append(action_label(r, state.state, stock_reversal=has_rev))

        if has_rev:
            pattern = rev.get("pattern") or "Bearish reversal"
            d = rev.get("date")
            if d is not None and not pd.isna(d):
                reversal_labels.append(f"{pattern} — {pd.Timestamp(d):%Y-%m-%d}")
            else:
                reversal_labels.append(pattern)
        else:
            reversal_labels.append("")

    x["Action"] = actions
    x["Stock Reversal"] = reversal_labels

    if "ma200_entry_label" in x.columns:
        x["MA200 Entry"] = x["ma200_entry_label"].map({
            "OVEREXTENDED_AVOID": "TOO FAR ABOVE 200WMA",
            "SHORT_SQUEEZE_CANDIDATE": "GOOD ENTRY / SHORT SQUEEZE",
            "NORMAL": "NORMAL",
            "INSUFFICIENT_HISTORY": "NO RATING",
        }).fillna("NO RATING")
    else:
        x["MA200 Entry"] = "NO RATING"

    if "pct_from_sma200" in x.columns:
        x["200DMA Distance"] = pd.to_numeric(
            x["pct_from_sma200"], errors="coerce"
        ).map(lambda v: f"{v*100:+.1f}%" if pd.notna(v) else "—")
    else:
        x["200DMA Distance"] = "—"

    if "ma200_entry_label" in x.columns:
        x["MA200 Entry"] = x["ma200_entry_label"].map({
            "OVEREXTENDED_AVOID": "TOO FAR ABOVE 200WMA",
            "SHORT_SQUEEZE_CANDIDATE": "GOOD ENTRY / SHORT SQUEEZE",
            "NORMAL": "NORMAL",
            "INSUFFICIENT_HISTORY": "NO RATING",
        }).fillna("NO RATING")
    else:
        x["MA200 Entry"] = "NO RATING"

    if "pct_from_sma200" in x.columns:
        x["200DMA Distance"] = pd.to_numeric(
            x["pct_from_sma200"], errors="coerce"
        ).map(lambda v: f"{v*100:+.1f}%" if pd.notna(v) else "—")
    else:
        x["200DMA Distance"] = "—"

    if latest_market_date is None or pd.isna(latest_market_date):
        if state.asof_date is not None:
            latest_market_date = pd.Timestamp(state.asof_date)
        elif "event_date" in x.columns and x["event_date"].notna().any():
            latest_market_date = x["event_date"].max()
        else:
            latest_market_date = pd.NaT
    else:
        latest_market_date = pd.Timestamp(latest_market_date)

    def expected_display(r):
        status = str(r.get("status", "")).upper()

        if status in ("CONFIRMED", "EARLY_RESPONSE"):
            d = r.get("actual_response_date")
            if pd.notna(d):
                return f"Responded — {pd.Timestamp(d):%Y-%m-%d}"
            return "Move in progress"

        bars = int(r.get("bars_until_expected", 0) or 0)
        d = r.get("expected_date")

        if bars <= 0:
            if pd.notna(d):
                return f"Today — {pd.Timestamp(d):%Y-%m-%d}"
            if pd.notna(latest_market_date):
                return f"Today — {pd.Timestamp(latest_market_date):%Y-%m-%d}"
            return "Today"

        # Prefer a stored expected date only if it is actually in the future.
        if pd.notna(d) and pd.notna(latest_market_date) and pd.Timestamp(d) > pd.Timestamp(latest_market_date):
            projected = pd.Timestamp(d)
        else:
            projected = add_trading_days(latest_market_date, bars)

        day_word = "day" if bars == 1 else "days"
        if pd.notna(projected):
            return f"{bars} trading {day_word} — {projected:%Y-%m-%d}"
        return f"{bars} trading {day_word}"

    x["Expected"] = [expected_display(r) for _, r in x.iterrows()]
    x["Signal"] = x["status"].map({
        "DUE": "Due now",
        "UPCOMING": "Approaching",
        "CONFIRMED": "Responding",
        "EARLY_RESPONSE": "Responded early",
    }).fillna(x["status"])

    return x


def aggregate_ohlc(daily_bars: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    x = daily_bars.copy()
    x["bar_date"] = pd.to_datetime(x["bar_date"], errors="coerce")
    x = x.dropna(subset=["bar_date"]).sort_values("bar_date")
    if timeframe.upper() == "WEEKLY":
        rule = "W-FRI"
    elif timeframe.upper() == "MONTHLY":
        rule = "ME"
    else:
        return x
    return (
        x.set_index("bar_date")
        .resample(rule)
        .agg({"open":"first","high":"max","low":"min","close":"last"})
        .dropna()
        .reset_index()
    )


def classify_tlt_period_state(period_bars: pd.DataFrame, timeframe: str,
                              reversal_lookback: int = 3,
                              swing_lookback: int = 3) -> TLTState:
    tf = timeframe.upper()
    if period_bars is None or period_bars.empty:
        return TLTState("NO_DATA", f"TLT {tf.lower()} status unavailable",
                        f"No TLT {tf.lower()} bars were found.",
                        None, None, None, None, None)

    x = period_bars.sort_values("bar_date").reset_index(drop=True).copy()
    for c in ["open","high","low","close"]:
        x[c] = pd.to_numeric(x[c], errors="coerce")
    x = x.dropna(subset=["bar_date","close"])

    if len(x) < 5:
        last = x.iloc[-1]
        return TLTState("NEUTRAL", f"TLT {tf.lower()} state is not yet confirmed",
                        "More history is required for the swing/reversal check.",
                        None, None, pd.Timestamp(last["bar_date"]),
                        float(last["close"]), None)

    last = x.iloc[-1]
    asof = pd.Timestamp(last["bar_date"])
    close = float(last["close"])
    lookback = min(int(swing_lookback), len(x)-1)
    swing_return = close / float(x.iloc[-1-lookback]["close"]) - 1.0

    x["ema3"] = x["close"].ewm(span=3, adjust=False).mean()
    upward_swing = swing_return > 0 and float(x.iloc[-1]["ema3"]) > float(x.iloc[-2]["ema3"])

    reversals = detect_bearish_reversals(x, reversal_lookback)
    latest_rev = reversals[-1] if reversals else None

    if latest_rev is not None:
        rev_date = pd.Timestamp(latest_rev["date"])
        post = x[x["bar_date"] > rev_date]
        fresh_positive_swing = (
            len(post) >= 2
            and float(post.iloc[-1]["close"]) > float(post.iloc[0]["close"])
            and float(post.iloc[-1]["ema3"]) > float(post.iloc[0]["ema3"])
        )
        if not fresh_positive_swing:
            return TLTState(
                "HOLD",
                f"TLT positive {tf.lower()} trade is ON HOLD",
                f"{latest_rev['pattern']} detected on {rev_date:%Y-%m-%d}. "
                f"No fresh confirmed {tf.lower()} upswing has re-established the positive setup yet.",
                latest_rev["pattern"], rev_date, asof, close, swing_return
            )

    if upward_swing:
        return TLTState(
            "ACTIVE",
            f"TLT is in a {tf} UPWARD SWING",
            f"No active confirmed bearish {tf.lower()} reversal is blocking the positive setup.",
            None, None, asof, close, swing_return
        )

    return TLTState(
        "NEUTRAL",
        f"TLT positive {tf.lower()} setup is WAITING",
        f"TLT does not currently meet the short {tf.lower()} upswing condition.",
        None, None, asof, close, swing_return
    )


def add_calendar_weeks(start_date, n):
    if start_date is None or pd.isna(start_date):
        return pd.NaT
    return pd.Timestamp(start_date) + pd.Timedelta(weeks=int(max(n,0)))


def add_calendar_months(start_date, n):
    if start_date is None or pd.isna(start_date):
        return pd.NaT
    return pd.Timestamp(start_date) + pd.DateOffset(months=int(max(n,0)))


def build_actionable_rows_period(expected: pd.DataFrame, state: TLTState,
                                 timeframe: str, max_lag: int = 7,
                                 stock_reversals=None):
    if expected is None or expected.empty:
        return pd.DataFrame()

    tf = timeframe.upper()
    x = expected.copy()
    x["event_date"] = pd.to_datetime(x["event_date"], errors="coerce")
    x["expected_date"] = pd.to_datetime(x["expected_date"], errors="coerce")
    if "actual_response_date" in x.columns:
        x["actual_response_date"] = pd.to_datetime(x["actual_response_date"], errors="coerce")

    x = x[x["normal_lag"].between(0, max_lag)].copy()
    x = x[x["status"].isin(["DUE","UPCOMING","CONFIRMED","EARLY_RESPONSE"])]
    if x.empty:
        return x

    x = x.sort_values(["event_date","score","hit_rate"], ascending=[False,False,False])
    x = x.drop_duplicates(["ticker","normal_lag"], keep="first")
    priority = {"DUE":0,"UPCOMING":1,"CONFIRMED":2,"EARLY_RESPONSE":3}
    x["status_rank"] = x["status"].map(priority).fillna(9)
    x = x.sort_values(["ticker","status_rank","score","event_date"],
                      ascending=[True,True,False,False]).drop_duplicates("ticker", keep="first")

    if tf == "WEEKLY":
        x["Timing"] = x["normal_lag"].map(lambda n: "IN SYNC" if int(n)==0 else f"{int(n)}-WEEK LAG")
    else:
        x["Timing"] = x["normal_lag"].map(lambda n: "IN SYNC" if int(n)==0 else f"{int(n)}-MONTH LAG")

    x["Confidence"] = [confidence_label(s,h) for s,h in zip(x["score"],x["hit_rate"])]

    stock_reversals = stock_reversals or {}
    actions, reversal_labels = [], []

    for _, r in x.iterrows():
        ticker = str(r.get("ticker","")).upper()
        rev = stock_reversals.get(ticker,{})
        has_rev = bool(rev.get("has_reversal",False))
        lag = int(r.get("normal_lag",0))
        status = str(r.get("status","")).upper()

        if has_rev:
            action = "HOLD"
        elif lag <= 1 and state.state != "ACTIVE":
            action = "HOLD"
        elif status == "DUE":
            action = "ACTIONABLE NOW" if state.state == "ACTIVE" else "WATCH / DUE"
        elif status == "UPCOMING":
            action = "WATCH / APPROACHING"
        else:
            action = "MOVE IN PROGRESS"
        actions.append(action)

        if has_rev:
            pattern = rev.get("pattern") or "Bearish reversal"
            d = rev.get("date")
            reversal_labels.append(
                f"{pattern} — {pd.Timestamp(d):%Y-%m-%d}" if d is not None and not pd.isna(d) else pattern
            )
        else:
            reversal_labels.append("")

    x["Action"] = actions
    x["Stock Reversal"] = reversal_labels

    if "ma200_entry_label" in x.columns:
        x["MA200 Entry"] = x["ma200_entry_label"].map({
            "OVEREXTENDED_AVOID": "TOO FAR ABOVE 200WMA",
            "SHORT_SQUEEZE_CANDIDATE": "GOOD ENTRY / SHORT SQUEEZE",
            "NORMAL": "NORMAL",
            "INSUFFICIENT_HISTORY": "NO RATING",
        }).fillna("NO RATING")
    else:
        x["MA200 Entry"] = "NO RATING"

    if "pct_from_sma200" in x.columns:
        x["200DMA Distance"] = pd.to_numeric(
            x["pct_from_sma200"], errors="coerce"
        ).map(lambda v: f"{v*100:+.1f}%" if pd.notna(v) else "—")
    else:
        x["200DMA Distance"] = "—"

    latest = state.asof_date

    def expected_display(r):
        status = str(r.get("status","")).upper()
        if status in ("CONFIRMED","EARLY_RESPONSE"):
            d = r.get("actual_response_date")
            return f"Responded — {pd.Timestamp(d):%Y-%m-%d}" if pd.notna(d) else "Move in progress"

        lag = int(r.get("normal_lag",0))
        d = r.get("expected_date")
        projected = pd.Timestamp(d) if pd.notna(d) else (
            add_calendar_weeks(latest, lag) if tf=="WEEKLY" else add_calendar_months(latest, lag)
        )
        if lag == 0:
            unit = "week" if tf=="WEEKLY" else "month"
            return f"This {unit} — {projected:%Y-%m-%d}" if pd.notna(projected) else "Now"
        unit = "week" if tf=="WEEKLY" else "month"
        units = unit if lag==1 else unit+"s"
        return f"in {lag} {units} — {projected:%Y-%m-%d}" if pd.notna(projected) else f"in {lag} {units}"

    x["Expected"] = [expected_display(r) for _, r in x.iterrows()]
    x["Signal"] = x["status"].map({
        "DUE":"Due now",
        "UPCOMING":"Approaching",
        "CONFIRMED":"Responding",
        "EARLY_RESPONSE":"Responded early",
    }).fillna(x["status"])
    return x


def build_fallback_followers_from_leadlag(leadlag: pd.DataFrame, timeframe: str,
                                          min_hit_rate: float = 0.40,
                                          min_score: float = 45.0,
                                          max_lag: int = 7) -> pd.DataFrame:
    """
    Build client-facing follower candidates directly from the historical lead/lag table.
    This prevents genuine followers from disappearing just because they did not survive
    the expected-move forecast filter.
    """
    if leadlag is None or leadlag.empty:
        return pd.DataFrame()

    x = leadlag.copy()
    for c in ["lag", "hit_rate", "score"]:
        x[c] = pd.to_numeric(x[c], errors="coerce")
    x = x.dropna(subset=["ticker", "lag", "hit_rate", "score"])
    x = x[x["lag"].between(0, max_lag)]

    if "is_best_lag" in x.columns and (x["is_best_lag"] == 1).any():
        best = x[x["is_best_lag"] == 1].copy()
    else:
        best = (
            x.sort_values(["ticker", "score", "hit_rate"], ascending=[True, False, False])
             .drop_duplicates("ticker", keep="first")
        )

    best = best[
        (best["hit_rate"] >= float(min_hit_rate)) &
        (best["score"] >= float(min_score))
    ].copy()

    if best.empty:
        return best

    tf = timeframe.upper()
    if tf == "WEEKLY":
        best["Timing"] = best["lag"].map(
            lambda n: "IN SYNC" if int(n) == 0 else f"{int(n)}-WEEK LAG"
        )
    else:
        best["Timing"] = best["lag"].map(
            lambda n: "IN SYNC" if int(n) == 0 else f"{int(n)}-MONTH LAG"
        )

    best["Confidence"] = [
        confidence_label(s, h) for s, h in zip(best["score"], best["hit_rate"])
    ]
    best["normal_lag"] = best["lag"].astype(int)
    best["Signal"] = "Historical follower"
    best["Action"] = "WATCH / FOLLOWER"
    best["Stock Reversal"] = ""
    best["Expected"] = ""

    return best[[
        "ticker", "normal_lag", "Timing", "Expected", "Signal",
        "Confidence", "Action", "Stock Reversal", "hit_rate", "score"
    ]].copy()


def build_weekly_resistance_snapshot(
    daily_bars: pd.DataFrame,
    lookback_weeks: int = 104,
    pivot_left: int = 2,
    pivot_right: int = 2,
) -> pd.DataFrame:
    """
    Find the nearest meaningful WEEKLY swing-high resistance above current price.

    A weekly resistance pivot is a weekly high that is greater than/equal to
    the highs of pivot_left weeks before and pivot_right weeks after it.

    For each ticker:
      - current_price = latest daily close
      - weekly_resistance = nearest pivot high above current_price
      - potential_upside_pct = resistance/current_price - 1

    If no valid weekly resistance exists above price, resistance/upside are NaN.
    """
    rows = []

    if daily_bars is None or daily_bars.empty:
        return pd.DataFrame()

    for ticker, g in daily_bars.groupby("symbol", sort=False):
        x = g[["bar_date", "open", "high", "low", "close"]].copy()
        x["bar_date"] = pd.to_datetime(x["bar_date"], errors="coerce")
        for c in ["open", "high", "low", "close"]:
            x[c] = pd.to_numeric(x[c], errors="coerce")
        x = x.dropna(subset=["bar_date", "high", "close"]).sort_values("bar_date")

        if x.empty:
            continue

        current_price = float(x.iloc[-1]["close"])
        asof = pd.Timestamp(x.iloc[-1]["bar_date"])

        w = (
            x.set_index("bar_date")
            .resample("W-FRI")
            .agg({
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
            })
            .dropna(subset=["high", "close"])
            .reset_index()
        )

        if lookback_weeks and len(w) > lookback_weeks:
            w = w.tail(int(lookback_weeks)).reset_index(drop=True)

        if len(w) < (pivot_left + pivot_right + 1):
            rows.append({
                "ticker": ticker,
                "resistance_asof": asof,
                "entry_price": current_price,
                "weekly_resistance": np.nan,
                "potential_upside_pct": np.nan,
                "resistance_date": pd.NaT,
            })
            continue

        highs = w["high"].to_numpy(dtype=float)
        pivots = []
        for i in range(pivot_left, len(w) - pivot_right):
            h = highs[i]
            left = highs[i-pivot_left:i]
            right = highs[i+1:i+1+pivot_right]
            if np.all(h >= left) and np.all(h >= right):
                if h > current_price:
                    pivots.append((float(h), pd.Timestamp(w.iloc[i]["bar_date"])))

        if pivots:
            # Nearest overhead resistance, not simply the highest historical high.
            resistance, resistance_date = min(pivots, key=lambda z: z[0])
            upside = resistance / current_price - 1.0 if current_price else np.nan
        else:
            resistance = np.nan
            resistance_date = pd.NaT
            upside = np.nan

        rows.append({
            "ticker": ticker,
            "resistance_asof": asof,
            "entry_price": current_price,
            "weekly_resistance": resistance,
            "potential_upside_pct": upside,
            "resistance_date": resistance_date,
        })

    return pd.DataFrame(rows)


def attach_weekly_resistance_target(actions: pd.DataFrame, snapshot: pd.DataFrame) -> pd.DataFrame:
    if actions is None or actions.empty:
        return actions
    if snapshot is None or snapshot.empty:
        out = actions.copy()
        out["Weekly Target"] = "—"
        out["Potential Upside"] = "—"
        return out

    out = actions.copy()
    key = "ticker" if "ticker" in out.columns else ("symbol" if "symbol" in out.columns else None)
    if key is None:
        return out

    snap = snapshot.copy()
    if key != "ticker":
        snap = snap.rename(columns={"ticker": key})

    keep = [
        key,
        "entry_price",
        "weekly_resistance",
        "potential_upside_pct",
        "resistance_date",
    ]
    out = out.merge(snap[keep], on=key, how="left")

    out["Weekly Target"] = pd.to_numeric(
        out["weekly_resistance"], errors="coerce"
    ).map(lambda v: f"{v:.2f}" if pd.notna(v) else "—")

    out["Potential Upside"] = pd.to_numeric(
        out["potential_upside_pct"], errors="coerce"
    ).map(lambda v: f"{v*100:+.1f}%" if pd.notna(v) else "—")

    return out
