"""
scanner_core.py — shared universe, utilities, scoring, and A+ logic.
"""
import sys
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz
import json
import os

ET_TZ = pytz.timezone("US/Eastern")

# ─── Stock universe ─────────────────────────────────────────────────────────
UNIVERSE = [
    "AAPL","MSFT","NVDA","TSLA","AMZN","META","GOOGL","AMD",
    "INTC","QCOM","AVGO","MU","NFLX","CRM","ORCL","ADBE","ARM","SMCI",
    "KLAC","LRCX","AMAT","MRVL","ON","TXN",
    "JPM","BAC","GS","MS","C","WFC","V","MA","AXP","SCHW","COIN","HOOD","SOFI",
    "XOM","CVX","SLB","OXY","HAL","COP",
    "LLY","PFE","JNJ","ABBV","MRNA","BNTX","GILD","BMY","REGN","BIIB",
    "NIO","XPEV","LI","RIVN","LCID",
    "PLTR","RBLX","SNAP","LYFT","UBER","ABNB","ROKU","ZM",
    "DOCU","SNOW","DDOG","CRWD","PANW","ZS","NET","OKTA",
    "BABA","JD","BIDU","PDD",
    "MSTR","RIOT","MARA","CLSK",
    "TGT","WMT","COST","NKE","SBUX","MCD",
    "RTX","LMT","BA","NOC","GE","CAT",
    "T","VZ","TMUS",
    "GME","AMC",
    "SPY","QQQ","IWM","DIA",
    "SOXL","SOXS","TQQQ","SQQQ","UVXY",
    "LABU","LABD","SPXL","SPXS","TECL","TECS",
    "GDX","GDXJ","GLD","SLV","TLT","HYG","USO","XLE","XLF","KRE",
]
UNIVERSE = sorted(set(UNIVERSE))

BASE        = os.path.dirname(os.path.abspath(__file__))
OUTPUTS_DIR = os.path.join(BASE, "outputs")
LOGS_DIR    = os.path.join(BASE, "logs")
os.makedirs(OUTPUTS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR,    exist_ok=True)

# ─── Time helpers ────────────────────────────────────────────────────────────

def now_et() -> datetime:
    return datetime.now(ET_TZ)

def market_open_today() -> datetime:
    return now_et().replace(hour=9, minute=30, second=0, microsecond=0)

def minutes_since_open() -> float:
    delta = now_et() - market_open_today()
    return max(1.0, delta.total_seconds() / 60)

# ─── Data fetching ───────────────────────────────────────────────────────────

def fetch_daily_bulk(tickers: list, days: int = 25) -> dict:
    """
    Returns dict: {ticker: {"prev_close": float, "avg_vol": float, "year_high": float}}
    Uses a single bulk yf.download call, column MultiIndex is (field, ticker).
    """
    try:
        raw = yf.download(
            tickers=tickers,
            period=f"{days}d",
            interval="1d",
            auto_adjust=True,
            progress=False,
        )
    except Exception as e:
        log(f"Bulk daily download error: {e}")
        return {}

    result = {}
    close_df  = raw.get("Close")  if isinstance(raw, pd.DataFrame) else None
    volume_df = raw.get("Volume") if isinstance(raw, pd.DataFrame) else None

    # Pandas stores as (field, ticker) MultiIndex → raw["Close"] gives a df with tickers as columns
    if close_df is None or close_df.empty:
        return result

    today_date = pd.Timestamp.now(tz="UTC").date()

    for tk in tickers:
        try:
            closes = close_df[tk].dropna() if tk in close_df.columns else pd.Series(dtype=float)
            vols   = volume_df[tk].dropna() if volume_df is not None and tk in volume_df.columns else pd.Series(dtype=float)
            if closes.empty:
                continue

            # Identify the previous trading day's close (not today's if market has closed)
            last_bar_date = closes.index[-1].date() if hasattr(closes.index[-1], "date") else closes.index[-1].date()
            if last_bar_date == today_date and len(closes) >= 2:
                # Today's bar is in the download — use second-to-last as prev_close
                prev_close = float(closes.iloc[-2])
            else:
                prev_close = float(closes.iloc[-1])

            result[tk] = {
                "prev_close": prev_close,
                "avg_vol":    float(vols.tail(20).mean()) if len(vols) >= 5 else None,
                "year_high":  float(closes.max()),
                "year_low":   float(closes.min()),
            }
        except Exception:
            pass

    return result

