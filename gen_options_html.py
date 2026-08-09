#!/usr/bin/env python3
"""
gen_options_html.py — Generate Options Dashboard HTML from scan_options JSON output.
Run after scan_options.py, or import and call generate_and_save(results, timestamp).
"""
import json, os, math, datetime
from pathlib import Path

try:
    import zoneinfo
    _ET = zoneinfo.ZoneInfo("America/New_York")
except ImportError:
    _ET = None

OUTPUT_DIR = Path(r"C:\CANSLIM\DayTrader\outputs")
DASH_PATH  = Path(r"C:\CANSLIM\Options_Dashboard.html")
TV_BASE    = "https://www.tradingview.com/chart/?symbol="


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _f(val, fmt="", prefix="", suffix="", na="—"):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return na
    try:
        return f"{prefix}{val:{fmt}}{suffix}"
    except Exception:
        return str(val)


def _grade_badge(grade):
    css = {"A+": "aplus", "A": "a", "B": "b", "C": "c"}.get(grade, "c")
    return f'<span class="grade grade-{css}">{grade}</span>'


def _rsi_class(rsi, direction):
    if rsi is None:
        return ""
    if direction == "call" and 52 <= rsi <= 65:
        return "val-good"
    if direction == "put" and 28 <= rsi <= 48:
        return "val-good"
    if direction == "call" and rsi > 73:
        return "val-warn"
    if direction == "put" and rsi < 20:
        return "val-warn"
    return ""


def _iv_class(iv):
    if iv < 0.25: return "iv-low"
    if iv < 0.40: return "iv-mid"
    return "iv-high"


def _delta_bar(delta, direction):
    pct = min(100, abs(delta) / 0.65 * 100)
    col = "#3fb950" if direction == "call" else "#f85149"
    return (f'<div class="dbar-wrap">'
            f'<div class="dbar" style="width:{pct:.0f}%;background:{col}"></div>'
            f'</div>')


def _score_dots(score):
    return "".join(
        '<span class="dot dot-on"></span>' if i < score
        else '<span class="dot dot-off"></span>'
        for i in range(10)
    )


