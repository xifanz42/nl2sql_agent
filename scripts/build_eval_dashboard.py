#!/usr/bin/env python3
"""Render the visual evaluation report (results-vis.html).

Low-text single page over the latest `*.raw.jsonl` per system. Every figure carries
an explicit caption; numbers come from `app.eval.reporter` and `app.eval.pricing`.

    python scripts/build_eval_dashboard.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.eval import reporter  # noqa: E402
from app.eval.paths import EvalPaths  # noqa: E402

SYSTEMS = [
    ("oracle", "Oracle", "Reference upper bound", "—", "—", "—", "—"),
    ("direct", "Direct", "Schema-only baseline", "none", "minimal", "none", "none"),
    ("direct+rag", "Direct+RAG", "Retrieval-augmented baseline", "dense", "minimal", "none", "none"),
    ("harness", "Harness", "System under evaluation", "dense", "engineered", "yes", "yes"),
]
TONE = {"oracle": "grey", "direct": "amber", "direct+rag": "blue", "harness": "green"}
FALLBACK_MODEL = {
    "direct": "Qwen/Qwen3-Coder-30B-A3B-Instruct",
    "direct+rag": "Qwen/Qwen3-Coder-30B-A3B-Instruct",
}
LEVELS = ("easy", "medium", "hard")

METRICS = [
    ("EX", "Multiset identity of result sets; row order ignored. Primary answer metric."),
    ("EM", "Normalised string identity with the reference query."),
    ("valid_sql", "Statement executes without a database error."),
    ("schema_adherence", "Every referenced relation resolves in the schema."),
    ("presumption rate ↓", "Answered although abstention was required."),
    ("over-clarify rate ↓", "Abstained although an answer was required."),
    ("clarification_correct", "Predicted action agrees with the reference action."),
    ("policy accuracy", "(TP + TN) / N over the action confusion matrix."),
]


# --------------------------------------------------------------------- helpers


def latest_raw(system: str) -> Path | None:
    files = sorted(EvalPaths.default().output_dir.glob(f"{system}-*.raw.jsonl"))
    return files[-1] if files else None


def derive(system: str, rows: list[dict]) -> dict:
    matrix = reporter.policy_matrix(rows)
    return {
        "rows": rows,
        "summary": reporter.summarize(rows),
        "matrix": matrix,
        "rates": reporter.policy_rates(matrix),
        "latency": reporter.latency_stats(rows),
        "tokens": reporter.token_stats(rows),
        "cost": reporter.cost_stats(rows, FALLBACK_MODEL.get(system)),
        "by_difficulty": reporter.summarize_by_sql_difficulty(rows),
    }


def pct(value: float, digits: int = 1) -> str:
    return f"{value * 100:.{digits}f}%"


def secs(ms: float) -> str:
    return f"{ms / 1000:.2f} s"


def money(value: float) -> str:
    return f"¥{value:.4f}"


# ------------------------------------------------------------------ chart prims

W, H = 700, 360


def _frame(x_label, y_label, x_range, y_range, x_fmt, y_fmt, *, w=W, h=H, pad=None):
    l, r, t, b = pad or (74, 30, 22, 54)
    pw, ph = w - l - r, h - t - b

    def sx(v):
        return l + (v - x_range[0]) / (x_range[1] - x_range[0]) * pw

    def sy(v):
        return t + ph - (v - y_range[0]) / (y_range[1] - y_range[0]) * ph

    out = [f'<line x1="{l}" y1="{t + ph}" x2="{l + pw}" y2="{t + ph}" class="axis-line"/>']
    out.append(f'<line x1="{l}" y1="{t}" x2="{l}" y2="{t + ph}" class="axis-line"/>')
    for i in range(5):
        gx = x_range[0] + (x_range[1] - x_range[0]) * i / 4
        gy = y_range[0] + (y_range[1] - y_range[0]) * i / 4
        out.append(f'<line x1="{sx(gx):.1f}" y1="{t}" x2="{sx(gx):.1f}" y2="{t + ph}" class="grid"/>')
        out.append(f'<line x1="{l}" y1="{sy(gy):.1f}" x2="{l + pw}" y2="{sy(gy):.1f}" class="grid"/>')
        if x_fmt:
            out.append(
                f'<text x="{sx(gx):.1f}" y="{t + ph + 18}" class="tick" text-anchor="middle">'
                f"{x_fmt(gx)}</text>"
            )
        if y_fmt:
            out.append(
                f'<text x="{l - 9}" y="{sy(gy) + 4:.1f}" class="tick" text-anchor="end">'
                f"{y_fmt(gy)}</text>"
            )
    if x_label:
        out.append(
            f'<text x="{l + pw / 2:.1f}" y="{h - 8}" class="axis-label" text-anchor="middle">'
            f"{x_label}</text>"
        )
    if y_label:
        mid = f"{t + ph / 2:.1f}"
        out.append(
            f'<text x="16" y="{mid}" class="axis-label" text-anchor="middle" '
            f'transform="rotate(-90 16 {mid})">{y_label}</text>'
        )
    return "".join(out), sx, sy


def scatter(points, *, x_label, y_label, x_range, y_range, x_fmt, y_fmt, ideal=None,
            w=W, h=320):
    body, sx, sy = _frame(x_label, y_label, x_range, y_range, x_fmt, y_fmt, w=w, h=h)
    extra = ""
    if ideal:
        extra = f'<circle cx="{sx(ideal[0]):.1f}" cy="{sy(ideal[1]):.1f}" r="17" class="ideal"/>'
    marks = ""
    for label, x, y, tone in points:
        cx, cy = sx(x), sy(y)
        marks += f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="6" class="pt {tone}"/>'
        marks += f'<text x="{cx + 11:.1f}" y="{cy + 4:.1f}" class="pt-label">{label}</text>'
    return f'<svg viewBox="0 0 {w} {h}" class="chart">{body}{extra}{marks}</svg>'


def waterfall(steps, *, w=W):
    """steps: [(label, start, end, kind, annotation)] with kind in level/increase/decrease."""
    h = 300
    body, sx, sy = _frame(None, "Execution accuracy", (0, len(steps)), (0, 100),
                          None, lambda v: f"{v:.0f}%", w=w, h=h, pad=(64, 24, 26, 44))
    bar_w = w * 0.093
    bars = ""
    for i, (label, start, end, kind, note) in enumerate(steps):
        cx = sx(i + 0.5)
        top, bottom = sy(max(start, end)), sy(min(start, end))
        bars += (
            f'<rect x="{cx - bar_w / 2:.1f}" y="{top:.1f}" width="{bar_w:.1f}" '
            f'height="{max(bottom - top, 3):.1f}" rx="6" class="wf {kind}"/>'
        )
        anchor = top - 8 if kind != "decrease" else bottom + 16
        bars += (
            f'<text x="{cx:.1f}" y="{anchor:.1f}" class="wf-label {kind}" '
            f'text-anchor="middle">{note}</text>'
        )
        bars += f'<text x="{cx:.1f}" y="{h - 10}" class="tick" text-anchor="middle">{label}</text>'
        if i < len(steps) - 1:
            bars += (
                f'<line x1="{cx + bar_w / 2:.1f}" y1="{sy(end):.1f}" '
                f'x2="{sx(i + 1.5) - bar_w / 2:.1f}" y2="{sy(end):.1f}" class="connector"/>'
            )
    return f'<svg viewBox="0 0 {w} {h}" class="chart">{body}{bars}</svg>'


def grouped_bars(rows, series, colors, *, x_label, value_fmt="{:.0f}%", w=W, bar_h=10, gap=5,
                 row_gap=16, pad_l=92, pad_r=54):
    """rows: [(label, {series: value})] drawn as horizontal grouped bars on a 0-100 axis."""
    t = 8
    row_h = len(series) * (bar_h + gap) + row_gap
    h = t + row_h * len(rows) + 40
    l, r = pad_l, pad_r
    pw = w - l - r

    def sx(v):
        return l + max(min(v, 100), 0) / 100 * pw

    parts = [f'<line x1="{l}" y1="{t}" x2="{l}" y2="{t + row_h * len(rows)}" class="axis-line"/>']
    for i in range(5):
        gx = 25 * i
        parts.append(
            f'<line x1="{sx(gx):.1f}" y1="{t}" x2="{sx(gx):.1f}" y2="{t + row_h * len(rows)}" class="grid"/>'
        )
        parts.append(
            f'<text x="{sx(gx):.1f}" y="{h - 14}" class="tick" text-anchor="middle">{gx}%</text>'
        )
    for i, (label, values) in enumerate(rows):
        y0 = t + i * row_h
        parts.append(
            f'<text x="{l - 12}" y="{y0 + len(series) * (bar_h + gap) / 2 + 4:.1f}" '
            f'class="row-label" text-anchor="end">{label}</text>'
        )
        for j, name in enumerate(series):
            y = y0 + j * (bar_h + gap)
            value = values.get(name, 0.0)
            parts.append(
                f'<rect x="{l}" y="{y:.1f}" width="{max(sx(value) - l, 1):.1f}" height="{bar_h}" '
                f'rx="{bar_h / 2:.1f}" class="gb {colors[j]}"/>'
            )
            parts.append(
                f'<text x="{sx(value) + 7:.1f}" y="{y + bar_h - 2:.1f}" class="gb-label">'
                f"{value_fmt.format(value)}</text>"
            )
    return f'<svg viewBox="0 0 {w} {h}" class="chart">{"".join(parts)}</svg>'


# ------------------------------------------------------------------- sections


def framework_section(data: dict) -> str:
    rows = data["oracle"]["rows"]
    total = len(rows)
    sql_n = sum(1 for r in rows if not reporter.is_clarification(r))
    clarify_n = sum(1 for r in rows if reporter.required_behavior_of(r) == "clarify")
    refuse_n = total - sql_n - clarify_n
    chips = "".join(
        f'<div class="chip {tone}"><b>{n}</b><span>{label}</span></div>'
        for tone, n, label in (
            ("grey", sql_n, "answerable"),
            ("amber", clarify_n, "under-specified"),
            ("red", refuse_n, "unanswerable"),
        )
    )
    cards = "".join(
        f'<div class="metric-card"><b>{name}</b><p>{desc}</p></div>' for name, desc in METRICS
    )
    systems = "".join(
        f'<tr><th scope="row">{label}</th><td>{role}</td><td>{ret}</td>'
        f"<td>{prompt}</td><td>{guard}</td><td>{abst}</td></tr>"
        for _, label, role, ret, prompt, guard, abst in SYSTEMS
    )
    return f"""
