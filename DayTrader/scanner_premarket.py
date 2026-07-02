"""
scanner_premarket.py — Pre-market gap scanner.
Runs at 13:00, 14:00, 15:00 local (= 7, 8, 9 AM ET).

When running during pre-market hours, uses intraday prepost=True bars to
find the latest pre-market price. When run after hours (testing), uses
last close vs prev close as the gap proxy.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
from scanner_core import (
    UNIVERSE, ET_TZ, OUTPUTS_DIR, save_output, log,
    fetch_daily_bulk, fetch_intraday_bulk,
    score_premarket, now_et
)

SCAN_NAME = "premarket"

def run():
    n_et = now_et()
    log(f"Pre-market scan starting — {n_et.strftime('%H:%M ET')}", SCAN_NAME)

    is_premarket_session = n_et.hour < 9 or (n_et.hour == 9 and n_et.minute < 30)

    # ── 1. Daily data for previous close + avg volume ─────────────────────────
    log(f"Fetching {len(UNIVERSE)} tickers daily data...", SCAN_NAME)
    daily = fetch_daily_bulk(UNIVERSE, days=25)
    log(f"Daily data fetched for {len(daily)} tickers", SCAN_NAME)

    # ── 2. Intraday data (prepost=True to capture pre-market bars) ─────────────
    log("Fetching intraday 1-min data (with pre/post)...", SCAN_NAME)
    intraday = fetch_intraday_bulk(UNIVERSE, period="1d", interval="1m", prepost=True)
    log(f"Intraday data fetched for {len(intraday)} tickers", SCAN_NAME)

    open_ts = n_et.replace(hour=9, minute=30, second=0, microsecond=0)

    results = []
    skipped = 0

    for ticker in UNIVERSE:
        try:
            d = daily.get(ticker, {})
            prev_close = d.get("prev_close")
            avg_vol    = d.get("avg_vol")
            year_high  = d.get("year_high")

            bars = intraday.get(ticker, pd.DataFrame())

            if bars.empty:
                skipped += 1; continue

            # During pre-market: get the most recent bar before 9:30 AM
            # After hours: use regular session bars
            if is_premarket_session:
                pm_bars  = bars[bars.index < open_ts]
                reg_bars = bars[bars.index >= open_ts]
                if not pm_bars.empty:
                    current_price = float(pm_bars["Close"].iloc[-1])
                    pm_vol = float(pm_bars["Volume"].sum())
                    # Previous close: use last bar of previous day if available,
                    # else daily prev_close
                    if prev_close is None and not reg_bars.empty:
                        prev_close = float(reg_bars["Open"].iloc[0])
                else:
                    skipped += 1; continue
            else:
                # After-hours testing mode: use today's close vs prev close
                reg_bars = bars[bars.index >= open_ts] if not bars.empty else bars
                pm_bars  = bars[bars.index <  open_ts]
                pm_vol   = float(pm_bars["Volume"].sum()) if not pm_bars.empty else 0

                if reg_bars.empty:
                    skipped += 1; continue
                current_price = float(reg_bars["Close"].iloc[-1])
                if prev_close is None:
                    # Fall back to open of today
                    prev_close = float(reg_bars["Open"].iloc[0])

            if not prev_close or prev_close == 0 or not current_price:
                skipped += 1; continue

            price    = current_price
            gap_pct  = (price - prev_close) / prev_close * 100

            # After-hours: use full day volume as proxy for "pm_vol"
            if not is_premarket_session and pm_vol == 0 and not bars.empty:
                pm_vol = float(bars["Volume"].sum())

            # Skip tiny movers
            if abs(gap_pct) < 1.0:
                skipped += 1; continue

            # Avg vol fallback via fast_info
            if not avg_vol:
                try:
                    avg_vol = yf.Ticker(ticker).fast_info.three_month_average_volume
                except Exception:
                    pass

            grade, score, reasons, direction = score_premarket(
                gap_pct=gap_pct,
                pm_vol=pm_vol,
                avg_vol=avg_vol,
                price=price,
                year_high=year_high,
            )

            if score < 2:
                skipped += 1; continue

            pm_rvol = None
            if avg_vol and pm_vol and avg_vol > 0:
                pm_rvol = round(pm_vol / (avg_vol * (90 / 390)), 2)

            results.append({
                "ticker":     ticker,
                "grade":      grade,
                "score":      score,
                "direction":  direction,
                "price":      round(price, 2),
                "prev_close": round(prev_close, 2),
                "gap_pct":    round(gap_pct, 2),
                "pm_volume":  int(pm_vol),
                "pm_rvol":    pm_rvol,
                "avg_vol":    int(avg_vol) if avg_vol else None,
                "year_high":  round(year_high, 2) if year_high else None,
                "reasons":    reasons,
            })

        except Exception as e:
            skipped += 1

    results.sort(key=lambda x: x["score"], reverse=True)
    aplus = [r for r in results if r["grade"] == "A+"]
    a     = [r for r in results if r["grade"] == "A"]
    log(f"Done. {len(results)} movers | A+: {len(aplus)} | A: {len(a)} | Skipped: {skipped}", SCAN_NAME)

    for r in results[:15]:
        tag = "[A+]" if r["grade"] == "A+" else (" [A]" if r["grade"] == "A" else " [B]")
        rv  = f"{r['pm_rvol']:.1f}x" if r.get("pm_rvol") else " ?"
        print(f"  {tag} {r['ticker']:6s}  {r['gap_pct']:+6.1f}%  PM-RVOL:{rv:>5}  {r['direction']}  score:{r['score']}")

    save_output(SCAN_NAME, results)
    return results

if __name__ == "__main__":
    run()
