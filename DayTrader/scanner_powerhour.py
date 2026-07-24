"""
scanner_powerhour.py — Power hour momentum continuation scanner.
Runs at 21:00 local (= 3:00 PM ET).
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
    score_powerhour, now_et, minutes_since_open,
    load_daily_universe,
)

SCAN_NAME = "powerhour"

def run():
    log(f"Power hour scan starting — {now_et().strftime('%H:%M ET')}", SCAN_NAME)
    mins_open = minutes_since_open()

    base_universe = load_daily_universe()

    seed_tickers = []
    try:
        with open(os.path.join(OUTPUTS_DIR, "midday_latest.json")) as f:
            md = json.load(f)
        seed_tickers = [r["ticker"] for r in md.get("results", [])[:25]]
        log(f"Midday seed: {len(seed_tickers)} candidates", SCAN_NAME)
    except Exception:
        log("No midday file — full universe", SCAN_NAME)

    combined = seed_tickers + [t for t in base_universe if t not in seed_tickers]

    log(f"Fetching data for {len(combined)} tickers...", SCAN_NAME)
    daily    = fetch_daily_bulk(combined, days=25)
    intraday = fetch_intraday_bulk(combined, period="1d", interval="1m", prepost=False)
    log(f"Data ready: daily={len(daily)}, intraday={len(intraday)}", SCAN_NAME)

    open_ts  = now_et().replace(hour=9, minute=30, second=0, microsecond=0)
    ph_start = now_et().replace(hour=15, minute=0,  second=0, microsecond=0)
    results, skipped = [], 0

    for ticker in combined:
        try:
            bars = intraday.get(ticker, pd.DataFrame())
            if bars.empty or len(bars) < 60:
                skipped += 1; continue

            reg = bars[bars.index >= open_ts]
            if len(reg) < 60:
                skipped += 1; continue

            d = daily.get(ticker, {})
            prev_close    = d.get("prev_close") or float(reg["Open"].iloc[0])
            current_price = float(reg["Close"].iloc[-1])
            day_high      = float(reg["High"].max())
            current_vol   = float(reg["Volume"].sum())

            day_change = (current_price - prev_close) / prev_close * 100 if prev_close else 0
            if abs(day_change) < 2.0:
                skipped += 1; continue

            # Power-hour bars only
            ph_bars = reg[reg.index >= ph_start] if not reg.empty else pd.DataFrame()
            pre_ph  = reg[reg.index < ph_start]  if not reg.empty else reg

            ph_vol     = float(ph_bars["Volume"].sum()) if not ph_bars.empty else 0
            pre_ph_vol = float(pre_ph.tail(30)["Volume"].sum()) if not pre_ph.empty else ph_vol
            ph_rvol_vs_prior = ph_vol / pre_ph_vol if pre_ph_vol > 0 else 1.0

            avg_vol = d.get("avg_vol")
            if not avg_vol:
                try: avg_vol = yf.Ticker(ticker).fast_info.three_month_average_volume
                except: pass
            rvol_day = calc_rvol(current_vol, avg_vol, mins_open) if avg_vol else None

            ph_rvol = None
            if avg_vol and avg_vol > 0:
                expected_ph = avg_vol * (len(ph_bars) / 390) if not ph_bars.empty else avg_vol * (30 / 390)
                ph_rvol = round(ph_vol / expected_ph, 2) if expected_ph > 0 else None

            vwap = calc_vwap(reg)
            rsi  = calc_rsi(reg["Close"])

            ph_high = float(ph_bars["High"].max()) if not ph_bars.empty else 0
            full_high = float(pre_ph["High"].max()) if not pre_ph.empty else ph_high
            new_intraday_high = ph_high >= full_high and ph_high > 0

            grade, score, reasons = score_powerhour(
                price=current_price, vwap=vwap, rvol=ph_rvol if ph_rvol else rvol_day,
                day_change_pct=day_change, new_high=new_intraday_high, rsi=rsi
            )
            if score < 3:
                skipped += 1; continue

            results.append({
                "ticker":            ticker,
                "grade":             grade,
                "score":             score,
                "price":             round(current_price, 2),
                "day_change_pct":    round(day_change, 2),
                "day_high":          round(day_high, 2),
                "new_intraday_high": new_intraday_high,
                "vwap":              round(vwap, 2) if vwap else None,
                "vs_vwap_pct":       round((current_price / vwap - 1) * 100, 2) if vwap else None,
                "rvol_day":          rvol_day,
                "rvol_ph":           ph_rvol,
                "ph_vol_vs_prior":   round(ph_rvol_vs_prior, 2),
                "rsi":               round(rsi, 1) if rsi else None,
                "volume_today":      int(current_vol),
                "reasons":           reasons,
            })

        except Exception:
            skipped += 1

    results.sort(key=lambda x: x["score"], reverse=True)
    aplus = [r for r in results if r["grade"] == "A+"]
    a     = [r for r in results if r["grade"] == "A"]
    log(f"Done. {len(results)} setups | A+: {len(aplus)} | A: {len(a)} | Skipped: {skipped}", SCAN_NAME)

    for r in results[:12]:
        tag = "[A+]" if r["grade"] == "A+" else (" [A]" if r["grade"] == "A" else " [B]")
        hi  = "<NEW HIGH>" if r.get("new_intraday_high") else ""
        print(f"  {tag} {r['ticker']:6s}  {r['day_change_pct']:+6.1f}%  PH-RVOL:{r.get('rvol_ph') or '?'}x  {hi}")

    save_output(SCAN_NAME, results)
    return results

if __name__ == "__main__":
    run()