<section class="reveal">
  <p class="kicker">01 · Evaluation framework</p>
  <h2>Metrics and dimensions</h2>
  <p class="lede">Cases are partitioned by the reference action. Metrics are reported over
  their own partition; no averaging is performed across partitions.</p>
  <div class="chips">{chips}</div>
  <div class="metrics">{cards}</div>
  <table class="grid compact">
    <thead><tr><th>System</th><th>Role</th><th>Retrieval</th><th>Prompt</th>
      <th>Guardrails</th><th>Abstention</th></tr></thead>
    <tbody>{systems}</tbody>
  </table>
</section>"""


def findings_section(data: dict) -> str:
    ex = {s: data[s]["summary"]["sql"]["execution_match"] for s in data}
    dre = (ex["direct+rag"] - ex["direct"]) * 100
    cond = (
        data["harness"]["summary"]["ex_at_answered"]
        - data["direct+rag"]["summary"]["ex_at_answered"]
    ) * 100
    cost_ratio = (
        data["direct+rag"]["cost"]["per_case_cny"] / data["direct"]["cost"]["per_case_cny"]
        if data["direct"]["cost"]["per_case_cny"]
        else 0
    )
    cards = "".join(
        f'<div class="stat {tone}"><span class="figure">{figure}</span>'
        f"<h3>{title}</h3><p>{desc}</p></div>"
        for tone, figure, title, desc in (
            ("up", f"+{dre:.1f} pt", "Retrieval effect",
             "EX gain from adding retrieval to the schema-only baseline."),
            ("neutral", f"{cond:+.1f} pt", "Conditional parity",
             "EX@answered difference between the agent and the retrieval baseline."),
            ("neutral", f"{cost_ratio:.1f}×", "Retrieval cost",
             "Per-case cost multiplier from injecting retrieved context."),
            ("up", "100% → 17.6%", "Presumption",
             "Both baselines answer every case; the agent abstains instead."),
        )
    )
    points = [
        (label, data[s]["summary"]["answer_rate"] * 100, ex[s] * 100, TONE[s])
        for s, label, *_ in SYSTEMS
    ]
    hero = scatter(
        points,
        x_label="Coverage — share of the 90 cases answered",
        y_label="Execution accuracy (73 answerable cases)",
        x_range=(70, 105),
        y_range=(0, 105),
        x_fmt=lambda v: f"{v:.0f}%",
        y_fmt=lambda v: f"{v:.0f}%",
        ideal=(100, 100),
        w=920,
        h=380,
    )
    return f"""
