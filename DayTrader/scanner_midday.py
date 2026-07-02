"""
scanner_midday.py — Mid-day consolidation/squeeze scanner.
Runs at 19:30 local (= 1:30 PM ET).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import yfinance as yf
import pandas as pd
import json
from datetime import datetime
from scanner_core import (
    UNIVERSE, ET_TZ, OUTPUTS_DIR, save_output, log,
    fetch_daily_bulk, fetch_intraday_bulk,
    calc_vwap, calc_rvol, calc_rsi,
    score_midday, now_et, minutes_since_open
)

SCAN_NAME = "midday"

def run():
    log(f"Mid-day scan starting — {now_et().strftime('%H:%M ET')}", SCAN_NAME)
    mins_open = minutes_since_open()

    seed_tickers = []
    try:
        with open(os.path.join(OUTPUTS_DIR, "opening_latest.json")) as f:
            op = json.load(f)
        seed_tickers = [r["ticker"] for r in op.get("results", [])[:30]]
        log(f"Opening seed: {len(seed_tickers)} candidates", SCAN_NAME)
    except Exception:
        log("No opening file — full universe", SCAN_NAME)

    combined = seed_tickers + [t for t in UNIVERSE if t not in seed_tickers]

    log(f"Fetching data for {len(combined)} tickers...", SCAN_NAME)
    daily    = fetch_daily_bulk(combined, days=25)
    intraday = fetch_intraday_bulk(combined, period="1d", interval="1m", prepost=False)
    log(f"Data ready: daily={len(daily)}, intraday={len(intraday)}", SCAN_NAME)

    open_ts    = now_et().replace(hour=9, minute=30, second=0, microsecond=0)
    cutoff_11  = now_et().replace(hour=11, minute=0,  second=0, microsecond=0)
    results, skipped = [], 0

    for ticker in combined:
        try:
            bars = intraday.get(ticker, pd.DataFrame())
            if bars.empty or len(bars) < 30:
                skipped += 1; continue

            reg = bars[bars.index >= open_ts]
            if len(reg) < 30:
                skipped += 1; continue

            morning = reg[reg.index < cutoff_11]
            after11 = reg[reg.index >= cutoff_11]

            if morning.empty:
                skipped += 1; continue

            current_price = float(reg["Close"].iloc[-1])
            d = daily.get(ticker, {})
            open_price    = float(reg["Open"].iloc[0])
            prev_close    = d.get("prev_close") or open_price

            morning_high = float(morning["High"].max())
            morning_low  = float(morning["Low"].min())
            morning_move = (morning_high - prev_close) / prev_close * 100 if prev_close else 0

            # Only care about stocks that had a meaningful morning move
            if abs(morning_move) < 2.0:
                skipped += 1; continue

            consol_range = 0.0
            if not after11.empty:
                lo, hi = after11["Low"].min(), after11["High"].max()
                consol_range = (hi - lo) / lo * 100 if lo > 0 else 99

            current_vol = float(reg["Volume"].sum())
            vwap = calc_vwap(reg)
            rsi  = calc_rsi(reg["Close"])

            avg_vol = d.get("avg_vol")
            if not avg_vol:
                try: avg_vol = yf.Ticker(ticker).fast_info.three_month_average_volume
                except: pass
            rvol = calc_rvol(current_vol, avg_vol, mins_open) if avg_vol else None

            last15 = float(reg.tail(15)["Volume"].sum())
            prev15 = float(reg.iloc[-30:-15]["Volume"].sum()) if len(reg) >= 30 else last15
            vol_trend = "increasing" if last15 > prev15 * 1.3 else "flat"

            day_change = (current_price - prev_close) / prev_close * 100 if prev_close else 0

            grade, score, reasons = score_midday(
                price=current_price, vwap=vwap, rvol=rvol,
                morning_high=morning_high, morning_low=morning_low,
                rsi=rsi, vol_trend=vol_trend
            )
            if score < 3:
                skipped += 1; continue

            results.append({
                "ticker":           ticker,
                "grade":            grade,
                "score":            score,
                "price":            round(current_price, 2),
                "day_change_pct":   round(day_change, 2),
                "morning_high":     round(morning_high, 2),
                "morning_move_pct": round(morning_move, 2),
                "consol_range_pct": round(consol_range, 2),
                "pct_from_high":    round((current_price - morning_high) / morning_high * 100, 2),
                "vwap":             round(vwap, 2) if vwap else None,
                "vs_vwap_pct":      round((current_price / vwap - 1) * 100, 2) if vwap else None,
                "rvol":             rvol,
                "rsi":              round(rsi, 1) if rsi else None,
                "vol_trend":        vol_trend,
                "volume":           int(current_vol),
                "reasons":          reasons,
            })

        except Exception:
            skipped += 1

    results.sort(key=lambda x: x["score"], reverse=True)
    aplus = [r for r in results if r["grade"] == "A+"]
    a     = [r for r in results if r["grade"] == "A"]
    log(f"Done. {len(results)} setups | A+: {len(aplus)} | A: {len(a)} | Skipped: {skipped}", SCAN_NAME)

    for r in results[:12]:
        tag = "[A+]" if r["grade"] == "A+" else (" [A]" if r["grade"] == "A" else " [B]")
        print(f"  {tag} {r['ticker']:6s}  AM:{r['morning_move_pct']:+5.1f}%  Range:{r['consol_range_pct']:.1f}%  VWAP:{r.get('vs_vwap_pct') or '?'}")

    save_output(SCAN_NAME, results)
    return results

if __name__ == "__main__":
    run()