def _render_card(r):
    direction = r["direction"]
    is_call   = direction == "call"
    dc        = "call" if is_call else "put"
    dir_lbl   = "LONG CALL" if is_call else "LONG PUT"
    grade     = r.get("grade", "C")
    ticker    = r.get("ticker", "")
    company   = r.get("company", ticker)
    sector    = r.get("sector", "")
    score     = r.get("score", 0)

    spot   = r.get("spot")
    rsi    = r.get("rsi")
    adx    = r.get("adx")
    p3m    = r.get("perf_3m")
    sma50  = r.get("sma50")
    sma200 = r.get("sma200")

    expiry = r.get("opt_expiry", "")
    dte    = r.get("opt_dte", 0)
    strike = r.get("opt_strike")
    bid    = r.get("opt_bid")
    ask    = r.get("opt_ask")
    mid    = r.get("opt_mid")
    iv     = r.get("opt_iv", 0)
    oi     = r.get("opt_oi", 0)
    vol    = r.get("opt_volume", 0)
    spread = r.get("opt_spread_pct")
    delta  = r.get("opt_delta", 0)
    theta  = r.get("opt_theta_day", 0)
    vega   = r.get("opt_vega", 0)
    cost   = r.get("opt_cost")
    be     = r.get("opt_breakeven")
    otm    = r.get("opt_otm_pct")

    stop_px   = round(mid * 0.50, 2) if mid else None
    target_px = round(mid * 2.00, 2) if mid else None
    sma_gap   = ((sma50 / sma200 - 1) * 100) if (sma50 and sma200) else None
    be_vs_spot = ((be / spot - 1) * 100) if (be and spot) else None

    p3m_cls   = "val-pos" if (p3m and p3m > 0) else "val-neg"
    rsi_cls   = _rsi_class(rsi, direction)
    iv_cls    = _iv_class(iv) if iv else ""

    # Trend tag
    if sma50 and sma200:
        if sma50 > sma200:
            trend_tag = '<span class="tag tag-call">Golden Cross</span>'
        else:
            trend_tag = '<span class="tag tag-put">Death Cross</span>'
    else:
        trend_tag = ""

    sector_tag = f'<span class="tag tag-sector">{sector}</span>' if sector else ""
    theta_per_contract = theta * 100 if theta else None
    dte_urgent = "dte-urgent" if dte and dte <= 20 else ""

    theta_cost = abs((theta or 0) * 100)
    vega_cost  = (vega or 0) * 100

    return f"""
<div class="card card-{dc}" data-direction="{direction}" data-grade="{grade}" data-score="{score}" data-iv="{iv or 0}" data-delta="{abs(delta or 0):.3f}" data-oi="{oi or 0}" data-spread="{spread or 99}" data-theta="{theta_cost:.2f}">
  <div class="card-top">
    <div class="top-left">
      <span class="dir-pill dir-{dc}">{dir_lbl}</span>
      <a href="{TV_BASE}{ticker}" target="_blank" class="ticker">{ticker}</a>
      <span class="company">{company}</span>
    </div>
    <div class="top-right">
      {_grade_badge(grade)}
      <div class="score-dots">{_score_dots(score)}</div>
    </div>
  </div>

  <div class="tags-row">{trend_tag}{sector_tag}</div>

  <div class="body-grid">
    <div class="col-stock">
      <div class="col-label">STOCK</div>
      <div class="spot">${_f(spot, ".2f")}</div>
      <div class="stat-row">
        <div class="stat">
          <div class="stat-lbl">RSI</div>
          <div class="stat-val {rsi_cls}">{_f(rsi, ".1f")}</div>
        </div>
        <div class="stat">
          <div class="stat-lbl">ADX</div>
          <div class="stat-val">{_f(adx, ".1f")}</div>
        </div>
        <div class="stat">
          <div class="stat-lbl">3M Perf</div>
          <div class="stat-val {p3m_cls}">{_f(p3m, "+.1f", suffix="%")}</div>
        </div>
      </div>
      <div class="ma-row">
        <div class="ma-item"><span class="ma-lbl">SMA50</span> <span class="ma-val">${_f(sma50, ".2f")}</span></div>
        <div class="ma-item"><span class="ma-lbl">SMA200</span> <span class="ma-val">${_f(sma200, ".2f")}</span></div>
        {f'<div class="ma-gap">Gap {_f(sma_gap, "+.1f")}%</div>' if sma_gap is not None else ""}
      </div>
    </div>

    <div class="col-opts">
      <div class="col-label">OPTIONS CONTRACT</div>
      <div class="expiry-row">
        <span class="expiry-date">{expiry}</span>
        <span class="dte-badge {dte_urgent}">{dte}d DTE</span>
      </div>
      <div class="strike-row">
        <span class="strike-lbl">Strike</span>
        <span class="strike-val">${_f(strike, ".0f")}</span>
        {f'<span class="otm">({_f(otm, "+.1f")}% OTM)</span>' if otm is not None else ""}
      </div>
      <div class="bid-ask-grid">
        <div class="ba-item"><div class="ba-lbl">Bid</div><div class="ba-val">${_f(bid, ".2f")}</div></div>
        <div class="ba-item"><div class="ba-lbl">Ask</div><div class="ba-val">${_f(ask, ".2f")}</div></div>
        <div class="ba-item ba-mid"><div class="ba-lbl">Mid</div><div class="ba-val">${_f(mid, ".2f")}</div></div>
      </div>
      <div class="cost-box">
        <span class="cost-lbl">Cost per contract</span>
        <span class="cost-val">${_f(cost, ".0f")}</span>
      </div>
    </div>
  </div>

  <div class="greeks-strip">
    <div class="greek-item greek-delta">
      <div class="greek-lbl">Delta</div>
      <div class="greek-val">{_f(delta, "+.3f")}</div>
      {_delta_bar(delta, direction)}
    </div>
    <div class="greek-item">
      <div class="greek-lbl">Theta / day</div>
      <div class="greek-val theta-val">{_f(theta_per_contract, "+.2f", prefix="$")}</div>
    </div>
    <div class="greek-item">
      <div class="greek-lbl">Vega / 1% IV</div>
      <div class="greek-val vega-val">{_f(vega_cost, "+.2f", prefix="$")}</div>
    </div>
    <div class="greek-item">
      <div class="greek-lbl">IV</div>
      <div class="greek-val {iv_cls}">{_f(iv * 100 if iv else None, ".1f", suffix="%")}</div>
    </div>
    <div class="greek-item">
      <div class="greek-lbl">Open Interest</div>
      <div class="greek-val">{_f(oi, ",")}</div>
    </div>
    <div class="greek-item">
      <div class="greek-lbl">Spread</div>
      <div class="greek-val">{_f(spread, ".1f", suffix="%")}</div>
    </div>
  </div>

  <div class="risk-strip">
    <div class="risk-item">
      <div class="risk-lbl">Breakeven at expiry</div>
      <div class="risk-val">${_f(be, ".2f")}{f" <span class='be-pct'>({_f(be_vs_spot, '+.1f')}%)</span>" if be_vs_spot else ""}</div>
    </div>
    <div class="risk-item risk-stop">
      <div class="risk-lbl">Stop Loss (-50%)</div>
      <div class="risk-val">${_f(stop_px, ".2f")}</div>
    </div>
    <div class="risk-item risk-target">
      <div class="risk-lbl">Target (+100%)</div>
      <div class="risk-val">${_f(target_px, ".2f")}</div>
    </div>
  </div>
</div>"""