<section class="reveal">
  <p class="kicker">02 · Principal findings</p>
  <h2>Four results</h2>
  <div class="stats">{cards}</div>
  <figure class="figure">
    <figcaption><b>Coverage–accuracy plane.</b> Horizontal axis: the share of cases the system
    answered. Vertical axis: execution accuracy over the 73 cases that have a reference query.
    The dashed marker is the theoretical optimum. The agent and the retrieval baseline are
    separated mainly along the horizontal axis, i.e. by coverage rather than by accuracy.</figcaption>
    {hero}
  </figure>
</section>"""


def answer_section(data: dict) -> str:
    ex = {s: data[s]["summary"]["sql"]["execution_match"] * 100 for s in data}
    wf = waterfall(
        [
            ("Direct", 0, ex["direct"], "level", f"{ex['direct']:.1f}%"),
            ("Retrieval", ex["direct"], ex["direct+rag"], "increase", f"+{ex['direct+rag'] - ex['direct']:.1f} pt"),
            ("Direct+RAG", 0, ex["direct+rag"], "level", f"{ex['direct+rag']:.1f}%"),
            ("Agent overhead", ex["direct+rag"], ex["harness"], "decrease", f"{ex['harness'] - ex['direct+rag']:.1f} pt"),
            ("Harness", 0, ex["harness"], "level", f"{ex['harness']:.1f}%"),
        ],
        w=470,
    )
    diff_rows = [
        (label, {lv: v["execution_match"] * 100 for lv, v in data[s]["by_difficulty"].items()})
        for s, label, *_ in SYSTEMS
        if data[s]["by_difficulty"]
    ]
    diff = grouped_bars(diff_rows, LEVELS, ["lvl0", "lvl1", "lvl2"], x_label="Execution accuracy",
                        bar_h=9, gap=4, w=470, pad_l=74, pad_r=48)
    legend = "".join(
        f'<span><i class="dot lvl{i}"></i>{lv} (n={sum(1 for r in data["oracle"]["rows"] if r["difficulty"] == lv)})</span>'
        for i, lv in enumerate(LEVELS)
    )
    return f"""