def fetch_intraday_bulk(tickers: list, period: str = "1d",
                         interval: str = "1m", prepost: bool = True) -> dict:
    """
    Returns dict: {ticker: pd.DataFrame of 1-min bars (ET-localised index)}.
    Single bulk download; parses (field, ticker) MultiIndex.
    """
    try:
        raw = yf.download(
            tickers=tickers,
            period=period,
            interval=interval,
            prepost=prepost,
            auto_adjust=True,
            progress=False,
        )
    except Exception as e:
        log(f"Bulk intraday download error: {e}")
        return {}

    if raw.empty:
        return {}

    # Localise index
    if raw.index.tz is None:
        raw.index = raw.index.tz_localize("UTC").tz_convert(ET_TZ)
    else:
        raw.index = raw.index.tz_convert(ET_TZ)

    result = {}
    close_df  = raw.get("Close")
    high_df   = raw.get("High")
    low_df    = raw.get("Low")
    open_df   = raw.get("Open")
    volume_df = raw.get("Volume")

    if close_df is None:
        return result

    for tk in tickers:
        try:
            if tk not in close_df.columns:
                continue
            df = pd.DataFrame({
                "Open":   open_df[tk]   if open_df   is not None else np.nan,
                "High":   high_df[tk]   if high_df   is not None else np.nan,
                "Low":    low_df[tk]    if low_df    is not None else np.nan,
                "Close":  close_df[tk],
                "Volume": volume_df[tk] if volume_df is not None else 0,
            }).dropna(subset=["Close"])
            if not df.empty:
                result[tk] = df
        except Exception:
            pass

    return result

def get_fast_info(ticker: str) -> dict:
    """Light per-ticker quote."""
    try:
        fi = yf.Ticker(ticker).fast_info
        return {
            "price":      getattr(fi, "last_price",                None),
            "prev_close": getattr(fi, "previous_close",            None),
            "avg_vol_3m": getattr(fi, "three_month_average_volume", None),
            "mkt_cap":    getattr(fi, "market_cap",                None),
            "year_high":  getattr(fi, "year_high",                 None),
            "year_low":   getattr(fi, "year_low",                  None),
        }
    except Exception:
        return {}

# ─── Technical indicators ────────────────────────────────────────────────────

def calc_vwap(df: pd.DataFrame) -> float | None:
    if df.empty or df["Volume"].sum() == 0:
        return None
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    return float((tp * df["Volume"]).sum() / df["Volume"].sum())

def calc_rvol(current_vol: float, avg_daily_vol: float,
              mins_elapsed: float) -> float | None:
    if not avg_daily_vol or avg_daily_vol <= 0 or mins_elapsed <= 0:
        return None
    expected = avg_daily_vol * (mins_elapsed / 390)
    return round(current_vol / expected, 2) if expected > 0 else None

