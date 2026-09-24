#!/usr/bin/env python3
"""Render the run-history page (results-history.html).

Reads the append-only ledger (`eval_results/runs.jsonl`) and shows, per system, how
the metrics move across runs, plus a provenance table. Runs are only comparable
when the reference-set fingerprint and the model list agree; the page marks rows
that break comparability.

    python scripts/build_history_dashboard.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.eval import ledger, scoreboard, snapshot  # noqa: E402

SYSTEMS = [
    ("oracle", "Oracle", "grey"),
    ("direct", "Direct", "amber"),
    ("direct+rag", "Direct+RAG", "blue"),
    ("harness", "Harness", "green"),
]
TRENDS = [
    ("execution_match", "Execution accuracy (answerable cases)", lambda v: f"{v:.0%}"),
    ("presumption_rate", "Presumption rate (lower is better)", lambda v: f"{v:.0%}"),
    ("cost_per_case", "Cost per case (CNY)", lambda v: f"¥{v:.5f}"),
]
FLAT = {"execution_match": 0.0, "presumption_rate": 0.0, "cost_per_case": 0.0}


def metric_of(record: dict, key: str) -> float:
    if key == "cost_per_case":
        return float(record.get("cost_cny", {}).get("per_case", 0.0))
    return float(record.get("metrics", {}).get(key, 0.0))


def line_chart(series, *, y_fmt, w=340, h=170, y_max=None):
    """series: [(label, [(run_label, value, comparable)])] drawn as points + line."""
    pad_l, pad_r, pad_t, pad_b = 58, 16, 14, 34
    pw, ph = w - pad_l - pad_r, h - pad_t - pad_b
    values = [v for _, pts, _ in series for _, v, _ in pts]
    top = y_max if y_max is not None else (max(values) * 1.25 if values else 1.0)
    top = top or 1.0
    longest = max((len(pts) for _, pts, _ in series), default=1)

    def sx(i):
        return pad_l + (i / max(longest - 1, 1)) * pw

    def sy(v):
        return pad_t + ph - (v / top) * ph

    parts = [f'<line x1="{pad_l}" y1="{pad_t + ph}" x2="{pad_l + pw}" y2="{pad_t + ph}" class="axis-line"/>']
    for i in range(3):
        gy = top * i / 2
        parts.append(f'<line x1="{pad_l}" y1="{sy(gy):.1f}" x2="{pad_l + pw}" y2="{sy(gy):.1f}" class="grid"/>')
        parts.append(f'<text x="{pad_l - 8}" y="{sy(gy) + 4:.1f}" class="tick" text-anchor="end">{y_fmt(gy)}</text>')
    for name, pts, tone in series:
        if not pts:
            continue
        coords = [(sx(i), sy(v)) for i, (_, v, _) in enumerate(pts)]
        if len(coords) > 1:
            path = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
            parts.append(f'<polyline points="{path}" class="poly {tone}"/>')
        for (x, y), (run_label, value, comparable) in zip(coords, pts):
            cls = "pt " + ("warn" if not comparable else tone)
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" class="{cls}"/>')
    return f'<svg viewBox="0 0 {w} {h}" class="chart">{"".join(parts)}</svg>'


def run_table(runs: list[dict]) -> str:
    latest = ledger.latest_per_system(runs)
    previous: dict[str, dict] = {}
    rows = ""
    for record in reversed(runs):
        system = record["system"]
        label, tone = next(((l, t) for s, l, t in SYSTEMS if s == system), (system, "grey"))
        comparable = "-"
        if system in previous:
            ok = ledger.is_comparable(record, previous[system])
            comparable = (
                '<span class="tag ok">comparable</span>'
                if ok
                else '<span class="tag warn">dataset/model changed</span>'
            )
        previous[system] = record
        m = record["metrics"]
        metrics = record.get("metrics", {})
        is_latest = latest.get(system) is record
        rows += f"""<tr class="{'latest' if is_latest else ''}">
          <td>{record['ts']}</td>
          <td><span class="sys {tone}">{label}</span></td>
          <td>{record['dataset']['label']}<small> · {record['dataset']['n']} cases</small></td>
          <td><code>{record['git']}</code></td>
          <td class="num">{metrics.get('execution_match', 0):.1%}</td>
          <td class="num">{metrics.get('ex_at_answered', 0):.1%}</td>
          <td class="num">{metrics.get('presumption_rate', 0):.1%}</td>
          <td class="num">{metrics.get('over_clarify_rate', 0):.1%}</td>
          <td class="num">{record['cost_cny']['per_case']:.5f}</td>
          <td>{comparable}</td>
          <td><a href="{record['report']}">report</a></td>
        </tr>"""
    return rows


CSS = """
:root{--bg:#fbfbfd;--card:#fff;--text:#1d1d1f;--muted:#6e6e73;--line:#e5e5ea;
  --blue:#0071e3;--green:#1d9a4e;--amber:#e08b00;--red:#e0342a;--grey:#8e8e93;
  --shadow:0 1px 2px rgba(0,0,0,.04),0 12px 34px rgba(0,0,0,.05)}