def generate(results, timestamp):
    calls  = [r for r in results if r["direction"] == "call"]
    puts   = [r for r in results if r["direction"] == "put"]
    aplus  = [r for r in results if r["grade"] == "A+"]
    a_gr   = [r for r in results if r["grade"] == "A"]

    aplus_html = ""
    if aplus:
        tickers = " &nbsp;|&nbsp; ".join(
            f'<a href="{TV_BASE}{r["ticker"]}" target="_blank" class="aplus-ticker">{r["ticker"]}</a>'
            for r in aplus
        )
        aplus_html = f'<div class="aplus-banner"><span class="aplus-label">A+ SETUPS</span>{tickers}</div>'

    cards_html = "\n".join(_render_card(r) for r in results)
    today_str  = datetime.date.today().strftime("%d %b %Y")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Options Dashboard {today_str}</title>
<style>
:root {{
  --bg:          #0d1117;
  --bg-card:     #161b22;
  --bg-card-hov: #1c2128;
  --border:      #30363d;
  --border-light:#21262d;
  --txt:         #e6edf3;
  --txt2:        #8b949e;
  --txt3:        #6e7681;
  --call:        #2ea043;
  --call-bright: #3fb950;
  --call-dim:    rgba(46,160,67,0.12);
  --put:         #da3633;
  --put-bright:  #f85149;
  --put-dim:     rgba(218,54,51,0.12);
  --aplus:       #e3b341;
  --a-grade:     #388bfd;
  --b-grade:     #d29922;
  --c-grade:     #6e7681;
  --stop-red:    #f85149;
  --tgt-green:   #3fb950;
  --theta-amber: #d29922;
}}
@media (prefers-color-scheme: light) {{
  :root {{
    --bg:          #f6f8fa;
    --bg-card:     #ffffff;
    --bg-card-hov: #f0f4f8;
    --border:      #d0d7de;
    --border-light:#e1e4e8;
    --txt:         #1f2328;
    --txt2:        #57606a;
    --txt3:        #8c959f;
    --call:        #1a7f37;
    --call-bright: #2da44e;
    --call-dim:    rgba(26,127,55,0.08);
    --put:         #cf222e;
    --put-bright:  #d1242f;
    --put-dim:     rgba(207,34,46,0.08);
  }}
}}
:root[data-theme="light"] {{
  --bg: #f6f8fa; --bg-card: #ffffff; --bg-card-hov: #f0f4f8;
  --border: #d0d7de; --border-light: #e1e4e8;
  --txt: #1f2328; --txt2: #57606a; --txt3: #8c959f;
  --call: #1a7f37; --call-bright: #2da44e; --call-dim: rgba(26,127,55,0.08);
  --put: #cf222e; --put-bright: #d1242f; --put-dim: rgba(207,34,46,0.08);
}}
:root[data-theme="dark"] {{
  --bg: #0d1117; --bg-card: #161b22; --bg-card-hov: #1c2128;
  --border: #30363d; --border-light: #21262d;
  --txt: #e6edf3; --txt2: #8b949e; --txt3: #6e7681;
  --call: #2ea043; --call-bright: #3fb950; --call-dim: rgba(46,160,67,0.12);
  --put: #da3633; --put-bright: #f85149; --put-dim: rgba(218,54,51,0.12);
}}