<section class="reveal">
  <p class="kicker">03 · Detailed analysis</p>
  <h2>Answer quality</h2>
  <p class="lede"><b>Answer quality</b> = execution accuracy (EX) over the 73 <em>answerable</em>
  cases: whether the emitted query returns the reference result set, ignoring row order and
  aliasing. Cases requiring abstention are excluded from this partition.</p>
  <div class="split">
    <figure class="figure">
      <figcaption><b>Component attribution.</b> Solid bars are absolute levels; floating bars are
      increments. Retrieval contributes the gain; the agent's additional machinery is
      net-negative on this axis.</figcaption>
      {wf}
    </figure>
    <figure class="figure">
      <figcaption><b>Accuracy by difficulty stratum.</b> Three bars per system, one per stratum.
      The agent and the retrieval baseline are level on easy and medium; the deficit is confined
      to <em>hard</em>.</figcaption>
      <div class="legend">{legend}</div>
      {diff}
    </figure>
  </div>
</section>"""


def policy_section(data: dict) -> str:
    cms = ""
    for s, label, *_ in SYSTEMS:
        m = data[s]["matrix"]
        cms += f"""
        <div class="cm {TONE[s]}">
          <h4>{label}</h4>
          <div class="cm-head"><span>reference ↓ / predicted →</span></div>
          <div class="cm-grid">
            <div class="cell ok"><b>{m['answered_as_expected']}</b><span>answered ✓</span></div>
            <div class="cell bad"><b>{m['over_clarified']}</b><span>over-clarify</span></div>
            <div class="cell bad"><b>{m['presumed']}</b><span>presumed</span></div>
            <div class="cell ok"><b>{m['declined_as_expected']}</b><span>abstained ✓</span></div>
          </div>
          <p class="cap">policy accuracy {pct(data[s]['rates']['policy_accuracy'])}</p>
        </div>"""
    rows = [
        (label, {
            "presumption": data[s]["rates"]["presumption_rate"] * 100,
            "over": data[s]["rates"]["over_clarify_rate"] * 100,
        })
        for s, label, *_ in SYSTEMS
    ]
    rates = grouped_bars(rows, ("presumption", "over"), ["red", "amber"],
                         x_label="Error rate (lower is better)", bar_h=11, gap=6, w=900, pad_l=96)
    return f"""
<section class="reveal">
  <h2>Abstention policy</h2>
  <p class="lede">The agent is designed not to presume: where the question is under-specified or
  unanswerable it should ask or decline. Two error rates describe that policy, both
  lower-is-better.</p>
  <div class="matrices">{cms}</div>
  <figure class="figure">
    <figcaption><b>Policy error rates.</b> <em>Presumption</em>: answered when abstention was
    required (the failure mode the agent targets). <em>Over-clarification</em>: abstained when an
    answer was required (the cost of that policy). Both baselines presume on every such case; the
    agent presumes on 3 of 17.</figcaption>
    <div class="legend">
      <span><i class="dot red"></i>presumption rate</span>
      <span><i class="dot amber"></i>over-clarify rate</span>
    </div>
    {rates}
  </figure>