@media (prefers-color-scheme:dark){:root{--bg:#000;--card:#1c1c1e;--text:#f5f5f7;
  --muted:#98989d;--line:#2c2c2e;--shadow:0 1px 2px rgba(0,0,0,.6),0 12px 34px rgba(0,0,0,.5)}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","Helvetica Neue",Arial,sans-serif;
  -webkit-font-smoothing:antialiased;line-height:1.55;font-variant-numeric:tabular-nums}
.wrap{max-width:1080px;margin:0 auto;padding:88px 24px 120px}
header{margin-bottom:52px}
.kicker{margin:0 0 8px;font-size:11.5px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--blue)}
h1{margin:0 0 12px;font-size:clamp(32px,4.4vw,46px);line-height:1.05;letter-spacing:-.03em;font-weight:700}
h2{margin:0 0 10px;font-size:clamp(20px,2.4vw,26px);letter-spacing:-.02em;font-weight:660}
h3{margin:0 0 4px;font-size:14px;font-weight:620}
.lede{margin:0 0 22px;font-size:15px;color:var(--muted);max-width:80ch}
.panel-note{margin:0 0 6px;font-size:12px;color:var(--muted)}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:22px;box-shadow:var(--shadow)}
.panels{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px;margin-bottom:44px}
.chart{width:100%;height:auto;display:block}
.grid{stroke:var(--line);stroke-width:1}
.axis-line{stroke:var(--muted);stroke-width:1;opacity:.45}
.tick{font-size:10px;fill:var(--muted)}
.poly{fill:none;stroke-width:2.2}
.poly.blue{stroke:var(--blue)}.poly.green{stroke:var(--green)}
.poly.amber{stroke:var(--amber)}.poly.grey{stroke:var(--grey)}
.pt{stroke:var(--card);stroke-width:1.5}
.pt.blue{fill:var(--blue)}.pt.green{fill:var(--green)}
.pt.amber{fill:var(--amber)}.pt.grey{fill:var(--grey)}
.pt.warn{fill:var(--red)}
table{width:100%;border-collapse:collapse}
th,td{padding:11px 9px;text-align:left;border-bottom:1px solid var(--line);font-size:13px}
thead th{font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
td.num{text-align:right;font-variant-numeric:tabular-nums}
tr.latest{background:color-mix(in srgb,var(--blue) 6%,transparent)}
.sys{font-weight:620}
.sys.blue{color:var(--blue)}.sys.green{color:var(--green)}
.sys.amber{color:var(--amber)}.sys.grey{color:var(--grey)}
.tag{font-size:10.5px;padding:2px 7px;border-radius:999px}
.tag.ok{background:color-mix(in srgb,var(--green) 14%,transparent);color:var(--green)}
.tag.warn{background:color-mix(in srgb,var(--red) 14%,transparent);color:var(--red)}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11.5px;
  background:color-mix(in srgb,var(--muted) 12%,transparent);padding:1px 5px;border-radius:5px}