*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  background: var(--bg);
  color: var(--txt);
  min-height: 100vh;
  font-size: 14px;
  line-height: 1.5;
}}
a {{ color: inherit; text-decoration: none; }}

/* ── Header ── */
.header {{
  padding: 20px 24px 0;
  border-bottom: 1px solid var(--border);
  background: var(--bg-card);
}}
.header-top {{
  display: flex;
  align-items: baseline;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}}
.header-top h1 {{
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.3px;
}}
.scan-meta {{ color: var(--txt2); font-size: 13px; }}
.theme-btn {{
  margin-left: auto;
  background: none;
  border: 1px solid var(--border);
  color: var(--txt2);
  border-radius: 6px;
  padding: 4px 10px;
  cursor: pointer;
  font-size: 12px;
}}
.theme-btn:hover {{ border-color: var(--txt2); }}

.stat-bar {{
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  padding-bottom: 16px;
}}
.stat-box {{
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 14px;
  min-width: 90px;
  text-align: center;
}}
.stat-box .sb-num {{
  font-size: 20px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}}
.stat-box .sb-lbl {{
  font-size: 11px;
  color: var(--txt2);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}}
.stat-box.green .sb-num {{ color: var(--call-bright); }}
.stat-box.red   .sb-num {{ color: var(--put-bright); }}
.stat-box.gold  .sb-num {{ color: var(--aplus); }}
.stat-box.blue  .sb-num {{ color: var(--a-grade); }}

/* ── A+ Banner ── */
.aplus-banner {{
  background: linear-gradient(90deg, rgba(227,179,65,0.15) 0%, transparent 100%);
  border-left: 3px solid var(--aplus);
  padding: 10px 24px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 13px;
}}
.aplus-label {{
  font-weight: 700;
  color: var(--aplus);
  font-size: 11px;
  letter-spacing: 1px;
  text-transform: uppercase;
  white-space: nowrap;
}}
.aplus-ticker {{
  color: var(--aplus);
  font-weight: 600;
}}
.aplus-ticker:hover {{ text-decoration: underline; }}