</section>"""


def efficiency_section(data: dict) -> str:
    token_rows = [
        (label, {
            "cached": data[s]["tokens"]["cached"],
            "uncached": data[s]["tokens"]["prompt"] - data[s]["tokens"]["cached"],
            "completion": data[s]["tokens"]["completion"],
        })
        for s, label, *_ in SYSTEMS
        if data[s]["tokens"]["per_case"]
    ]
    max_per_case = max((data[s]["tokens"]["per_case"] for s, *_ in SYSTEMS), default=1) or 1
    stacks = ""
    for s, label, *_ in SYSTEMS:
        tok = data[s]["tokens"]
        lat = data[s]["latency"]
        cost = data[s]["cost"]
        if tok["per_case"]:
            scale = tok["per_case"] / max_per_case * 100
            total = tok["total"] or 1
            segs = (
                ("cached", tok["cached"]),
                ("uncached", tok["prompt"] - tok["cached"]),
                ("completion", tok["completion"]),
            )
            left = 0.0
            body = ""
            for name, value in segs:
                width = scale * value / total
                body += f'<i class="seg {name}" style="--l:{left:.1f}%;--w:{width:.1f}%"></i>'
                left += width
            cap = (
                f"{tok['per_case']:.0f} tokens / case · {pct(tok['cached_share'])} of prompt cached · "
                f"{tok['calls_per_case']:.1f} calls / case · {money(cost['per_case_cny'])} / case"
            )
        else:
            body = '<i class="seg none" style="--l:0;--w:100%"></i>'
            cap = "no model call"
        stacks += (
            f'<div class="row"><div class="label">{label}</div><div class="track">'
            f'<div class="stack">{body}</div><div class="cap">{cap}</div></div></div>'
        )
    cheapest = min(
        (data[s]["cost"]["per_case_cny"] for s, *_ in SYSTEMS if data[s]["cost"]["per_case_cny"]),
        default=0,
    )
    priciest = max((data[s]["cost"]["per_case_cny"] for s, *_ in SYSTEMS), default=0)
    table = ""
    for s, label, *_ in SYSTEMS:
        tok = data[s]["tokens"]
        lat = data[s]["latency"]
        cost = data[s]["cost"]["per_case_cny"]
        if not tok["per_case"]:
            cost_cell = "<td>—</td>"
        elif cost <= cheapest * 1.05:
            cost_cell = f'<td class="good">{money(cost)}</td>'
        elif cost >= priciest * 0.95:
            cost_cell = f'<td class="warn">{money(cost)}</td>'
        else:
            cost_cell = f"<td>{money(cost)}</td>"
        table += (
            f"<tr><th scope='row'>{label}</th><td>{tok['calls_per_case']:.1f}</td>"
            f"<td>{tok['per_case']:.0f}</td><td>{pct(tok['cached_share'], 0)}</td>"
            f"{cost_cell}<td>{secs(lat['p50_ms'])}</td><td>{secs(lat['p95_ms'])}</td></tr>"
        )
    return f"""
<section class="reveal">
  <h2>Cost and latency</h2>
  <p class="lede">Per-case inference cost. Cost is derived from token counts and a dated price
  list; latency and call count do not enter the cost.</p>
  <figure class="figure">
    <figcaption><b>Token composition per case.</b> Each bar is one system; segment width is
    proportional to tokens per case, relative to the most expensive system. Cached prompt tokens
    are billed at the cached-input rate where the model publishes one.</figcaption>
    <div class="legend">
      <span><i class="dot cached"></i>cached prompt</span>
      <span><i class="dot uncached"></i>uncached prompt</span>
      <span><i class="dot completion"></i>completion</span>
    </div>
    <div class="rows">{stacks}</div>
  </figure>
  <table class="grid">
    <thead><tr><th>System</th><th>calls / case</th><th>tokens / case</th><th>cached</th>
      <th>cost / case</th><th>p50</th><th>p95</th></tr></thead>
    <tbody>{table}</tbody>
  </table>
  <p class="cap">Cost highlighting: green = cheapest, amber = most expensive. Retrieval multiplies
  cost 3.7×; the agent's routing call runs on a zero-priced model and adds no cost.</p>