def calc_rsi(closes: pd.Series, period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    delta = closes.diff().dropna()
    gain  = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - 100 / (1 + rs)
    return float(rsi.iloc[-1]) if not rsi.empty else None

# ─── Scoring ─────────────────────────────────────────────────────────────────

def grade_score(score: int) -> str:
    if score >= 8:  return "A+"
    if score >= 6:  return "A"
    if score >= 4:  return "B"
    return "C"

def score_premarket(gap_pct, pm_vol, avg_vol, price, year_high):
    score, reasons = 0, []
    gap_abs = abs(gap_pct) if gap_pct else 0
    direction = "LONG" if (gap_pct or 0) >= 0 else "SHORT"

    if gap_abs >= 10: score += 5; reasons.append(f"Huge gap {gap_abs:.1f}%")
    elif gap_abs >= 5: score += 3; reasons.append(f"Strong gap {gap_abs:.1f}%")
    elif gap_abs >= 3: score += 2; reasons.append(f"Gap {gap_abs:.1f}%")
    elif gap_abs >= 1.5: score += 1

    if avg_vol and pm_vol:
        pm_rvol = pm_vol / (avg_vol * (90 / 390))
        if pm_rvol >= 4:   score += 3; reasons.append(f"PM RVOL {pm_rvol:.1f}x")
        elif pm_rvol >= 2: score += 2; reasons.append(f"PM RVOL {pm_rvol:.1f}x")
        elif pm_rvol >= 1: score += 1; reasons.append(f"PM RVOL {pm_rvol:.1f}x")

    if price and 5 < price < 200: score += 1
    if year_high and price and year_high > 0:
        pct = (price - year_high) / year_high * 100
        if pct >= -3: score += 2; reasons.append(f"Near 52w high ({pct:+.1f}%)")

    return grade_score(score), score, reasons, direction

def score_opening(price, vwap, rvol, rsi, gap_pct):
    score, reasons = 0, []
    if vwap and price:
        if price > vwap: score += 2; reasons.append(f"Above VWAP ({(price/vwap-1)*100:+.2f}%)")
        else:            reasons.append(f"Below VWAP ({(price/vwap-1)*100:+.2f}%)")
    if rvol:
        if rvol >= 5:     score += 4; reasons.append(f"RVOL {rvol:.1f}x [FIRE]")
        elif rvol >= 3:   score += 3; reasons.append(f"RVOL {rvol:.1f}x")
        elif rvol >= 2:   score += 2; reasons.append(f"RVOL {rvol:.1f}x")
        elif rvol >= 1.5: score += 1; reasons.append(f"RVOL {rvol:.1f}x")
    if rsi:
        if 50 <= rsi <= 70:  score += 2; reasons.append(f"RSI {rsi:.0f} (momentum)")
        elif rsi > 70:       score -= 1; reasons.append(f"RSI {rsi:.0f} (overbought)")
    if gap_pct and abs(gap_pct) > 2: score += 2; reasons.append(f"Gap held ({gap_pct:+.1f}%)")
    return grade_score(score), score, reasons

def score_midday(price, vwap, rvol, morning_high, morning_low, rsi, vol_trend):
    score, reasons = 0, []
    if vwap and price:
        if price > vwap: score += 2; reasons.append("Holding above VWAP")
        else:            reasons.append("Below VWAP")
    if morning_high and price:
        intraday_range = (morning_high - morning_low) / morning_high * 100 if morning_low else 99
        pct_from_high  = (price - morning_high) / morning_high * 100
        if intraday_range < 4 and pct_from_high >= -2: score += 2; reasons.append(f"Tight consol ({intraday_range:.1f}%)")
        if pct_from_high >= -1.5: score += 2; reasons.append(f"Near high ({pct_from_high:+.1f}%)")
    if rvol and rvol >= 1.5: score += 1; reasons.append(f"RVOL {rvol:.1f}x")
    if vol_trend == "increasing": score += 2; reasons.append("Vol picking up (squeeze)")
    if rsi and 45 <= rsi <= 65:  score += 1; reasons.append(f"RSI {rsi:.0f}")
    return grade_score(score), score, reasons

def score_powerhour(price, vwap, rvol, day_change_pct, new_high, rsi):
    score, reasons = 0, []
    if day_change_pct >= 10:  score += 4; reasons.append(f"Up {day_change_pct:.1f}% [ROCKET]")
    elif day_change_pct >= 5: score += 3; reasons.append(f"Up {day_change_pct:.1f}%")
    elif day_change_pct >= 2: score += 1; reasons.append(f"Up {day_change_pct:.1f}%")
    elif day_change_pct <= -5: score += 2; reasons.append(f"Down {day_change_pct:.1f}% (short)")
    if vwap and price:
        if price > vwap: score += 2; reasons.append("Holding VWAP")
        else:            reasons.append("Lost VWAP")
    if rvol and rvol >= 1.5: score += 2; reasons.append(f"PH RVOL {rvol:.1f}x")
    if new_high:             score += 2; reasons.append("New intraday high")
    if rsi and 50 <= rsi <= 75: score += 1; reasons.append(f"RSI {rsi:.0f}")
    return grade_score(score), score, reasons

# ─── Output helpers ──────────────────────────────────────────────────────────

def save_output(scan_name: str, results: list) -> str:
    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
    payload = {
        "scan":      scan_name,
        "timestamp": now_et().strftime("%Y-%m-%d %H:%M:%S ET"),
        "count":     len(results),
        "results":   results,
    }
    archive = os.path.join(OUTPUTS_DIR, f"{scan_name}_{ts}.json")
    latest  = os.path.join(OUTPUTS_DIR, f"{scan_name}_latest.json")
    for path in (archive, latest):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
    return latest

def log(msg: str, scan_name: str = "daytrader"):
    ts   = now_et().strftime("%H:%M:%S ET")
    line = f"[{datetime.now().strftime('%Y-%m-%d')} {ts}] [{scan_name.upper()}] {msg}"
    print(line, flush=True)
    log_path = os.path.join(LOGS_DIR, "daytrader_log.txt")
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass  # file lock from concurrent writer — stdout already captured it