/* ── Controls ── */
.controls {{
  padding: 16px 24px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
  border-bottom: 1px solid var(--border);
  background: var(--bg-card);
}}
.tab-btn {{
  background: none;
  border: 1px solid var(--border);
  color: var(--txt2);
  border-radius: 20px;
  padding: 5px 14px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.15s;
}}
.tab-btn:hover {{ border-color: var(--txt); color: var(--txt); }}
.tab-btn.active {{
  background: var(--txt);
  color: var(--bg);
  border-color: var(--txt);
  font-weight: 600;
}}
.tab-btn.active.tab-call {{ background: var(--call); border-color: var(--call); color: #fff; }}
.tab-btn.active.tab-put  {{ background: var(--put);  border-color: var(--put);  color: #fff; }}
.tab-btn.active.tab-aplus {{ background: var(--aplus); border-color: var(--aplus); color: #0d1117; }}
.tab-btn.tab-top5 {{ border-color: var(--put-bright); color: var(--put-bright); font-weight: 700; }}
.tab-btn.active.tab-top5 {{ background: var(--put-bright); border-color: var(--put-bright); color: #fff; }}
.count-tag {{ color: var(--txt3); font-size: 11px; margin-left: 2px; }}
.sort-lbl {{ margin-left: auto; font-size: 12px; color: var(--txt3); }}

/* ── Grid ── */
.grid {{ padding: 20px 24px; display: grid; grid-template-columns: repeat(auto-fill, minmax(520px, 1fr)); gap: 16px; }}
@media (max-width: 580px) {{ .grid {{ padding: 12px; grid-template-columns: 1fr; }} }}

/* ── Card ── */
.card {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  transition: box-shadow 0.15s;
}}
.card:hover {{ box-shadow: 0 4px 20px rgba(0,0,0,0.25); }}
.card-call {{ border-left: 3px solid var(--call); }}
.card-put  {{ border-left: 3px solid var(--put);  }}

/* Card top */
.card-top {{
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 14px 16px 6px;
  gap: 12px;
}}
.top-left {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
.dir-pill {{
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.8px;
  text-transform: uppercase;
  border-radius: 4px;
  padding: 2px 7px;
  white-space: nowrap;
}}
.dir-call {{ background: var(--call-dim); color: var(--call-bright); border: 1px solid var(--call); }}
.dir-put  {{ background: var(--put-dim);  color: var(--put-bright);  border: 1px solid var(--put); }}
.ticker {{
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.5px;
  color: var(--txt);
}}
.ticker:hover {{ color: var(--a-grade); }}
.company {{ font-size: 12px; color: var(--txt2); }}

.top-right {{ display: flex; flex-direction: column; align-items: flex-end; gap: 6px; flex-shrink: 0; }}
.grade {{
  font-size: 14px;
  font-weight: 800;
  border-radius: 6px;
  padding: 3px 10px;
  letter-spacing: 0.5px;
}}
.grade-aplus {{ background: rgba(227,179,65,0.2); color: var(--aplus); border: 1px solid var(--aplus); }}
.grade-a     {{ background: rgba(56,139,253,0.15); color: var(--a-grade); border: 1px solid var(--a-grade); }}
.grade-b     {{ background: rgba(210,153,34,0.15); color: var(--b-grade); border: 1px solid var(--b-grade); }}
.grade-c     {{ background: rgba(110,118,129,0.15); color: var(--c-grade); border: 1px solid var(--c-grade); }}
.score-dots {{ display: flex; gap: 3px; }}
.dot {{ width: 7px; height: 7px; border-radius: 50%; }}
.dot-on  {{ background: var(--txt2); }}
.dot-off {{ background: var(--border); }}

/* Tags */
.tags-row {{ display: flex; gap: 6px; flex-wrap: wrap; padding: 0 16px 10px; }}
.tag {{
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.5px;
  border-radius: 4px;
  padding: 2px 7px;
  text-transform: uppercase;
}}
.tag-call   {{ background: var(--call-dim); color: var(--call-bright); }}
.tag-put    {{ background: var(--put-dim);  color: var(--put-bright); }}
.tag-sector {{ background: var(--bg); color: var(--txt3); border: 1px solid var(--border); }}

/* Body grid */
.body-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0;
  border-top: 1px solid var(--border-light);
  border-bottom: 1px solid var(--border-light);
}}
.col-stock, .col-opts {{ padding: 12px 16px; }}
.col-stock {{ border-right: 1px solid var(--border-light); }}
.col-label {{
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: var(--txt3);
  margin-bottom: 8px;
}}
.spot {{
  font-size: 26px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  letter-spacing: -1px;
  margin-bottom: 8px;
}}
.stat-row {{ display: flex; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }}
.stat .stat-lbl {{ font-size: 10px; color: var(--txt3); text-transform: uppercase; letter-spacing: 0.5px; }}
.stat .stat-val {{
  font-size: 15px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}}
.val-good {{ color: var(--call-bright); }}
.val-warn {{ color: var(--put-bright); }}
.val-pos  {{ color: var(--call-bright); }}
.val-neg  {{ color: var(--put-bright); }}

.ma-row {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; font-size: 12px; }}
.ma-lbl {{ color: var(--txt3); }}
.ma-val {{ font-weight: 600; font-variant-numeric: tabular-nums; }}
.ma-gap {{ color: var(--txt3); font-size: 11px; }}

.expiry-row {{ display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }}
.expiry-date {{ font-size: 14px; font-weight: 600; }}
.dte-badge {{
  font-size: 11px;
  font-weight: 700;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 2px 8px;
  color: var(--txt2);
}}
.dte-urgent {{ background: rgba(248,81,73,0.15); border-color: var(--put); color: var(--put-bright); }}

.strike-row {{ display: flex; align-items: baseline; gap: 8px; margin-bottom: 8px; }}
.strike-lbl {{ font-size: 11px; color: var(--txt3); text-transform: uppercase; letter-spacing: 0.5px; }}
.strike-val {{ font-size: 20px; font-weight: 800; font-variant-numeric: tabular-nums; }}
.otm {{ font-size: 12px; color: var(--txt2); }}

.bid-ask-grid {{ display: flex; gap: 0; margin-bottom: 8px; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }}
.ba-item {{ flex: 1; padding: 6px 8px; text-align: center; }}
.ba-item + .ba-item {{ border-left: 1px solid var(--border); }}
.ba-mid {{ background: var(--bg); }}
.ba-lbl {{ font-size: 10px; color: var(--txt3); text-transform: uppercase; letter-spacing: 0.5px; }}
.ba-val {{ font-size: 14px; font-weight: 700; font-variant-numeric: tabular-nums; }}

.cost-box {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 12px;
}}
.cost-lbl {{ font-size: 11px; color: var(--txt2); }}
.cost-val {{ font-size: 18px; font-weight: 800; font-variant-numeric: tabular-nums; }}

/* Greeks strip */
.greeks-strip {{
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  border-bottom: 1px solid var(--border-light);
  background: var(--bg);
}}
@media (max-width: 620px) {{ .greeks-strip {{ grid-template-columns: repeat(3, 1fr); }} }}
.greek-item {{ padding: 8px 12px; border-right: 1px solid var(--border-light); }}
.greek-item:last-child {{ border-right: none; }}
.greek-lbl {{ font-size: 9px; color: var(--txt3); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 3px; }}
.greek-val {{ font-size: 13px; font-weight: 700; font-variant-numeric: tabular-nums; }}
.theta-val {{ color: var(--theta-amber); }}
.vega-val  {{ color: var(--call-bright); }}
.iv-low  {{ color: var(--call-bright); }}
.iv-mid  {{ color: var(--b-grade); }}
.iv-high {{ color: var(--put-bright); }}
.dbar-wrap {{ height: 3px; background: var(--border); border-radius: 2px; margin-top: 5px; overflow: hidden; }}
.dbar {{ height: 100%; border-radius: 2px; transition: width 0.3s; }}

/* Risk strip */
.risk-strip {{
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  padding: 10px 0;
}}
.risk-item {{ padding: 4px 14px; border-right: 1px solid var(--border-light); }}
.risk-item:last-child {{ border-right: none; }}
.risk-lbl {{ font-size: 9px; color: var(--txt3); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px; }}
.risk-val {{ font-size: 13px; font-weight: 700; font-variant-numeric: tabular-nums; }}
.be-pct {{ font-size: 11px; font-weight: 400; color: var(--txt2); }}
.risk-stop .risk-val  {{ color: var(--stop-red); }}
.risk-target .risk-val {{ color: var(--tgt-green); }}

/* Footer */
.footer {{
  margin: 0 24px 32px;
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-card);
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}}
@media (max-width: 620px) {{ .footer {{ grid-template-columns: 1fr; }} }}
.footer h3 {{ font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: var(--txt2); margin-bottom: 8px; }}
.footer ul {{ list-style: none; display: flex; flex-direction: column; gap: 5px; }}
.footer li {{ font-size: 12px; color: var(--txt2); padding-left: 10px; position: relative; }}
.footer li::before {{ content: "-"; position: absolute; left: 0; color: var(--txt3); }}
.params {{ font-size: 11px; color: var(--txt3); line-height: 1.8; }}
.params span {{ display: block; }}
.na {{ color: var(--txt3); }}
.hidden {{ display: none !important; }}
.rank-badge {{
  font-size: 11px;
  font-weight: 800;
  background: var(--put-bright);
  color: #fff;
  border-radius: 4px;
  padding: 2px 7px;
  letter-spacing: 0.5px;
  flex-shrink: 0;
}}
</style>
</head>
<body>

<div class="header">
  <div class="header-top">
    <h1>Options Dashboard</h1>
    <span class="scan-meta">Scan: {timestamp} &nbsp;|&nbsp; Target DTE ~37 days</span>
    <button class="theme-btn" onclick="toggleTheme()">Toggle Theme</button>
  </div>
  <div class="stat-bar">
    <div class="stat-box">
      <div class="sb-num">{len(results)}</div>
      <div class="sb-lbl">Total Setups</div>
    </div>
    <div class="stat-box green">
      <div class="sb-num">{len(calls)}</div>
      <div class="sb-lbl">Long Calls</div>
    </div>
    <div class="stat-box red">
      <div class="sb-num">{len(puts)}</div>
      <div class="sb-lbl">Long Puts</div>
    </div>
    <div class="stat-box gold">
      <div class="sb-num">{len(aplus)}</div>
      <div class="sb-lbl">Grade A+</div>
    </div>
    <div class="stat-box blue">
      <div class="sb-num">{len(a_gr)}</div>
      <div class="sb-lbl">Grade A</div>
    </div>
  </div>
</div>

{aplus_html}

<div class="controls">
  <button class="tab-btn active" data-filter="all" onclick="filter(this,'all')">
    All <span class="count-tag">({len(results)})</span>
  </button>
  <button class="tab-btn tab-call" data-filter="call" onclick="filter(this,'call')">
    Long Calls <span class="count-tag">({len(calls)})</span>
  </button>
  <button class="tab-btn tab-put" data-filter="put" onclick="filter(this,'put')">
    Long Puts <span class="count-tag">({len(puts)})</span>
  </button>
  <button class="tab-btn tab-aplus" data-filter="aplus" onclick="filter(this,'aplus')">
    A+ Only <span class="count-tag">({len(aplus)})</span>
  </button>
  <button class="tab-btn tab-top5" data-filter="top5" onclick="filterTop5(this)">
    Top 5
  </button>
  <span class="sort-lbl">Sorted by score (highest first)</span>
</div>

<div class="grid" id="cards">
{cards_html}
</div>

<div class="footer">
  <div>
    <h3>Exit Rules</h3>
    <ul>
      <li>Stop loss: close if option loses 50% of premium paid</li>
      <li>Take profit: sell half position at +100%, let rest run with floor</li>
      <li>Time stop: exit all remaining at 14 DTE regardless of P&L</li>
      <li>Floor: raise your stop floor as position moves in your favour</li>
    </ul>
  </div>
  <div>
    <h3>Scanner Parameters</h3>
    <div class="params">
      <span>DTE target: 25-65 days (ideal 37)</span>
      <span>Delta range: 0.28 - 0.52</span>
      <span>Max IV filter: 70%</span>
      <span>Max bid/ask spread: 25% of mid</span>
      <span>Min open interest: 25 contracts</span>
      <span>OTM range: -1% to +8% from spot</span>
    </div>
  </div>
</div>

<script>
function filter(btn, val) {{
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  document.querySelectorAll(".card").forEach(card => {{
    const dir   = card.dataset.direction;
    const grade = card.dataset.grade;
    if (val === "all")        card.classList.remove("hidden");
    else if (val === "call")  card.classList.toggle("hidden", dir !== "call");
    else if (val === "put")   card.classList.toggle("hidden", dir !== "put");
    else if (val === "aplus") card.classList.toggle("hidden", grade !== "A+");
  }});
}}

function filterTop5(btn) {{
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");

  // Score each A+ card on Greek quality
  const cards = Array.from(document.querySelectorAll(".card"));
  const aplus = cards.filter(c => c.dataset.grade === "A+");

  const ranked = aplus.map(card => {{
    const score  = parseFloat(card.dataset.score  || 0);
    const iv     = parseFloat(card.dataset.iv     || 0.99);
    const delta  = parseFloat(card.dataset.delta  || 0);
    const oi     = parseInt(  card.dataset.oi     || 0);
    const spread = parseFloat(card.dataset.spread || 99);
    const theta  = parseFloat(card.dataset.theta  || 99);

    let elite = score * 2;                          // base: 16-20 pts

    // IV — lower means cheaper entry and less crush risk
    if      (iv < 0.25) elite += 4;
    else if (iv < 0.35) elite += 3;
    else if (iv < 0.45) elite += 2;
    else if (iv < 0.55) elite += 1;

    // Delta sweet spot 0.38–0.48 (balanced exposure)
    if      (delta >= 0.38 && delta <= 0.48) elite += 3;
    else if (delta >= 0.30 && delta <= 0.55) elite += 1;

    // Liquidity — higher OI = easier fills
    if      (oi > 2000) elite += 3;
    else if (oi > 500)  elite += 2;
    else if (oi > 100)  elite += 1;

    // Spread — tighter means closer to mid on entry
    if      (spread < 5)  elite += 3;
    else if (spread < 10) elite += 2;
    else if (spread < 15) elite += 1;

    // Theta cost — lower daily decay = more time cushion
    if      (theta < 8)  elite += 2;
    else if (theta < 20) elite += 1;

    return {{ card, elite }};
  }}).sort((a, b) => b.elite - a.elite);

  // Hide all, show top 5 only
  cards.forEach(c => c.classList.add("hidden"));
  ranked.slice(0, 5).forEach((r, i) => {{
    r.card.classList.remove("hidden");
    // Add rank badge temporarily
    let existing = r.card.querySelector(".rank-badge");
    if (!existing) {{
      const badge = document.createElement("div");
      badge.className = "rank-badge";
      badge.textContent = "#" + (i + 1);
      r.card.querySelector(".card-top").prepend(badge);
    }} else {{
      existing.textContent = "#" + (i + 1);
    }}
  }});
}}

function toggleTheme() {{
  const r = document.documentElement;
  const current = r.getAttribute("data-theme");
  if (current === "light") r.setAttribute("data-theme","dark");
  else if (current === "dark") r.setAttribute("data-theme","light");
  else {{
    const isDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    r.setAttribute("data-theme", isDark ? "light" : "dark");
  }}
}}
</script>
</body>
</html>"""


def load_results():
    today = datetime.date.today().isoformat()
    json_path = OUTPUT_DIR / f"options_scan_{today}.json"
    if not json_path.exists():
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        json_path = OUTPUT_DIR / f"options_scan_{yesterday}.json"
    if not json_path.exists():
        return [], "No scan data found"
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("results", []), data.get("timestamp", today)


def generate_and_save(results=None, timestamp=None):
    if results is None:
        results, timestamp = load_results()
    if not timestamp:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    html = generate(results, timestamp)
    DASH_PATH.write_text(html, encoding="utf-8")
    print(f"Options dashboard saved: {DASH_PATH}")
    return DASH_PATH


if __name__ == "__main__":
    path = generate_and_save()
    print(f"Done: {path}")
