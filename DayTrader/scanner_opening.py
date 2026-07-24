"""
scanner_opening.py — Opening bell VWAP + RVOL breakout scanner.
Runs at 15:35 local (= 9:35 AM ET).
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
    ET_TZ, OUTPUTS_DIR, save_output, log,
    fetch_daily_bulk, fetch_intraday_bulk,
    calc_vwap, calc_rvol, calc_rsi,
    score_opening, now_et, minutes_since_open,
    load_daily_universe,
)

SCAN_NAME = "opening"

def run():
    log(f"Opening scan starting — {now_et().strftime('%H:%M ET')}", SCAN_NAME)
    mins_open = minutes_since_open()
    log(f"Minutes since open: {mins_open:.0f}", SCAN_NAME)

    base_universe = load_daily_universe()

    # Seed from pre-market output if available (prioritise top movers at top of list)
    seed_tickers = []
    try:
        with open(os.path.join(OUTPUTS_DIR, "premarket_latest.json")) as f:
            pm = json.load(f)
        seed_tickers = [r["ticker"] for r in pm.get("results", [])[:40]]
        log(f"Pre-market seed: {len(seed_tickers)} candidates", SCAN_NAME)
    except Exception:
        log("No pre-market file — scanning full universe", SCAN_NAME)

    combined = seed_tickers + [t for t in base_universe if t not in seed_tickers]

    # ── Bulk downloads ──────────────────────────────────────────────────────────
    log(f"Fetching daily + intraday data for {len(combined)} tickers...", SCAN_NAME)
    daily    = fetch_daily_bulk(combined, days=25)
    intraday = fetch_intraday_bulk(combined, period="1d", interval="1m", prepost=True)
    log(f"Data ready: daily={len(daily)}, intraday={len(intraday)}", SCAN_NAME)

    open_ts = now_et().replace(hour=9, minute=30, second=0, microsecond=0)
    results, skipped = [], 0

    for ticker in combined:
        try:
            bars = intraday.get(ticker, pd.DataFrame())
            if bars.empty:
                skipped += 1; continue

            pm_bars  = bars[bars.index < open_ts]
            reg_bars = bars[bars.index >= open_ts]

            if reg_bars.empty:
                skipped += 1; continue

            current_price = float(reg_bars["Close"].iloc[-1])
            open_price    = float(reg_bars["Open"].iloc[0])
            current_vol   = float(reg_bars["Volume"].sum())

            # Previous close: from daily or from last pm bar or first open
            d = daily.get(ticker, {})
            prev_close = d.get("prev_close")
            if not prev_close:
                prev_close = float(pm_bars["Close"].iloc[-1]) if not pm_bars.empty else open_price

            # VWAP from regular-session bars only
            vwap = calc_vwap(reg_bars)
            rsi  = calc_rsi(reg_bars["Close"])

            # RVOL
            avg_vol = d.get("avg_vol")
            if not avg_vol:
                try: avg_vol = yf.Ticker(ticker).fast_info.three_month_average_volume
                except: pass
            rvol = calc_rvol(current_vol, avg_vol, mins_open) if avg_vol else None

            gap_pct    = (open_price - prev_close) / prev_close * 100 if prev_close else 0
            day_change = (current_price - prev_close) / prev_close * 100 if prev_close else 0

            # Skip flat movers
            if abs(day_change) < 1.0 and (not rvol or rvol < 1.5):
                skipped += 1; continue

            grade, score, reasons = score_opening(
                price=current_price, vwap=vwap, rvol=rvol, rsi=rsi, gap_pct=gap_pct
            )
            if score < 2:
                skipped += 1; continue

            results.append({
                "ticker":         ticker,
                "grade":          grade,
                "score":          score,
                "price":          round(current_price, 2),
                "prev_close":     round(prev_close, 2) if prev_close else None,
                "gap_pct":        round(gap_pct, 2),
                "day_change_pct": round(day_change, 2),
                "vwap":           round(vwap, 2) if vwap else None,
                "vs_vwap_pct":    round((current_price / vwap - 1) * 100, 2) if vwap else None,
                "rvol":           rvol,
                "rsi":            round(rsi, 1) if rsi else None,
                "volume":         int(current_vol),
                "avg_vol":        int(avg_vol) if avg_vol else None,
                "reasons":        reasons,
            })

        except Exception:
            skipped += 1

    results.sort(key=lambda x: x["score"], reverse=True)
    aplus = [r for r in results if r["grade"] == "A+"]
    a     = [r for r in results if r["grade"] == "A"]
    log(f"Done. {len(results)} setups | A+: {len(aplus)} | A: {len(a)} | Skipped: {skipped}", SCAN_NAME)

    for r in results[:15]:
        tag = "[A+]" if r["grade"] == "A+" else (" [A]" if r["grade"] == "A" else " [B]")
        vwap = f"VWAP:{r['vs_vwap_pct']:+.1f}%" if r.get("vs_vwap_pct") is not None else ""
        rv   = f"RVOL:{r['rvol']:.1f}x" if r.get("rvol") else ""
        print(f"  {tag} {r['ticker']:6s}  {r['day_change_pct']:+6.1f}%  {vwap:12s}  {rv}")

    save_output(SCAN_NAME, results)
    return results

if __name__ == "__main__":
    run()
