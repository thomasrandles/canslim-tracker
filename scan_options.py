#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scan_options.py - Long Call / Long Put opportunity scanner.

Screens US stocks + ETFs for directional options setups using:
  - TradingView screener for stock-level filters (trend, RSI, momentum)
  - A fixed liquid-names overlay (SPY, QQQ, NVDA, etc.) always scanned
  - yfinance for live options chains (IV, OI, spread, Greeks)
  - Black-Scholes for Delta / Theta calculation

Usage:
    python C:/CANSLIM/scan_options.py
    python C:/CANSLIM/scan_options.py --calls-only
    python C:/CANSLIM/scan_options.py --puts-only
    python C:/CANSLIM/scan_options.py --top 20
"""

import sys, math, datetime, time, argparse, zoneinfo
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd
import yfinance as yf
from scipy.stats import norm
from tradingview_screener import Query, col

_ET = zoneinfo.ZoneInfo("America/New_York")


def _check_market_hours():
    """Warn if US options market is likely closed."""
    now_et = datetime.datetime.now(_ET)
    day    = now_et.weekday()          # 0=Mon … 6=Sun
    hour   = now_et.hour + now_et.minute / 60.0
    if day >= 5:
        print(f"  WARNING: Today is {'Saturday' if day == 5 else 'Sunday'} — "
              f"US markets are closed. Options quotes will be empty.\n")
        return False
    if hour < 9.5 or hour >= 16.0:
        open_in = max(0, 9.5 - hour) if hour < 9.5 else 0
        print(f"  WARNING: US market is CLOSED right now "
              f"({now_et.strftime('%H:%M ET')}).\n"
              f"  Options quotes will be empty — run between 09:30–16:00 ET "
              f"(14:30–21:00 Irish time).\n"
              f"  {'Market opens in %.0f min.' % (open_in*60) if open_in > 0 else ''}\n")
        return False
    return True

# -- Constants -----------------------------------------------------------------
TARGET_DTE_MIN   = 25
TARGET_DTE_MAX   = 65
TARGET_DTE_IDEAL = 37      # prefer expiry near 37 DTE
OTM_PCT_MIN      = -0.01   # allow slight ITM / ATM as well
OTM_PCT_MAX      = 0.08    # up to 8% OTM
MAX_SPREAD_PCT   = 0.25    # bid/ask spread < 25% of mid
MIN_OI           = 25      # minimum open interest
MAX_IV           = 0.70    # avoid buying when IV > 70%
TODAY            = datetime.date.today()
R                = 0.045   # risk-free rate

# Always scan these regardless of trend screen (most liquid options in market)
LIQUID_OVERLAY_CALLS = [
    "SPY", "QQQ", "IWM", "DIA",          # index ETFs
    "XLK", "XLF", "XLE", "XLV", "XLY",  # sector ETFs
    "GLD", "SLV", "USO",                  # commodity ETFs
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA",  # mega-cap tech
    "NFLX", "AMD", "ORCL", "CRM", "UBER", "COIN",              # high-IV names
    "JPM", "BAC", "GS", "V", "MA",        # financials
    "XOM", "CVX",                          # energy
]

LIQUID_OVERLAY_PUTS = [
    "SPY", "QQQ", "IWM",
    "XLK", "XLF", "XLE",
    "AAPL", "MSFT", "NVDA", "AMZN", "TSLA", "META",
    "AMD", "COIN", "NFLX", "GOOGL",
]

TV_COLUMNS = [
    "name", "description", "close", "exchange", "sector",
    "market_cap_basic", "average_volume_10d_calc",
    "RSI", "ADX", "SMA50", "SMA200",
    "Perf.1W", "Perf.3M", "Perf.Y",
    "price_52_week_high", "earnings_per_share_diluted_yoy_growth_ttm",
]

# -- Black-Scholes -------------------------------------------------------------
def bs_delta_call(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0: return 1.0 if S > K else 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    return norm.cdf(d1)

def bs_delta_put(S, K, T, r, sigma):
    return bs_delta_call(S, K, T, r, sigma) - 1.0

def bs_theta(S, K, T, r, sigma, is_call=True):
    if T <= 0.001 or sigma <= 0: return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    term1 = -(S * norm.pdf(d1) * sigma) / (2 * math.sqrt(T))
    term2 = (-r * K * math.exp(-r * T) * norm.cdf(d2)) if is_call \
            else (r * K * math.exp(-r * T) * norm.cdf(-d2))
    return (term1 + term2) / 365.0

# -- TradingView screens -------------------------------------------------------
def _tv_query(extra_filters, limit=100):
    try:
        _, df = (
            Query()
            .select(*TV_COLUMNS)
            .where(
                col("average_volume_10d_calc") > 1_000_000,
                col("market_cap_basic") > 1_000_000_000,
                col("exchange").isin(["NYSE", "NASDAQ", "CBOE", "AMEX"]),
                *extra_filters,
            )
            .order_by("average_volume_10d_calc", ascending=False)
            .set_markets("america")
            .limit(limit)
            .get_scanner_data()
        )
        return df
    except Exception as e:
        print(f"  TradingView error: {e}")
        return pd.DataFrame()


def screen_calls(limit=100):
    print("Screening for bullish stocks (TradingView, sorted by volume)...")
    df = _tv_query([
        col("SMA50") > col("SMA200"),       # golden cross
        col("close") > col("SMA50"),        # price above 50MA
        col("RSI").between(44, 74),
        col("Perf.3M") > 4,
        col("ADX") > 15,
    ], limit=limit)
    print(f"  {len(df)} call candidates from TV screen")
    return df


def screen_puts(limit=100):
    print("Screening for bearish stocks (TradingView, sorted by volume)...")
    df = _tv_query([
        col("close") < col("SMA50"),        # price below 50MA
        col("RSI").between(18, 54),
        col("Perf.3M") < -4,
    ], limit=limit)
    print(f"  {len(df)} put candidates from TV screen")
    return df


# -- Options chain analysis ----------------------------------------------------
def pick_expiry(expiries):
    best, best_diff = None, 9999
    for e in expiries:
        try:
            dte = (datetime.date.fromisoformat(e) - TODAY).days
            if TARGET_DTE_MIN <= dte <= TARGET_DTE_MAX:
                diff = abs(dte - TARGET_DTE_IDEAL)
                if diff < best_diff:
                    best, best_diff = e, diff
        except Exception:
            pass
    return best


def find_best_contract(ticker, spot, direction):
    try:
        tk       = yf.Ticker(ticker)
        expiries = tk.options
        if not expiries:
            return None

        expiry = pick_expiry(expiries)
        if not expiry:
            return None

        chain     = tk.option_chain(expiry)
        contracts = chain.calls if direction == "call" else chain.puts
        dte       = (datetime.date.fromisoformat(expiry) - TODAY).days
        T         = dte / 365.0

        best, best_score = None, -1

        for _, row in contracts.iterrows():
            strike = float(row["strike"])
            bid    = float(row.get("bid", 0) or 0)
            ask    = float(row.get("ask", 0) or 0)
            iv     = float(row.get("impliedVolatility", 0) or 0)
            # openInterest/volume can be NaN — int(NaN) raises ValueError
            oi_raw = row.get("openInterest", 0)
            oi     = 0 if oi_raw is None or (isinstance(oi_raw, float) and math.isnan(oi_raw)) else int(oi_raw)
            vol_raw= row.get("volume", 0)
            vol    = 0 if vol_raw is None or (isinstance(vol_raw, float) and math.isnan(vol_raw)) else int(vol_raw)

            if ask <= 0 or iv <= 0:
                continue

            mid = (bid + ask) / 2.0
            if mid <= 0:
                continue

            otm_pct = ((strike - spot) / spot) if direction == "call" \
                      else ((spot - strike) / spot)

            if not (OTM_PCT_MIN <= otm_pct <= OTM_PCT_MAX):
                continue
            if oi < MIN_OI:
                continue
            if iv > MAX_IV:
                continue

            spread_pct = (ask - bid) / mid if mid > 0 else 99
            if spread_pct > MAX_SPREAD_PCT:
                continue

            if direction == "call":
                delta = round(bs_delta_call(spot, strike, T, R, iv), 3)
                theta = round(bs_theta(spot, strike, T, R, iv, is_call=True), 3)
            else:
                delta = round(bs_delta_put(spot, strike, T, R, iv), 3)
                theta = round(bs_theta(spot, strike, T, R, iv, is_call=False), 3)

            score = 0
            score += max(0, 3 - spread_pct * 10)
            score += min(3, math.log10(max(oi, 1)))
            if 0.28 <= abs(delta) <= 0.52: score += 2
            if iv < 0.28: score += 2
            elif iv < 0.40: score += 1

            if score > best_score:
                best_score = score
                best = {
                    "expiry":     expiry,
                    "dte":        dte,
                    "strike":     strike,
                    "bid":        round(bid, 2),
                    "ask":        round(ask, 2),
                    "mid":        round(mid, 2),
                    "iv":         round(iv, 3),
                    "oi":         oi,
                    "volume":     vol,
                    "spread_pct": round(spread_pct * 100, 1),
                    "delta":      delta,
                    "theta_day":  theta,
                    "cost":       round(mid * 100, 2),
                    "breakeven":  round(strike + mid, 2) if direction == "call"
                                  else round(strike - mid, 2),
                    "otm_pct":    round(otm_pct * 100, 1),
                }
        return best
    except Exception:
        return None


# -- Scoring -------------------------------------------------------------------
def score_setup(stock, contract, direction):
    score   = 0
    rsi     = stock.get("RSI") or 0
    adx     = stock.get("ADX") or 0
    p3m     = stock.get("Perf.3M") or 0
    sma50   = stock.get("SMA50") or 0
    sma200  = stock.get("SMA200") or 0
    price   = stock.get("close") or 0
    iv      = contract.get("iv", 0.5)
    delta   = abs(contract.get("delta", 0))
    spread  = contract.get("spread_pct", 99)
    oi      = contract.get("oi", 0)

    if direction == "call":
        if sma50 > 0 and sma200 > 0 and sma50 > sma200: score += 2
        if price > sma50:                                 score += 1
        if 52 <= rsi <= 65:  score += 2
        elif 44 <= rsi < 52: score += 1
        elif 65 < rsi <= 73: score += 1
        if p3m > 20:   score += 2
        elif p3m > 8:  score += 1
        if adx > 30:   score += 1
    else:
        if sma50 > 0 and sma200 > 0 and sma50 < sma200: score += 2
        if price < sma50:                                 score += 1
        if 28 <= rsi <= 48:  score += 2
        elif 18 <= rsi < 28: score += 1
        elif 48 < rsi <= 54: score += 1
        if p3m < -20:   score += 2
        elif p3m < -8:  score += 1
        if adx > 25:    score += 1

    if iv < 0.25:              score += 2
    elif iv < 0.38:            score += 1
    if 0.28 <= delta <= 0.50:  score += 1
    if spread < 8:             score += 1
    if oi > 500:               score += 1

    return min(score, 10)


def grade(score):
    if score >= 8: return "A+"
    if score >= 6: return "A"
    if score >= 4: return "B"
    return "C"


# -- Fetch spot price for liquid overlay tickers (not in TV screen) ------------
def fetch_spots(tickers):
    spots = {}
    try:
        raw = yf.download(tickers, period="1d", auto_adjust=True, progress=False)
        if "Close" in raw.columns:
            last = raw["Close"].iloc[-1]
            for t in tickers:
                try:
                    spots[t] = float(last[t])
                except Exception:
                    pass
        elif hasattr(raw["Close"], "item"):
            # single ticker
            spots[tickers[0]] = float(raw["Close"].iloc[-1])
    except Exception:
        pass
    return spots


# -- Main ----------------------------------------------------------------------
def run(calls=True, puts=True, top_n=15):
    now_et = datetime.datetime.now(_ET)
    print("=" * 68)
    print(f"  Options Scanner  -  Long Call / Long Put")
    print(f"  {TODAY}   {now_et.strftime('%H:%M ET')}   Target DTE: {TARGET_DTE_IDEAL} days")
    print("=" * 68)
    print()
    _check_market_hours()

    results = []

    def process_tv_row(row, direction):
        ticker = str(row.get("name", "")).strip().upper()
        if not ticker or ":" in ticker:
            return
        spot = row.get("close")
        if not spot or spot <= 0:
            return
        contract = find_best_contract(ticker, float(spot), direction)
        if not contract:
            return
        sc = score_setup(row, contract, direction)
        results.append(build_result(ticker, row, float(spot), contract, direction, sc))

    def process_overlay(ticker, direction, spot_override=None):
        spot = spot_override
        if spot is None:
            try:
                spot = yf.Ticker(ticker).fast_info.last_price
            except Exception:
                return
        if not spot or spot <= 0:
            return
        contract = find_best_contract(ticker, float(spot), direction)
        if not contract:
            return
        # Minimal stock data for scoring overlay tickers
        stock_data = {"RSI": None, "ADX": None, "Perf.3M": None,
                      "SMA50": None, "SMA200": None, "close": spot}
        try:
            tk   = yf.Ticker(ticker)
            hist = tk.history(period="200d", interval="1d", auto_adjust=True)
            if len(hist) >= 200:
                prices             = hist["Close"]
                stock_data["RSI"]  = _rsi(prices)
                stock_data["SMA50"]  = float(prices.tail(50).mean())
                stock_data["SMA200"] = float(prices.tail(200).mean())
                stock_data["Perf.3M"] = (float(prices.iloc[-1]) / float(prices.iloc[-63]) - 1) * 100
                stock_data["ADX"]    = _adx(hist)
        except Exception:
            pass
        sc = score_setup(stock_data, contract, direction)
        results.append(build_result(ticker, stock_data, float(spot), contract, direction, sc))

    def build_result(ticker, stock, spot, contract, direction, sc):
        label = "LONG CALL" if direction == "call" else "LONG PUT"
        return {
            "direction": direction,
            "label":     label,
            "grade":     grade(sc),
            "score":     sc,
            "ticker":    ticker,
            "company":   str(stock.get("description") or ticker)[:28].strip(),
            "sector":    str(stock.get("sector") or "").strip(),
            "spot":      round(spot, 2),
            "rsi":       round(float(stock["RSI"]), 1) if stock.get("RSI") else None,
            "adx":       round(float(stock["ADX"]), 1) if stock.get("ADX") else None,
            "perf_3m":   round(float(stock["Perf.3M"]), 1) if stock.get("Perf.3M") else None,
            "sma50":     round(float(stock["SMA50"]), 2) if stock.get("SMA50") else None,
            "sma200":    round(float(stock["SMA200"]), 2) if stock.get("SMA200") else None,
            **{f"opt_{k}": v for k, v in contract.items()},
        }

    # -- Step 1: TradingView screen (sorted by volume = most optionable first)
    if calls:
        call_df = screen_calls(limit=100)
        if not call_df.empty:
            tv_tickers = set()
            print(f"Analysing options chains for {len(call_df)} TV call candidates...")
            for _, row in call_df.iterrows():
                t = str(row.get("name","")).strip().upper()
                tv_tickers.add(t)
                process_tv_row(row, "call")
                time.sleep(0.1)

    if puts:
        put_df = screen_puts(limit=100)
        if not put_df.empty:
            tv_put_tickers = set()
            print(f"Analysing options chains for {len(put_df)} TV put candidates...")
            for _, row in put_df.iterrows():
                t = str(row.get("name","")).strip().upper()
                tv_put_tickers.add(t)
                process_tv_row(row, "put")
                time.sleep(0.1)

    # -- Step 2: Liquid overlay (mega-caps + ETFs always scanned)
    # Track separately per direction so the same ticker can appear as both call and put
    done_calls = {r["ticker"] for r in results if r["direction"] == "call"}
    done_puts  = {r["ticker"] for r in results if r["direction"] == "put"}

    if calls:
        overlay_calls = [t for t in LIQUID_OVERLAY_CALLS if t not in done_calls]
        print(f"\nScanning {len(overlay_calls)} liquid overlay names for calls...")
        for ticker in overlay_calls:
            process_overlay(ticker, "call")
            time.sleep(0.12)

    if puts:
        overlay_puts = [t for t in LIQUID_OVERLAY_PUTS if t not in done_puts]
        print(f"Scanning {len(overlay_puts)} liquid overlay names for puts...")
        for ticker in overlay_puts:
            process_overlay(ticker, "put")
            time.sleep(0.12)

    if not results:
        print("\nNo qualifying setups found today.")
        return []

    results.sort(key=lambda x: x["score"], reverse=True)

    # Deduplicate per (ticker, direction) — keep highest score
    seen: dict = {}
    for r in results:
        key = (r["ticker"], r["direction"])
        if key not in seen or r["score"] > seen[key]["score"]:
            seen[key] = r
    results = sorted(seen.values(), key=lambda x: x["score"], reverse=True)

    # -- Print results
    print()
    print("=" * 68)
    print(f"  TOP SETUPS  ({len(results)} total, showing top {min(top_n, len(results))})")
    print("=" * 68)

    shown = 0
    for r in results:
        if shown >= top_n:
            break
        shown += 1

        sma50  = r.get("sma50")  or 0
        sma200 = r.get("sma200") or 0
        if sma50 and sma200:
            trend_tag = "Golden X" if sma50 > sma200 else "Death X"
        else:
            trend_tag = ""

        rsi_str   = f"RSI:{r['rsi']}" if r.get("rsi") else "RSI:n/a"
        adx_str   = f"ADX:{r['adx']}" if r.get("adx") else ""
        p3m_str   = f"3M:{r['perf_3m']:+.1f}%" if r.get("perf_3m") else ""
        sma50_str = f"SMA50 ${sma50:.2f}" if sma50 else ""
        sma200_str= f"SMA200 ${sma200:.2f}" if sma200 else ""

        print()
        print(f"  [{r['grade']}] {r['label']}  {r['ticker']:7s} {r['company']}")
        print(f"       Score: {r['score']}/10   {r['sector']}")
        print(f"       Stock:  ${r['spot']:.2f}   {rsi_str}   {adx_str}   {p3m_str}   {trend_tag}")
        if sma50 or sma200:
            print(f"       MAs:    {sma50_str}   {sma200_str}")
        print()
        print(f"       Contract: ${r['opt_strike']:.0f} {r['label'].split()[1]}  exp {r['opt_expiry']}  ({r['opt_dte']} DTE)")
        print(f"       Price:    Bid ${r['opt_bid']:.2f}  Ask ${r['opt_ask']:.2f}  Mid ${r['opt_mid']:.2f}")
        print(f"       Cost:     ${r['opt_cost']:.0f} per contract (= 100 shares exposure)")
        print(f"       IV: {r['opt_iv']:.1%}   OI: {r['opt_oi']:,}   Vol: {r['opt_volume']:,}   Spread: {r['opt_spread_pct']:.1f}%")
        print(f"       Delta: {r['opt_delta']:+.3f}   Theta: ${r['opt_theta_day']*100:+.2f}/contract/day")
        print(f"       Strike {r['opt_otm_pct']:+.1f}% vs spot   Breakeven at expiry: ${r['opt_breakeven']:.2f}")
        stop = round(r["opt_mid"] * 0.50, 2)
        tgt  = round(r["opt_mid"] * 2.00, 2)
        print(f"       Stop: option at ${stop:.2f} (-50%)   Target: ${tgt:.2f} (+100%)")
        print(f"       " + "-" * 58)

    calls_out = [r for r in results if r["direction"] == "call"]
    puts_out  = [r for r in results if r["direction"] == "put"]
    aplus     = [r for r in results if r["grade"] == "A+"]
    a_grade   = [r for r in results if r["grade"] == "A"]

    print()
    print("=" * 68)
    print(f"  SUMMARY   Long Calls: {len(calls_out)}   Long Puts: {len(puts_out)}   "
          f"A+: {len(aplus)}   A: {len(a_grade)}")
    if aplus:
        print(f"  A+ setups: {', '.join(r['ticker'] for r in aplus)}")
    print(f"  {TODAY}")
    print("=" * 68)

    return results


# -- Helpers for overlay Greeks calculation ------------------------------------
def _rsi(prices, period=14):
    delta = prices.diff()
    up    = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
    down  = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean()
    rs    = up / down
    return float(100 - 100 / (1 + rs.iloc[-1]))


def _adx(hist, period=14):
    try:
        hi, lo, cl = hist["High"], hist["Low"], hist["Close"]
        tr  = pd.concat([hi - lo, (hi - cl.shift()).abs(), (lo - cl.shift()).abs()], axis=1).max(axis=1)
        dm_p = hi.diff().clip(lower=0)
        dm_n = (-lo.diff()).clip(lower=0)
        atr  = tr.ewm(com=period - 1, adjust=False).mean()
        dip  = (dm_p.ewm(com=period - 1, adjust=False).mean() / atr * 100)
        din  = (dm_n.ewm(com=period - 1, adjust=False).mean() / atr * 100)
        dx   = ((dip - din).abs() / (dip + din) * 100).ewm(com=period - 1, adjust=False).mean()
        return float(dx.iloc[-1])
    except Exception:
        return None


OUTPUT_DIR = r"C:\CANSLIM\DayTrader\outputs"


def run_and_save(calls=True, puts=True, top_n=15):
    """Run the scan and tee output to both console and a dated text file."""
    import io, os
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"options_scan_{TODAY}.txt")

    # Capture everything printed during run()
    buf = io.StringIO()
    old_stdout = sys.stdout

    class Tee:
        def write(self, data):
            old_stdout.write(data)
            buf.write(data)
        def flush(self):
            old_stdout.flush()

    sys.stdout = Tee()
    try:
        results = run(calls=calls, puts=puts, top_n=top_n)
    finally:
        sys.stdout = old_stdout

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(buf.getvalue())

    print(f"\nSaved to: {out_path}")

    # Save JSON for HTML dashboard generation
    import json
    json_path = os.path.join(OUTPUT_DIR, f"options_scan_{TODAY}.json")
    payload = {
        "date":      str(TODAY),
        "timestamp": datetime.datetime.now(_ET).strftime("%Y-%m-%d %H:%M ET"),
        "results":   results,
    }
    with open(json_path, "w", encoding="utf-8") as jf:
        json.dump(payload, jf, indent=2)
    print(f"JSON saved to: {json_path}")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--calls-only", action="store_true")
    parser.add_argument("--puts-only",  action="store_true")
    parser.add_argument("--top",        type=int, default=15)
    args = parser.parse_args()

    run_and_save(
        calls = not args.puts_only,
        puts  = not args.calls_only,
        top_n = args.top,
    )