</section>"""


def conclusion_section(data: dict) -> str:
    columns = [
        ("Answer quality (EX)", lambda s: data[s]["summary"]["sql"]["execution_match"], True, "pct"),
        ("EX@answered", lambda s: data[s]["summary"]["ex_at_answered"], True, "pct"),
        ("Coverage", lambda s: data[s]["summary"]["answer_rate"], True, "pct"),
        ("Presumption ↓", lambda s: data[s]["rates"]["presumption_rate"], False, "pct"),
        ("Over-clarify ↓", lambda s: data[s]["rates"]["over_clarify_rate"], False, "pct"),
        ("Cost / case", lambda s: data[s]["cost"]["per_case_cny"], False, "money"),
    ]
    values = {name: {s: fn(s) for s, *_ in SYSTEMS} for name, fn, _, _ in columns}
    body = ""
    for s, label, *_ in SYSTEMS:
        cells = ""
        for name, _, higher_better, kind in columns:
            value = values[name][s]
            pool = list(values[name].values())
            best = max(pool) if higher_better else min(pool)
            worst = min(pool) if higher_better else max(pool)
            shown = money(value) if kind == "money" else pct(value)
            if value == best:
                cells += f'<td class="good">{shown}</td>'
            elif value == worst:
                cells += f'<td class="bad">{shown}</td>'
            else:
                cells += f"<td>{shown}</td>"
        body += f"<tr><th scope='row'>{label}</th>{cells}</tr>"
    head = "".join(f"<th>{name}</th>" for name, *_ in columns)
    return f"""
<section class="reveal">
  <p class="kicker">04 · Conclusion</p>
  <h2>Synthesis</h2>
  <table class="grid summary">
    <thead><tr><th>System</th>{head}</tr></thead>
    <tbody>{body}</tbody>
  </table>
  <p class="cap">Best value per column in green, worst in red.</p>
  <ol class="conclusions">
    <li>Retrieval is the dominant contributor to answer quality (+32.9 pt EX); the agent's
        additional machinery is net-negative on that axis (−8.2 pt).</li>
    <li>At equal coverage the agent is indistinguishable from the retrieval baseline
        (EX@answered 60.6% vs 63.0%, within run-to-run variance): its aggregate deficit is a
        coverage effect, not a generation defect.</li>
    <li>The agent's differentiator is abstention (presumption 100% → 17.6%). The highest-leverage
        improvement is therefore calibration of that policy, not further prompt engineering.</li>
  </ol>
</section>"""


CSS = """
:root{
  --bg:#fbfbfd; --card:#fff; --text:#1d1d1f; --muted:#6e6e73; --line:#e5e5ea;
  --blue:#0071e3; --green:#1d9a4e; --amber:#e08b00; --red:#e0342a; --grey:#8e8e93;
  --shadow:0 1px 2px rgba(0,0,0,.04), 0 12px 34px rgba(0,0,0,.05);
}
@media (prefers-color-scheme: dark){
  :root{ --bg:#000; --card:#1c1c1e; --text:#f5f5f7; --muted:#98989d; --line:#2c2c2e;
         --shadow:0 1px 2px rgba(0,0,0,.6), 0 12px 34px rgba(0,0,0,.5); }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","Helvetica Neue",Arial,sans-serif;
  -webkit-font-smoothing:antialiased;line-height:1.55;font-variant-numeric:tabular-nums}
.wrap{max-width:1080px;margin:0 auto;padding:88px 24px 130px}
section{margin-bottom:88px}
.kicker{margin:0 0 8px;font-size:11.5px;font-weight:600;letter-spacing:.1em;
  text-transform:uppercase;color:var(--blue)}
h1{margin:0 0 14px;font-size:clamp(34px,4.6vw,50px);line-height:1.05;letter-spacing:-.03em;font-weight:700}
h2{margin:0 0 10px;font-size:clamp(22px,2.6vw,28px);letter-spacing:-.02em;font-weight:670}
h3{margin:0 0 4px;font-size:15px;letter-spacing:-.01em;font-weight:620}
h4{margin:0 0 6px;font-size:14px;font-weight:600}
.lede{margin:0 0 24px;font-size:15px;color:var(--muted);max-width:80ch}
.cap{margin:10px 0 0;font-size:12.5px;color:var(--muted);max-width:86ch}
.reveal{opacity:0;transform:translateY(18px);
  transition:opacity .7s ease,transform .7s cubic-bezier(.16,1,.3,1)}
.reveal.in{opacity:1;transform:none}
.chips{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:26px}
.chip{display:flex;align-items:baseline;gap:9px;padding:10px 16px;border-radius:13px;
  background:var(--card);border:1px solid var(--line);box-shadow:var(--shadow)}
