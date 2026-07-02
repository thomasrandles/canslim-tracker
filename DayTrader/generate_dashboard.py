"""
generate_dashboard.py — Reads all scan outputs and produces a single HTML dashboard.
Run after any scanner to update the page.
"""
import json, os, sys
from datetime import datetime
import pytz

ET_TZ = pytz.timezone("US/Eastern")
BASE  = os.path.dirname(__file__)
OUT   = os.path.join(BASE, "outputs")
DASH  = os.path.join(BASE, "DayTrader_Dashboard.html")

SCANS = [
    ("premarket", "Pre-Market Gaps",     "🌙", "7–9 AM ET"),
    ("opening",   "Opening Bell",        "🔔", "9:35 AM ET"),
    ("midday",    "Mid-Day Squeeze",     "☀️",  "1:30 PM ET"),
    ("powerhour", "Power Hour Momentum", "⚡",  "3:00 PM ET"),
]

GRADE_CSS = {
    "A+": "grade-aplus",
    "A":  "grade-a",
    "B":  "grade-b",
    "C":  "grade-c",
}

TV_BASE = "https://www.tradingview.com/chart/?symbol="

def load_scan(name: str) -> dict | None:
    path = os.path.join(OUT, f"{name}_latest.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def fmt(val, fmt_str: str = "", suffix: str = "", prefix: str = "") -> str:
    if val is None: return "<span class='na'>—</span>"
    try:
        return f"{prefix}{val:{fmt_str}}{suffix}"
    except Exception:
        return str(val)

def direction_badge(direction: str) -> str:
    if direction == "LONG":
        return "<span class='badge badge-long'>LONG</span>"
    return "<span class='badge badge-short'>SHORT</span>"

def render_reasons(reasons: list) -> str:
    if not reasons: return ""
    items = "".join(f"<span class='tag'>{r}</span>" for r in reasons)
    return f"<div class='tags'>{items}</div>"

def render_scan_table(scan_name: str, data: dict) -> str:
    results = data.get("results", [])
    ts      = data.get("timestamp", "")
    count   = data.get("count", 0)
    aplus   = [r for r in results if r.get("grade") == "A+"]

    rows = ""
    for r in results[:20]:   # show top 20
        grade = r.get("grade", "C")
        gcss  = GRADE_CSS.get(grade, "grade-c")
        tv_link = f"https://www.tradingview.com/chart/?symbol={r['ticker']}"

        if scan_name == "premarket":
            dir_badge = direction_badge(r.get("direction", "LONG"))
            extra = f"""
              <td>{fmt(r.get('gap_pct'), '+.1f', '%')}</td>
              <td>{fmt(r.get('pm_rvol'), '.1f', '×')}</td>
              <td>{fmt(r.get('pm_volume'), ',')}</td>
              <td>{dir_badge}</td>
            """
            cols_extra = "<th>Gap %</th><th>PM RVOL</th><th>PM Vol</th><th>Side</th>"

        elif scan_name == "opening":
            extra = f"""
              <td>{fmt(r.get('gap_pct'), '+.1f', '%')}</td>
              <td>{fmt(r.get('vs_vwap_pct'), '+.2f', '%')}</td>
              <td>{fmt(r.get('rvol'), '.1f', '×')}</td>
              <td>{fmt(r.get('rsi'), '.0f')}</td>
            """
            cols_extra = "<th>Gap %</th><th>vs VWAP</th><th>RVOL</th><th>RSI</th>"

        elif scan_name == "midday":
            extra = f"""
              <td>{fmt(r.get('morning_move_pct'), '+.1f', '%')}</td>
              <td>{fmt(r.get('consol_range_pct'), '.1f', '%')}</td>
              <td>{fmt(r.get('pct_from_high'), '+.1f', '%')}</td>
              <td>{fmt(r.get('vs_vwap_pct'), '+.2f', '%')}</td>
            """
            cols_extra = "<th>AM Move</th><th>Range</th><th>vs High</th><th>vs VWAP</th>"

        else:  # powerhour
            new_high = "↑ NEW HIGH" if r.get("new_intraday_high") else ""
            extra = f"""
              <td>{fmt(r.get('day_change_pct'), '+.1f', '%')}</td>
              <td>{fmt(r.get('rvol_ph'), '.1f', '×')}</td>
              <td>{fmt(r.get('vs_vwap_pct'), '+.2f', '%')}</td>
              <td><span class='newhigh'>{new_high}</span></td>
            """
            cols_extra = "<th>Day %</th><th>PH RVOL</th><th>vs VWAP</th><th>Signal</th>"

        rows += f"""
        <tr class='{"row-aplus" if grade == "A+" else "row-a" if grade == "A" else ""}'>
          <td><span class='grade-badge {gcss}'>{grade}</span></td>
          <td><a href='{tv_link}' target='_blank' class='ticker-link'>{r['ticker']}</a></td>
          <td>{fmt(r.get('price'), '.2f', '', '$')}</td>
          {extra}
          <td>{render_reasons(r.get('reasons', []))}</td>
        </tr>
        """

    if not results:
        rows = "<tr><td colspan='10' class='empty'>No results yet — scanner hasn't run.</td></tr>"
        cols_extra = ""

    return f"""
    <table>
      <thead>
        <tr>
          <th>Grade</th><th>Ticker</th><th>Price</th>
          {cols_extra}
          <th>Signals</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    <div class='scan-meta'>
      Updated: {ts or 'Never'} &bull; {count} stocks scanned &bull;
      <span class='aplus-count'>{len(aplus)} A+ setup{"s" if len(aplus) != 1 else ""}</span>
    </div>
    """

def build_html() -> str:
    now_local = datetime.now().strftime("%Y-%m-%d %H:%M")
    now_et    = datetime.now(ET_TZ).strftime("%H:%M ET")

    tabs_html = ""
    panels_html = ""
    first = True

    for scan_name, label, icon, time_str in SCANS:
        data      = load_scan(scan_name)
        active    = "active" if first else ""
        has_data  = data is not None
        aplus_cnt = len([r for r in (data or {}).get("results", []) if r.get("grade") == "A+"]) if has_data else 0
        badge     = f" <span class='tab-badge'>{aplus_cnt} A+</span>" if aplus_cnt > 0 else ""

        tabs_html += f"<button class='tab-btn {active}' onclick='showTab(\"{scan_name}\")'>{icon} {label}{badge}<br><small>{time_str}</small></button>"

        content = render_scan_table(scan_name, data) if has_data else "<p class='empty'>Scanner has not run today.</p>"
        panels_html += f"<div id='tab-{scan_name}' class='tab-panel {active}'>{content}</div>"
        first = False

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="120">
<title>DayTrader Scanner — {now_local}</title>
<style>
  :root {{
    --bg: #0d1117; --card: #161b22; --border: #30363d;
    --text: #c9d1d9; --muted: #8b949e; --link: #58a6ff;
    --aplus: #ffd700; --a: #3fb950; --b: #d29922; --c: #8b949e;
    --long: #3fb950; --short: #f85149; --badge-bg: #1f2937;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: "Segoe UI", system-ui, sans-serif; font-size: 14px; }}

  header {{ background: linear-gradient(135deg, #1a1f2e 0%, #0d1117 100%);
    border-bottom: 1px solid var(--border); padding: 16px 24px;
    display: flex; justify-content: space-between; align-items: center; }}
  header h1 {{ font-size: 1.4rem; font-weight: 700; color: #fff; }}
  header h1 span {{ color: var(--aplus); }}
  .time-badge {{ background: var(--badge-bg); border: 1px solid var(--border);
    border-radius: 6px; padding: 4px 12px; font-size: 12px; color: var(--muted); }}

  .legend {{ display: flex; gap: 12px; padding: 10px 24px; background: var(--card);
    border-bottom: 1px solid var(--border); align-items: center; font-size: 12px; }}
  .legend-item {{ display: flex; align-items: center; gap: 5px; }}

  .tabs {{ display: flex; gap: 4px; padding: 12px 24px 0;
    border-bottom: 1px solid var(--border); background: var(--card); overflow-x: auto; }}
  .tab-btn {{ background: transparent; border: none; border-bottom: 3px solid transparent;
    color: var(--muted); cursor: pointer; padding: 8px 16px 10px; font-size: 13px;
    font-weight: 500; text-align: center; white-space: nowrap; transition: all .2s; }}
  .tab-btn:hover {{ color: var(--text); }}
  .tab-btn.active {{ color: var(--aplus); border-bottom-color: var(--aplus); }}
  .tab-btn small {{ font-size: 10px; opacity: .7; }}
  .tab-badge {{ background: var(--aplus); color: #000; border-radius: 10px;
    padding: 1px 7px; font-size: 10px; font-weight: 700; margin-left: 4px; }}

  .tab-panel {{ display: none; padding: 20px 24px; }}
  .tab-panel.active {{ display: block; }}

  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ background: #1c2128; color: var(--muted); text-align: left;
    padding: 8px 10px; font-weight: 600; font-size: 11px; text-transform: uppercase;
    letter-spacing: .5px; border-bottom: 1px solid var(--border); position: sticky; top: 0; }}
  td {{ padding: 7px 10px; border-bottom: 1px solid #21262d; vertical-align: middle; }}
  tr:hover td {{ background: #1c2128; }}
  .row-aplus {{ background: rgba(255,215,0,.04); }}
  .row-a {{ background: rgba(63,185,80,.03); }}

  .grade-badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px;
    font-weight: 700; font-size: 11px; }}
  .grade-aplus {{ background: rgba(255,215,0,.2); color: var(--aplus); border: 1px solid rgba(255,215,0,.4); }}
  .grade-a {{ background: rgba(63,185,80,.2); color: var(--a); border: 1px solid rgba(63,185,80,.4); }}
  .grade-b {{ background: rgba(210,153,34,.2); color: var(--b); border: 1px solid rgba(210,153,34,.4); }}
  .grade-c {{ background: rgba(139,148,158,.1); color: var(--c); border: 1px solid rgba(139,148,158,.3); }}

  .ticker-link {{ color: var(--link); text-decoration: none; font-weight: 600;
    font-family: "Courier New", monospace; }}
  .ticker-link:hover {{ text-decoration: underline; }}

  .badge {{ display: inline-block; padding: 2px 7px; border-radius: 4px; font-size: 10px; font-weight: 700; }}
  .badge-long  {{ background: rgba(63,185,80,.2);  color: var(--long); }}
  .badge-short {{ background: rgba(248,81,73,.2);  color: var(--short); }}

  .tags {{ display: flex; flex-wrap: wrap; gap: 3px; }}
  .tag  {{ background: #1c2128; border: 1px solid var(--border); border-radius: 4px;
    padding: 1px 6px; font-size: 10px; color: var(--muted); white-space: nowrap; }}

  .newhigh {{ color: var(--aplus); font-weight: 700; font-size: 11px; }}
  .na {{ color: var(--muted); }}
  .empty {{ color: var(--muted); padding: 40px; text-align: center; }}
  .scan-meta {{ margin-top: 10px; font-size: 11px; color: var(--muted); }}
  .aplus-count {{ color: var(--aplus); font-weight: 600; }}

  .legend-aplus {{ color: var(--aplus); font-weight: 700; }}
  .legend-a {{ color: var(--a); font-weight: 700; }}
  .legend-b {{ color: var(--b); font-weight: 700; }}
  .legend-c {{ color: var(--c); }}

  @media (max-width: 768px) {{ td, th {{ padding: 5px 6px; font-size: 11px; }} }}
</style>
</head>
<body>

<header>
  <h1>📈 <span>DayTrader</span> Scanner</h1>
  <div class="time-badge">{now_local} local &bull; {now_et}</div>
</header>

<div class="legend">
  <strong>Grade:</strong>
  <div class="legend-item"><span class="legend-aplus">🎯 A+</span> = Prime setup, trade it</div>
  <div class="legend-item"><span class="legend-a">⭐ A</span> = Strong setup</div>
  <div class="legend-item"><span class="legend-b">◆ B</span> = Watch only</div>
  <div class="legend-item"><span class="legend-c">· C</span> = Skip</div>
  <div class="legend-item" style="margin-left:auto; color: var(--muted); font-size:11px;">
    Ticker links open TradingView chart &bull; Auto-refresh 2 min
  </div>
</div>

<div class="tabs">
  {tabs_html}
</div>

{panels_html}

<script>
function showTab(name) {{
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  event.currentTarget.classList.add('active');
}}
</script>
</body>
</html>"""

if __name__ == "__main__":
    html = build_html()
    with open(DASH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Dashboard saved: {DASH}")
    print(f"Open: file:///{DASH.replace(chr(92), '/')}")
