#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
screen_stocks.py — Direct TradingView screener + deterministic Python CANSLIM scoring.

Replaces the Claude + TradingView MCP screening step.
Outputs C:\\CANSLIM\\screen_output.json in the exact format notion_writer.py expects.

Usage:
    python C:\\CANSLIM\\screen_stocks.py
"""

import sys, os, re, json, math, datetime
import pandas as pd
from tradingview_screener import Query, col

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUTPUT_FILE = r"C:\CANSLIM\screen_output.json"
TODAY = datetime.date.today().isoformat()

# ── Columns to fetch from TradingView ─────────────────────────────────────────
COLUMNS = [
    "name",                                        # ticker symbol
    "description",                                 # company name
    "close",                                       # current price
    "exchange",
    "sector",
    "currency",
    "country",
    "market_cap_basic",                            # market cap in USD
    "earnings_per_share_diluted_yoy_growth_ttm",   # EPS growth %
    "total_revenue_yoy_growth_ttm",                # revenue growth %
    "return_on_equity",                            # ROE %
    "net_margin_ttm",                              # net margin %
    "Perf.3M",                                     # 3-month perf %
    "Perf.Y",                                      # 1-year perf %
    "Perf.YTD",                                    # YTD perf %
    "RSI",                                         # RSI (14)
    "ADX",                                         # ADX (14)
    "relative_volume_10d_calc",                    # relative volume vs 10d avg
    "price_52_week_high",                          # 52-week high price
    "recommendation_buy",                          # analyst buy count
    "Recommend.All",                               # overall rec score (-1 to +1)
    "price_target_average",                        # average analyst price target
    "SMA50",                                       # 50-day simple moving average
    "SMA200",                                      # 200-day simple moving average
    "average_volume_10d_calc",                     # 10-day avg volume (filter only)
]

# ── Screens ────────────────────────────────────────────────────────────────────

def run_us_screen():
    """US screen: strict CANSLIM filters, large caps, liquid."""
    print("Running US screen (america)...")
    try:
        _, df = (
            Query()
            .select(*COLUMNS)
            .where(
                col("earnings_per_share_diluted_yoy_growth_ttm") > 25,
                col("total_revenue_yoy_growth_ttm") > 10,
                col("return_on_equity") > 15,
                col("net_margin_ttm") > 8,
                col("Perf.3M") > 5,
                col("Perf.Y") > 15,
                col("RSI").between(45, 85),
                col("SMA50") > col("SMA200"),
                col("close") > col("SMA50"),
                col("market_cap_basic") > 500_000_000,
                col("average_volume_10d_calc") > 200_000,
            )
            .set_markets("america")
            .limit(500)
            .get_scanner_data()
        )
        print(f"  US screen: {len(df)} results")
        return df
    except Exception as e:
        print(f"  US screen error: {e}")
        return pd.DataFrame()


EU_MARKETS = [
    "switzerland",
    "uk", "germany", "france", "spain", "netherlands",
    "italy", "belgium", "norway", "denmark", "sweden",
    "finland", "poland", "ireland", "austria",
]


def run_eu_screen():
    """European + Swiss screens: combined, relaxed thresholds."""
    print("Running EU/Swiss screens...")
    frames = []
    for market in EU_MARKETS:
        try:
            _, df = (
                Query()
                .select(*COLUMNS)
                .where(
                    col("earnings_per_share_diluted_yoy_growth_ttm") > 15,
                    col("market_cap_basic") > 200_000_000,
                    col("return_on_equity") > 12,
                    col("net_margin_ttm") > 5,
                    col("Perf.3M") > 3,
                    col("Perf.Y") > 10,
                    col("RSI").between(40, 85),
                    col("close") > col("SMA50"),
                    col("SMA50") > col("SMA200"),
                    col("average_volume_10d_calc") > 10_000,
                )
                .set_markets(market)
                .limit(300)
                .get_scanner_data()
            )
            if not df.empty:
                frames.append(df)
        except Exception as e:
            print(f"  {market} error: {e}")

    if not frames:
        print("  EU/Swiss screen: 0 results")
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)

    # Drop Real Estate (negation not universally supported by screener API)
    if "sector" in combined.columns:
        combined = combined[combined["sector"].fillna("") != "Real Estate"]

    # Drop US-headquartered companies — they must go through US thresholds only.
    # German/GETTEX/Tradegate exchanges list US stocks but our EU filters are too lenient for them.
    if "country" in combined.columns:
        combined = combined[~combined["country"].str.upper().isin(["UNITED STATES", "CANADA"])]

    # Drop junk/OTC shadow exchanges — always duplicates of better primary listings
    JUNK_EXCHANGES = {"GETTEX", "TRADEGATE", "LSX", "FWB"}
    if "exchange" in combined.columns:
        combined = combined[~combined["exchange"].str.upper().isin(JUNK_EXCHANGES)]

    print(f"  EU/Swiss screen: {len(combined)} results (across {len(frames)} markets)")
    return combined


# ── IOB / depository line filter ───────────────────────────────────────────────
_IOB_RE = re.compile(r"^0[A-Z0-9]{3}$")

def _is_iob(ticker: str, exchange: str) -> bool:
    t = (ticker or "").split(":")[-1].strip().upper()
    return str(exchange).upper() in ("LSE", "LSIN") and bool(_IOB_RE.fullmatch(t))


# ── CANSLIM scoring ────────────────────────────────────────────────────────────

def _canslim_score(row: dict, is_us: bool, perf_y_p75: float | None) -> int:
    eps_thresh = 25 if is_us else 15
    roe_thresh = 15 if is_us else 12
    buy_thresh = 5  if is_us else 3

    eps     = row.get("earnings_per_share_diluted_yoy_growth_ttm")
    roe     = row.get("return_on_equity")
    price   = row.get("close")
    high52  = row.get("price_52_week_high")
    rel_vol = row.get("relative_volume_10d_calc")
    sma50   = row.get("SMA50")
    sma200  = row.get("SMA200")
    perf_y  = row.get("Perf.Y")
    buys    = row.get("recommendation_buy")

    score = 0
    # C — Current quarterly earnings
    if eps is not None and eps > eps_thresh:
        score += 1
    # A — Annual earnings / ROE
    if roe is not None and roe > roe_thresh:
        score += 1
    # N — New high: within 25% of 52-week high
    if price and high52 and high52 > 0 and price >= 0.75 * high52:
        score += 1
    # S — Supply/demand: volume strength + golden cross confirmed
    if (rel_vol is not None and rel_vol > 1.0
            and sma50 is not None and sma200 is not None and sma50 > sma200):
        score += 1
    # L — Leader: top quartile 1Y performance in this screen
    if perf_y is not None and perf_y_p75 is not None and perf_y >= perf_y_p75:
        score += 1
    # I — Institutional sponsorship: analyst buy count
    if buys is not None and buys >= buy_thresh:
        score += 1
    # M — Market direction: always 1 (stock passed uptrend filters to get here)
    score += 1

    return score


def _tier(score: int) -> str:
    if score >= 6: return "Tier 1"
    if score == 5: return "Tier 2"
    return "Tier 3"


def _verdict(score: int, rsi, recommend_all) -> str:
    # Flagged stocks still get a verdict; notion_writer overrides Status to Flagged
    tier = _tier(score)
    if tier == "Tier 1":
        return "Strong Buy" if (rsi is None or rsi < 75) else "Buy (wait)"
    if tier == "Tier 2":
        return "Buy"
    return "Watch"


# ── Row → output record ────────────────────────────────────────────────────────

def _f(v, dp=2):
    """Safe float round — converts NaN/Inf/None to None."""
    try:
        if v is None: return None
        fv = float(v)
        if math.isnan(fv) or math.isinf(fv): return None
        return round(fv, dp)
    except: return None

def _i(v):
    """Safe int — converts NaN/None to None."""
    try:
        if v is None: return None
        fv = float(v)
        if math.isnan(fv) or math.isinf(fv): return None
        return int(fv)
    except: return None


def _row_to_stock(row: dict, is_us: bool, perf_y_p75: float | None) -> dict | None:
    ticker   = str(row.get("name", "")).strip().upper()
    exchange = str(row.get("exchange", "")).strip().upper()

    if not ticker:
        return None
    if _is_iob(ticker, exchange):
        return None

    score = _canslim_score(row, is_us, perf_y_p75)
    rsi   = row.get("RSI")
    rec   = row.get("Recommend.All")
    price = row.get("close")
    mcap  = row.get("market_cap_basic")

    country_raw = str(row.get("country", "")).strip().title()
    if not country_raw:
        country_raw = "United States" if is_us else ""

    return {
        "ticker":        ticker,
        "exchange":      exchange,
        "country":       country_raw,
        "company":       str(row.get("description", ticker)).strip(),
        "sector":        str(row.get("sector", "")).strip(),
        "currency":      str(row.get("currency", "")).strip().upper(),
        "price":         _f(price, 4),
        "mcap_b":        _f(float(mcap) / 1e9, 3) if mcap else None,
        "score":         score,
        "tier":          _tier(score),
        "eps_growth":    _f(row.get("earnings_per_share_diluted_yoy_growth_ttm")),
        "rev_growth":    _f(row.get("total_revenue_yoy_growth_ttm")),
        "roe":           _f(row.get("return_on_equity")),
        "net_margin":    _f(row.get("net_margin_ttm")),
        "perf_3m":       _f(row.get("Perf.3M")),
        "perf_1y":       _f(row.get("Perf.Y")),
        "perf_ytd":      _f(row.get("Perf.YTD")),
        "rsi":           _f(rsi),
        "adx":           _f(row.get("ADX")),
        "rel_volume":    _f(row.get("relative_volume_10d_calc")),
        "ath_price":     _f(row.get("price_52_week_high")),
        "analyst_buys":  _i(row.get("recommendation_buy")),
        "price_target":  _f(row.get("price_target_average")),
        "recommend_all": _f(rec),
        "verdict":       _verdict(score, rsi, rec),
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print(f"CANSLIM Screen — {TODAY}")
    print("=" * 55)

    t0 = datetime.datetime.now()

    us_df = run_us_screen()
    eu_df = run_eu_screen()

    results = []
    seen    = set()   # dedupe by ticker within this run (cross-listing guard)

    # ── Process US ─────────────────────────────────────────────────────────────
    if not us_df.empty:
        p75_us = us_df["Perf.Y"].quantile(0.75) if "Perf.Y" in us_df.columns else None
        for _, row in us_df.iterrows():
            stock = _row_to_stock(row.to_dict(), is_us=True, perf_y_p75=p75_us)
            if stock and stock["ticker"] not in seen:
                results.append(stock)
                seen.add(stock["ticker"])

    # ── Process EU / Swiss ─────────────────────────────────────────────────────
    if not eu_df.empty:
        p75_eu = eu_df["Perf.Y"].quantile(0.75) if "Perf.Y" in eu_df.columns else None
        for _, row in eu_df.iterrows():
            stock = _row_to_stock(row.to_dict(), is_us=False, perf_y_p75=p75_eu)
            if stock and stock["ticker"] not in seen:
                results.append(stock)
                seen.add(stock["ticker"])

    # Sort: Tier 1 first, then by score desc
    results.sort(key=lambda x: x["score"], reverse=True)

    elapsed = (datetime.datetime.now() - t0).total_seconds()

    # ── Summary ────────────────────────────────────────────────────────────────
    tier1    = [r for r in results if r["tier"] == "Tier 1"]
    tier2    = [r for r in results if r["tier"] == "Tier 2"]
    tier3    = [r for r in results if r["tier"] == "Tier 3"]
    flagged  = [r for r in results if r.get("recommend_all") is not None and r["recommend_all"] < 0]
    overbought = [r for r in results if r.get("rsi") and r["rsi"] > 78]
    high_vol   = [r for r in results if r.get("rel_volume") and r["rel_volume"] > 3]

    us_count = sum(1 for r in results if r.get("country") == "US" or r.get("exchange") in ("NYSE","NASDAQ","CBOE"))
    eu_count = len(results) - us_count

    print(f"\n{'─'*55}")
    print(f"Total : {len(results)}  (US: {us_count}  EU/CH: {eu_count})")
    print(f"Tier 1: {len(tier1)}  Tier 2: {len(tier2)}  Tier 3: {len(tier3)}  Flagged: {len(flagged)}")
    print(f"Elapsed: {elapsed:.1f}s")
    print(f"{'─'*55}")

    print("\nTop stocks by score:")
    for r in results[:25]:
        flag = " [FLAGGED]" if r.get("recommend_all") is not None and r["recommend_all"] < 0 else ""
        print(f"  [{r['tier']}] {r['ticker']:8s} {r['company'][:28]:28s}"
              f"  Score:{r['score']}  RSI:{r.get('rsi') or '?':5}  RVOL:{r.get('rel_volume') or '?'}{flag}")

    if overbought:
        print(f"\nOverbought RSI>78 : {', '.join(r['ticker'] for r in overbought)}")
    if high_vol:
        print(f"Volume spike >3x  : {', '.join(r['ticker'] for r in high_vol)}")

    # ── Write output ───────────────────────────────────────────────────────────
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)

    size = os.path.getsize(OUTPUT_FILE)
    print(f"\nWrote {len(results)} stocks → {OUTPUT_FILE} ({size:,} bytes)")
    print("Hand-off complete. Run notion_writer.py to update Notion.")

if __name__ == "__main__":
    main()