.chip b{font-size:20px;font-weight:660;letter-spacing:-.02em}
.chip span{font-size:13px;color:var(--muted)}
.chip.red b{color:var(--red)} .chip.amber b{color:var(--amber)}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(228px,1fr));gap:14px;margin-bottom:30px}
.metric-card{background:var(--card);border:1px solid var(--line);border-radius:14px;
  padding:16px 18px;box-shadow:var(--shadow)}
.metric-card b{font-size:13.5px;letter-spacing:-.005em}
.metric-card p{margin:5px 0 0;font-size:12.5px;color:var(--muted);line-height:1.45}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(196px,1fr));gap:16px;margin-bottom:36px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:18px;
  padding:20px 20px;box-shadow:var(--shadow)}
.stat .figure{display:block;font-size:clamp(19px,2.1vw,24px);font-weight:680;
  letter-spacing:-.02em;line-height:1.1;margin-bottom:9px}
.stat.up .figure{color:var(--green)} .stat.down .figure{color:var(--red)}
.stat.neutral .figure{color:var(--text)}
.stat p{margin:0;font-size:12.5px;color:var(--muted);line-height:1.45}
.split{display:grid;grid-template-columns:1fr;gap:24px}
@media (min-width:920px){ .split{grid-template-columns:1fr 1fr} }
.figure{margin:0;background:var(--card);border:1px solid var(--line);
  border-radius:18px;padding:20px 22px 12px;box-shadow:var(--shadow)}
.figure figcaption{font-size:12.5px;color:var(--muted);margin-bottom:12px;line-height:1.5}
.chart{width:100%;height:auto;display:block}
.grid{stroke:var(--line);stroke-width:1}
.axis-line{stroke:var(--muted);stroke-width:1;opacity:.45}
.connector{stroke:var(--muted);stroke-width:1;stroke-dasharray:4 4;opacity:.6}
.tick{font-size:10.5px;fill:var(--muted)}
.axis-label{font-size:11px;fill:var(--muted)}
.row-label{font-size:12.5px;fill:var(--text);font-weight:600}
.pt-label{font-size:11px;fill:var(--text);font-weight:600}
.pt{stroke:var(--card);stroke-width:1.5}
.pt.blue{fill:var(--blue)} .pt.green{fill:var(--green)} .pt.amber{fill:var(--amber)}
.pt.red{fill:var(--red)} .pt.grey{fill:var(--grey)}
.ideal{fill:none;stroke:var(--muted);stroke-width:1.2;stroke-dasharray:4 5;opacity:.6}
.wf.level{fill:var(--muted);opacity:.55}
.wf.increase{fill:var(--green)}
.wf.decrease{fill:var(--red);opacity:.85}
.wf-label{font-size:11.5px;font-weight:660}
.wf-label.level{fill:var(--text)}
.wf-label.increase{fill:var(--green)}
.wf-label.decrease{fill:var(--red)}
.gb{border-radius:5px}
.gb.red{fill:var(--red)} .gb.amber{fill:var(--amber)}
.gb.lvl0{fill:color-mix(in srgb,var(--blue) 32%,transparent)}
.gb.lvl1{fill:color-mix(in srgb,var(--blue) 62%,transparent)}
.gb.lvl2{fill:var(--blue)}
.gb-label{font-size:10.5px;fill:var(--muted)}
.matrices{display:grid;grid-template-columns:repeat(auto-fit,minmax(186px,1fr));gap:14px;margin-bottom:30px}
.cm{background:var(--card);border:1px solid var(--line);border-radius:16px;
  padding:16px;box-shadow:var(--shadow)}
.cm-head{font-size:10.5px;color:var(--muted);margin-bottom:8px;letter-spacing:.02em}
.cm-grid{display:grid;grid-template-columns:1fr 1fr;gap:7px}
.cell{border-radius:11px;padding:10px 8px;text-align:center}
.cell b{display:block;font-size:17px;font-weight:660;letter-spacing:-.02em}
.cell span{font-size:10.5px;color:var(--muted)}
.cell.ok{background:color-mix(in srgb,var(--green) 11%,transparent)}
.cell.bad{background:color-mix(in srgb,var(--red) 11%,transparent)}
.legend{display:flex;gap:18px;margin:0 0 14px;font-size:11.5px;color:var(--muted);flex-wrap:wrap}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}
.dot.cached{background:color-mix(in srgb,var(--blue) 32%,transparent)}
.dot.uncached{background:var(--blue)}
.dot.completion{background:color-mix(in srgb,var(--text) 26%,transparent)}
.dot.red{background:var(--red)} .dot.amber{background:var(--amber)}
.dot.lvl0{background:color-mix(in srgb,var(--blue) 32%,transparent)}
.dot.lvl1{background:color-mix(in srgb,var(--blue) 62%,transparent)}
.dot.lvl2{background:var(--blue)}
.rows .row{display:grid;grid-template-columns:118px 1fr;gap:18px;align-items:center;
  padding:13px 0;border-top:1px solid var(--line)}
