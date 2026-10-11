"""Render the article's figures from the ledger + raw dumps (matplotlib -> PNG).

PNG rather than SVG: the labels are Chinese, and a rasterised image carries the
font with it instead of depending on the reader's installed fonts. 2x DPI so the
numbers stay legible.

    python scripts/build_article_figures.py [--out DIR]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from app import PROJECT_ROOT  # noqa: E402
from app.eval.paths import EvalPaths  # noqa: E402
from app.eval.systems import extract_sql  # noqa: E402

plt.rcParams["font.sans-serif"] = ["Hiragino Sans GB", "Arial Unicode MS", "Heiti TC", "Songti SC"]
plt.rcParams["axes.unicode_minus"] = False

# Blowfish palette: neutral-600 / primary-500 / secondary-500 / neutral-400 (+ a lighter blue)
C = {
    "direct": "#464E7A",
    "direct+rag": "#4A9EF0",
    "harness": "#F0705A",
    "zero": "#8D94BD",
    "alt": "#9AA6D9",
}
SYSTEMS = ["direct", "direct+rag", "harness"]
MODELS = [
    ("Qwen3-Coder\n(30B/3B 激活)", "Qwen/Qwen3-Coder-30B-A3B-Instruct", None),
    ("DeepSeek-V3", "deepseek-ai/DeepSeek-V3", None),
    ("DS-Flash\n(思考模式关闭)", "deepseek-flash", False),
]


def load():
    ledger = [
        json.loads(line)
        for line in (PROJECT_ROOT / "eval_results/runs.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    cases = {
        c["id"]: c
        for c in (
            json.loads(line)
            for line in (PROJECT_ROOT / "tests/eval/golden_dataset.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    return ledger, cases


def pick(ledger, model: str, system: str, thinking=None):
    """The FIRST run of the *current* configuration (the one carrying ``decoding``).

    Two traps, both of which silently produced wrong figures before:
    * the ledger still holds earlier runs whose prompt was not aligned, so
      "any run for this model+system" is not the same as "this experiment";
    * repeats of the same cell are the §3.2.4 evidence, not the headline column.
    Requiring a ``decoding`` key selects the current config only, and taking the
    first of those matches the pass the tables report.
    """
    hits = [
        r
        for r in ledger
        if r["models"] == [model]
        and r["system"] == system
        and "decoding" in r
        and r["decoding"].get("thinking") is thinking
    ]
    return hits[0] if hits else None


def raw_of(record) -> dict:
    path = EvalPaths.default().raw_for(record["report"])
    return {x["id"]: x for x in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())}


def label_bars(ax, bars, fmt="{:.1f}", dy=1.6, color="black", size=8.5):
    for b in bars:
        ax.annotate(
            fmt.format(b.get_height()),
            (b.get_x() + b.get_width() / 2, b.get_height() + dy),
            ha="center", va="bottom", fontsize=size, color=color,
        )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("/Users/x.zou/Documents/github/xifanz42.github.io/static/reports/nl2sql-eval"),
    )
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    ledger, cases = load()
    answer_ids = [i for i, c in cases.items() if c["required_behavior"] == "answer"]
    m = {name: {s: pick(ledger, mid, s, th) for s in SYSTEMS} for name, mid, th in MODELS}

    # ---------------------------------------------------------------- fig 1: EX
    fig, ax = plt.subplots(figsize=(7.4, 3.6))
    w, xs = 0.26, range(len(MODELS))
    for k, s in enumerate(SYSTEMS):
        vals = [m[n][s]["metrics"]["execution_match"] * 100 for n, _, _ in MODELS]
        bars = ax.bar([x + (k - 1) * w for x in xs], vals, w, label=s, color=C[s])
        label_bars(ax, bars)
    ax.set_xticks(list(xs))
    ax.set_xticklabels([n for n, _, _ in MODELS], fontsize=9)
    ax.set_ylabel("EX（%）")
    ax.set_ylim(0, 80)
    ax.set_title("执行一致率 EX（可答题 n=73）", fontsize=11)
    ax.legend(frameon=False, ncol=3, loc="upper right", fontsize=9)
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(args.out / "fig1-ex.png", dpi=200)
    plt.close(fig)

    # ------------------------------------------- fig 2: balanced accuracy + zero skill
    fig, ax = plt.subplots(figsize=(7.4, 3.6))
    for k, s in enumerate(SYSTEMS):
        vals = [_balanced_accuracy(m[n][s], cases) for n, _, _ in MODELS]
        bars = ax.bar([x + (k - 1) * w for x in xs], vals, w, label=s, color=C[s])
        label_bars(ax, bars)
    ax.axhline(50.0, color=C["zero"], lw=1.6, ls="--")
    ax.annotate("零能力基线 50%", (len(MODELS) - 0.52, 51.5), color="#6B7280", fontsize=8.5)
    ax.set_xticks(list(xs))
    ax.set_xticklabels([n for n, _, _ in MODELS], fontsize=9)
    ax.set_ylabel("平衡准确率（%）")
    ax.set_ylim(0, 108)
    ax.set_title("行为轴：平衡准确率（两类等权）", fontsize=11)
    ax.legend(frameon=False, ncol=3, loc="upper left", fontsize=9)
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(args.out / "fig2-balanced-accuracy.png", dpi=200)
    plt.close(fig)

    # ------------------------------- fig 3: what the contract layer can actually fix
    rows = []
    for n, mid, th in MODELS:
        a = raw_of(m[n]["direct+rag"])
        b = raw_of(m[n]["harness"])
        junk = 0
        for i in answer_ids:
            cand = extract_sql(a[i].get("raw_output") or "")
            if cand and ";" in cand and cand.split(";", 1)[1].strip():
                junk += 1
        fixed = sum(1 for i in answer_ids if not a[i]["metrics"]["valid_sql"] and b[i]["metrics"]["valid_sql"])
        d_ex = (m[n]["harness"]["metrics"]["execution_match"] - m[n]["direct+rag"]["metrics"]["execution_match"]) * 100
        rows.append((n, junk, fixed, d_ex))

    fig, ax = plt.subplots(figsize=(7.4, 3.6))
    w = 0.34
    b1 = ax.bar([x - w / 2 for x in xs], [r[1] for r in rows], w,
                label="基线回复的「尾部杂质」条数", color=C["direct"])
    b2 = ax.bar([x + w / 2 for x in xs], [r[2] for r in rows], w,
                label="输出契约层实际修回条数", color=C["harness"])
    label_bars(ax, b1)
    label_bars(ax, b2)
    for x, r in zip(xs, rows):
        ax.annotate(f"ΔEX {r[3]:+.1f} pt", (x, -3.4), ha="center", fontsize=9, color="#374151")
    ax.set_xticks(list(xs))
    ax.set_xticklabels([r[0] for r in rows], fontsize=9)
    ax.set_ylabel("条数（可答题 73 条中）")
    ax.set_ylim(-6, 16)
    ax.set_title("这层只能修「SQL 正确但尾部带杂质」——没有杂质可修，ΔEX 就是 0", fontsize=10.5)
    ax.legend(frameon=False, fontsize=9, loc="upper right")
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(args.out / "fig3-mechanism.png", dpi=200)
    plt.close(fig)

    # ------------- fig 4: the behavior plane (presumption x over-clarification)
    # Every constant classifier sits on x + y = 100, so the dashed "zero-skill" line
    # is also the BA = 50 contour: distance from it is twice the behavioral skill.
    MODEL_COLOR = {name: col for (name, _mid, _th), col in
                   zip(MODELS, ["#464E7A", "#4A9EF0", "#F0705A"])}
    MARKER = {"direct": "o", "direct+rag": "s", "harness": "^"}

    fig, ax = plt.subplots(figsize=(6.4, 5.4))
    ax.plot([0, 100], [100, 0], ls="--", lw=1.5, color=C["zero"], zorder=1)
    ax.annotate("零能力线（两端：恒弃答 / 恒作答）：BA = 50", (30, 62), rotation=-45,
                fontsize=8.5, color="#6B7280", ha="center", va="center")
    for name, mid, th in MODELS:
        col = MODEL_COLOR[name]
        px = [m[name][s]["metrics"]["presumption_rate"] * 100 for s in SYSTEMS]
        py = [m[name][s]["metrics"]["over_clarify_rate"] * 100 for s in SYSTEMS]
        for k in range(len(SYSTEMS) - 1):
            ax.annotate("", (px[k + 1], py[k + 1]), (px[k], py[k]),
                        arrowprops=dict(arrowstyle="-|>", color=col, lw=1.5, alpha=0.7))
        for k, s in enumerate(SYSTEMS):
            ax.scatter(px[k], py[k], s=140, marker=MARKER[s], color=col,
                       edgecolor="white", lw=1.3, zorder=3)
        ax.scatter([], [], color=col, s=70, label=name.split("\n")[0])
    sys_handles = [
        plt.Line2D([], [], color="#9CA3AF", marker=MARKER[s], ls="", ms=9, label=s) for s in SYSTEMS
    ]
    leg_sys = ax.legend(handles=sys_handles, frameon=False, fontsize=9, loc="upper right",
                        title="系统（箭头：direct → +rag → harness）", title_fontsize=8.5)
    ax.add_artist(leg_sys)
    ax.legend(frameon=False, fontsize=9, loc="lower right", title="模型", title_fontsize=8.5)
    ax.set_xlabel("臆测率（%）：该弃答却作答")
    ax.set_ylabel("过度澄清率（%）：该作答却追问")
    ax.set_xlim(-3, 107)
    ax.set_ylim(-4, 107)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title("行为平面：两轴越低越好，原点最理想", fontsize=11)
    ax.grid(alpha=0.25)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(args.out / "fig4-scatter.png", dpi=200)
    plt.close(fig)

    # ------------------------------------------------------------------ fig 5: cost
    fig, ax = plt.subplots(figsize=(7.4, 3.6))
    for k, s in enumerate(SYSTEMS):
        vals = [m[n][s]["cost_cny"]["per_case"] * 1000 for n, _, _ in MODELS]
        bars = ax.bar([x + (k - 1) * w for x in xs], vals, w, label=s, color=C[s])
        label_bars(ax, bars, fmt="{:.2f}")
    ax.set_xticks(list(xs))
    ax.set_xticklabels([n for n, _, _ in MODELS], fontsize=9)
    ax.set_ylabel("每例成本（×0.001 CNY）")
    ax.set_ylim(0, 4.6)
    ax.set_title("成本（价目表见 §2.4.3；DeepSeek 取高峰价）", fontsize=11)
    ax.legend(frameon=False, ncol=3, loc="upper left", fontsize=9)
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(args.out / "fig5-cost.png", dpi=200)
    plt.close(fig)

    for p in sorted(args.out.glob("fig*.png")):
        print(f"  wrote {p}  ({p.stat().st_size // 1024} KB)")
    return 0


def _balanced_accuracy(record, cases) -> float:
    """BA recomputed from the raw dump so it is exact, not a rounded ledger field."""
    rows = raw_of(record)
    abstain = [i for i, c in cases.items() if c["required_behavior"] != "answer"]
    tp = sum(1 for i in cases if i not in abstain and rows[i]["predicted_kind"] == "sql")
    fp = sum(1 for i in abstain if rows[i]["predicted_kind"] == "sql")
    return (tp / (len(cases) - len(abstain)) + (len(abstain) - fp) / len(abstain)) / 2 * 100


if __name__ == "__main__":
    raise SystemExit(main())