small{color:var(--muted)}
footer{margin-top:44px;color:var(--muted);font-size:12.5px;border-top:1px solid var(--line);padding-top:18px}
.empty{color:var(--muted);font-size:14px}
"""


def render(runs: list[dict]) -> str:
    if not runs:
        return "<!doctype html><html><body><p class='empty'>No runs recorded yet.</p></body></html>"

    panels = ""
    for system, label, tone in SYSTEMS:
        history = ledger.history_for(runs, system)
        if not history:
            continue
        for key, title, fmt in TRENDS:
            compare = []
            for i, r in enumerate(history):
                comparable = i == 0 or ledger.is_comparable(history[i - 1], r)
                compare.append((r["ts"][5:16], metric_of(r, key), comparable))
            panels += f"""
        <div class="card">
          <h3>{label} — {title}</h3>
          <p class="panel-note">{len(history)} run(s)</p>
          {line_chart([(label, compare, tone)], y_fmt=fmt)}
        </div>"""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NL2SQL · Run history</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <header>
    <p class="kicker">NL2SQL · Evaluation</p>
    <h1>Run history</h1>
    <p class="lede">Append-only record of every evaluation run. A run is only comparable
    with the previous run of the same system when the reference-set fingerprint and the model
    list agree; breaking rows are marked. Red markers denote a non-comparable step.</p>
  </header>

  <h2>Trends</h2>
  <div class="panels">{panels}</div>

  <h2>Runs</h2>
  <table>
    <thead><tr><th>time (UTC)</th><th>system</th><th>dataset</th><th>git</th>
      <th>EX</th><th>EX@ans</th><th>presumption</th><th>over-clarify</th><th>cost/case</th>
      <th>comparability</th><th>report</th></tr></thead>
    <tbody>{run_table(runs)}</tbody>
  </table>

  <footer>Generated from <code>eval_results/runs.jsonl</code> by
  <code>python scripts/build_history_dashboard.py</code>. The ledger contains aggregates and
  provenance only; per-case detail stays in the private raw dumps.</footer>
</div>
</body>
</html>
"""


RESULTS_MD = ledger.LEDGER_PATH.parent / "RESULTS.md"
RUNS_BEGIN = "<!-- RUNS:BEGIN -->"
RUNS_END = "<!-- RUNS:END -->"


def scoreboard_block(runs: list[dict]) -> str:
    """Dataset badge + run table, injected into RESULTS.md between markers."""
    identity = ledger.dataset_identity()
    lines = [
        f"Reference set: **{identity.label}** (fingerprint `{identity.hash}`, {identity.n} cases)"
        f" · {len(runs)} recorded run(s)",
        "",
        "| time (UTC) | system | dataset | git | EX | EX@answered | presumption ↓ | "
        "over-clarify ↓ | cost / case | report |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for record in reversed(runs):
        metrics = record.get("metrics", {})
        flag = "" if record["dataset"]["hash"] == identity.hash else " ⚠︎"
        lines.append(
            f"| {record['ts']} | `{record['system']}` | {record['dataset']['label']}{flag} | "
            f"`{record['git']}` | {metrics.get('execution_match', 0):.1%} | "
            f"{metrics.get('ex_at_answered', 0):.1%} | {metrics.get('presumption_rate', 0):.1%} | "
            f"{metrics.get('over_clarify_rate', 0):.1%} | ¥{record['cost_cny']['per_case']:.5f} | "
            f"[{record['report']}]({record['report']}) |"
        )
    lines += [
        "",
        "⚠︎ = scored against a different reference set; not comparable with the current one.",
        "Older reports are pruned; the ledger is the durable record. The numeric blocks in §2–§4",
        "are generated from the ledger and the latest raw dumps by",
        "`python scripts/build_history_dashboard.py`, so they cannot drift.",
    ]
    return "\n".join(lines)


def inject_scoreboard(runs: list[dict]) -> bool:
    if not RESULTS_MD.exists():
        return False
    text = RESULTS_MD.read_text(encoding="utf-8")
    if RUNS_BEGIN not in text or RUNS_END not in text:
        return False
    head, _, rest = text.partition(RUNS_BEGIN)
    _, _, tail = rest.partition(RUNS_END)
    RESULTS_MD.write_text(
        f"{head}{RUNS_BEGIN}\n{scoreboard_block(runs)}\n{RUNS_END}{tail}", encoding="utf-8"
    )
    return True


def main() -> int:
    runs = ledger.load_runs()
    out = ledger.LEDGER_PATH.parent / "results-history.html"
    out.write_text(render(runs), encoding="utf-8")
    print(f"wrote {out} ({len(runs)} runs)")
    print(f"updated {RESULTS_MD.name}" if inject_scoreboard(runs) else "RESULTS.md: no RUNS markers")

    data = snapshot.load_all()
    updated = scoreboard.update(RESULTS_MD, data)
    print(f"synchronised RESULTS.md: {', '.join(updated) if updated else 'no marked blocks'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