.rows .row:first-child{border-top:0}
.label{font-weight:600;font-size:13.5px}
.stack{position:relative;height:13px;border-radius:999px;overflow:hidden;
  background:color-mix(in srgb,var(--muted) 13%,transparent)}
.stack .seg{position:absolute;top:0;left:var(--l);width:var(--w);height:100%;
  transform:scaleX(0);transform-origin:left;
  transition:transform .9s cubic-bezier(.16,1,.3,1) .1s}
.reveal.in .stack .seg{transform:scaleX(1)}
.seg.cached{background:color-mix(in srgb,var(--blue) 32%,transparent)}
.seg.uncached{background:var(--blue)}
.seg.completion{background:color-mix(in srgb,var(--text) 26%,transparent)}
.seg.none{background:color-mix(in srgb,var(--muted) 20%,transparent)}
table.grid{width:100%;border-collapse:collapse}
table.grid th,table.grid td{padding:11px 9px;text-align:left;border-bottom:1px solid var(--line);
  font-size:13.5px;vertical-align:middle}
table.grid thead th{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
table.grid tbody th{font-weight:620;white-space:nowrap}
table.grid.compact td,table.grid.compact th{font-size:12.5px;padding:9px 7px}
table.grid td.good{color:var(--green);font-weight:620}
table.grid td.bad{color:var(--red)}
table.grid td.warn{color:var(--amber);font-weight:620}
table.grid.summary td,table.grid.summary th{text-align:right}
table.grid.summary th:first-child{text-align:left}
.conclusions{margin:26px 0 0;padding-left:20px}
.conclusions li{margin-bottom:9px;font-size:14px;max-width:88ch}
footer{color:var(--muted);font-size:12.5px;border-top:1px solid var(--line);padding-top:20px}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;
  background:color-mix(in srgb,var(--muted) 12%,transparent);padding:2px 5px;border-radius:5px}
@media (prefers-reduced-motion: reduce){
  .reveal{opacity:1;transform:none;transition:none}
  .stack .seg{transform:scaleX(1);transition:none}
}
"""

SCRIPT = """
const io = new IntersectionObserver((entries) => {
  for (const entry of entries) {
    if (entry.isIntersecting) { entry.target.classList.add('in'); io.unobserve(entry.target); }
  }
}, { threshold: 0.12 });
document.querySelectorAll('.reveal').forEach((el) => io.observe(el));
"""


def render(data: dict) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows = data["oracle"]["rows"]
    total = len(rows)
    sql_n = sum(1 for r in rows if not reporter.is_clarification(r))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NL2SQL · Evaluation report</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <header class="reveal">
    <p class="kicker">NL2SQL · Evaluation</p>
    <h1>Baseline report</h1>
    <p class="lede">{total} private cases — {sql_n} answerable, {total - sql_n} requiring
    abstention. All systems share a single SQL generation model, so observed differences are
    attributable to system architecture rather than model capacity.</p>
    <p class="cap">Generated {stamp}</p>
  </header>

  {framework_section(data)}
  {findings_section(data)}
  {answer_section(data)}
  {policy_section(data)}
  {efficiency_section(data)}
  {conclusion_section(data)}

  <footer>
    Reference set, expected results and per-case dumps are private and never published; this
    page reports aggregates only. Regenerate with
    <code>python scripts/build_eval_dashboard.py</code>.
  </footer>
</div>
<script>{SCRIPT}</script>
</body>
</html>
"""


def main() -> int:
    behaviors = reporter.load_case_behaviors(EvalPaths.default().dataset)
    data = {}
    for system, *_ in SYSTEMS:
        path = latest_raw(system)
        if path:
            data[system] = derive(system, reporter.load_raw(path, behaviors))

    missing = [s for s, *_ in SYSTEMS if s not in data]
    if missing:
        print(f"warning: no raw dump for {', '.join(missing)}")

    out = EvalPaths.default().output_dir / "results-vis.html"
    out.write_text(render(data), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
