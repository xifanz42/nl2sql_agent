"""Render the article's figures from the ledger + raw dumps (matplotlib -> PNG).

PNG rather than SVG: the labels are Chinese, and a rasterised image carries the
font with it instead of depending on the reader's installed fonts. 2x DPI so the
numbers stay legible.

    python scripts/build_article_figures.py [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

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

LANG = "zh"


def T(zh: str, en: str) -> str:
    """Label for the active language (`--lang`)."""
    return en if LANG == "en" else zh


def build_models():
    return [
        (T("Qwen3-Coder\n(30B/3B 激活)", "Qwen3-Coder\n(30B/3B active)"), "Qwen/Qwen3-Coder-30B-A3B-Instruct", None),
        ("DeepSeek-V3", "deepseek-ai/DeepSeek-V3", None),
        (T("DS-Flash\n(轻量通用档)", "DS-Flash\n(lightweight general tier)"), "deepseek-flash", False),
    ]


MODELS = build_models()


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
    ap.add_argument("--lang", choices=("zh", "en"), default="zh")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    global LANG, MODELS
    LANG = args.lang
    MODELS = build_models()
    if args.out is None:
        base = Path("/Users/x.zou/Documents/github/xifanz42.github.io/static/reports/nl2sql-eval")
        args.out = base / "en" if LANG == "en" else base
    args.out.mkdir(parents=True, exist_ok=True)

    ledger, cases = load()
    answer_ids = [i for i, c in cases.items() if c["required_behavior"] == "answer"]
    m = {name: {s: pick(ledger, mid, s, th) for s in SYSTEMS} for name, mid, th in MODELS}

    w, xs = 0.26, range(len(MODELS))

    # ---------------------------------------------------------------- fig 1: EX
    fig, ax = plt.subplots(figsize=(7.4, 3.6))
    w, xs = 0.26, range(len(MODELS))
    for k, s in enumerate(SYSTEMS):
        vals = [m[n][s]["metrics"]["execution_match"] * 100 for n, _, _ in MODELS]
        bars = ax.bar([x + (k - 1) * w for x in xs], vals, w, label=s, color=C[s])
        label_bars(ax, bars)
    ax.set_xticks(list(xs))
    ax.set_xticklabels([n for n, _, _ in MODELS], fontsize=9)
    ax.set_ylabel(T("EX（%）", "EX (%)"))
    ax.set_ylim(0, 80)
    ax.set_title(T("执行一致率 EX（可答题 n=73）", "Execution match EX (answerable n=73)"), fontsize=11)
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
    ax.annotate(T("零能力基线 50%", "Zero-skill = 50%"), (len(MODELS) - 0.52, 51.5), color="#6B7280", fontsize=8.5)
    ax.set_xticks(list(xs))
    ax.set_xticklabels([n for n, _, _ in MODELS], fontsize=9)
    ax.set_ylabel(T("平衡准确率（%）", "Balanced accuracy (%)"))
    ax.set_ylim(0, 108)
    ax.set_title(T("行为轴：平衡准确率（两类等权）", "Behavior axis: balanced accuracy (two classes, equal weight)"), fontsize=11)
    ax.legend(frameon=False, ncol=3, loc="upper left", fontsize=9)
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(args.out / "fig2-balanced-accuracy.png", dpi=200)
    plt.close(fig)

    # --------------- fig 3: abstention correctness, two panels like fig 4a -------------
    # Same layout as fig 4a: left / right panel = the two abstention types, x = model,
    # three system-coloured bars per group, one legend. Counts are raw case counts (out of
    # 14 `refuse` / 3 `clarify`), with a dotted full-marks line in each panel.
    ABSTAIN = {}
    for n, _m, _t in MODELS:
        for sname in SYSTEMS:
            rows_ = raw_of(m[n][sname])
            rf = [x for x in rows_.values() if x["required_behavior"] == "refuse"]
            cl = [x for x in rows_.values() if x["required_behavior"] == "clarify"]
            ABSTAIN[(n, sname)] = (
                sum(1 for x in rf if x["predicted_kind"] != "sql"),
                sum(1 for x in cl if x["predicted_kind"] != "sql"),
            )

    fig, panels = plt.subplots(1, 2, figsize=(7.8, 3.5), sharey=True)
    for ax, (idx, title, full) in zip(
        panels,
        ((0, T("`refuse`：该拒绝却作答了吗（满分 14 条）", "`refuse`: answered when it\nshould have refused? (of 14)"), 14),
         (1, T("`clarify`：该追问却作答了吗（满分 3 条）", "`clarify`: answered when it\nshould have asked? (of 3)"), 3)),
    ):
        for k, sname in enumerate(SYSTEMS):
            vals = [ABSTAIN[(n, sname)][idx] for n, _, _ in MODELS]
            bars = ax.bar([x + (k - 1) * w for x in xs], vals, w, color=C[sname],
                          label=sname)
            label_bars(ax, bars, fmt="{:.0f}", dy=0.35, size=9)
        ax.axhline(full, color=C["zero"], lw=1.4, ls=":")
        ax.annotate(T(f"满分 {full}", f"out of {full}"), (len(MODELS) - 0.5, full + 0.5), ha="right",
                    fontsize=8.5, color="#6B7280")
        ax.set_xticks(list(xs))
        ax.set_xticklabels([n.split("\n")[0] for n, _, _ in MODELS], fontsize=9)
        ax.set_title(title, fontsize=9.5)
        ax.set_ylim(0, 17.5)
        ax.grid(axis="y", alpha=0.25)
        ax.set_axisbelow(True)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    panels[0].set_ylabel(T("答对的条数", "correct count"), fontsize=9)
    panels[1].legend(frameon=False, loc="upper right", fontsize=8.5)
    fig.tight_layout()
    fig.savefig(args.out / "fig3-abstention.png", dpi=200)
    plt.close(fig)

    # --------------- fig 4: the two behavior error rates, side by side ---------------
    # A scatter with two legends + arrows was tried first and was unreadable: with
    # only 9 cells the reader had to decode colour AND marker AND trajectory to find
    # a single point. Two grouped-bar panels reuse the fig 1/2/5 layout, so the
    # trade-off between the two rates is read straight across two identical panels.
    fig, panels = plt.subplots(1, 2, figsize=(7.8, 3.5), sharey=True)
    PANEL = (
        ("presumption_rate", T("臆测率（该弃答却作答）", "presumption rate\n(answered when it should abstain)"), T("恒作答（零能力）= 100", "always answer (zero skill) = 100")),
        ("over_clarify_rate", T("过度澄清率（该作答却追问）", "over-clarify rate\n(asked when it should answer)"), T("恒弃答（零能力）= 100", "always abstain (zero skill) = 100")),
    )
    for ax, (key, title, worst) in zip(panels, PANEL):
        for k, s in enumerate(SYSTEMS):
            vals = [m[n][s]["metrics"][key] * 100 for n, _, _ in MODELS]
            bars = ax.bar([x + (k - 1) * w for x in xs], vals, w, label=s, color=C[s])
            label_bars(ax, bars, dy=1.8, size=7.5)
        ax.axhline(100, color=C["zero"], lw=1.3, ls="--")
        ax.annotate(worst, (-0.45, 92), ha="left", fontsize=8, color="#6B7280")
        ax.set_xticks(list(xs))
        ax.set_xticklabels([n for n, _, _ in MODELS], fontsize=9)
        ax.set_title(title, fontsize=10)
        ax.set_ylim(0, 112)
        ax.grid(axis="y", alpha=0.25)
        ax.set_axisbelow(True)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    panels[0].set_ylabel(T("占 17 条不可答题的比例（%）", "share of the 17 unanswerable cases (%)"))
    panels[1].set_ylabel(T("占 73 条可答题的比例（%）", "share of the 73 answerable cases (%)"))
    panels[1].legend(frameon=False, loc="upper right", fontsize=8.5)
    fig.tight_layout()
    fig.savefig(args.out / "fig4-behavior-bars.png", dpi=200)
    plt.close(fig)

    # --------- fig 4b: the same nine cells as a plane (companion to the bars) ---------
    # Why a second view at all: "the two rates trade off, so nearer the origin is better"
    # is a 2-D statement, which two separate bar panels cannot express.
    # Colour is RESERVED for the system across the whole article (fig 1/2/5 and here +
    # below): an earlier version coloured this plane by *model*, so the same three hues
    # meant two different things in two figures. Models therefore become panels, which
    # also removes the need for a second legend or marker-shape coding.
    # `harness` is drawn as a ring: its point sits almost exactly on top of `direct+rag`
    # for Qwen (11.8, 9.6) vs (11.8, 8.2), and a filled dot would simply hide it.
    SHORT = {name: short for (name, _m, _t), short in
             zip(MODELS, ["Qwen3-Coder", "DeepSeek-V3", "DS-Flash"])}
    fig, panels = plt.subplots(1, 3, figsize=(7.6, 3.35), sharex=True, sharey=True)
    for ax, (name, mid, th) in zip(panels, MODELS):
        ax.plot([0, 100], [100, 0], ls="--", lw=1.4, color=C["zero"], zorder=1)
        px = [m[name][s]["metrics"]["presumption_rate"] * 100 for s in SYSTEMS]
        py = [m[name][s]["metrics"]["over_clarify_rate"] * 100 for s in SYSTEMS]
        ax.plot(px, py, ls="-", lw=1.1, color="#9CA3AF", alpha=0.85, zorder=2)
        for k, sysname in enumerate(SYSTEMS):
            ring = sysname == "harness"
            ax.scatter(px[k], py[k], s=132 if ring else 92, color=C[sysname],
                       edgecolor=C[sysname], lw=1.9 if ring else 1.1,
                       facecolor="none" if ring else C[sysname],
                       label=sysname if ax is panels[0] else None, zorder=3 + k)
        ax.set_title(SHORT[name], fontsize=9.5)
        ax.set_xlim(-5, 108)
        ax.set_ylim(-5, 108)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel(T("臆测率（%）", "presumption rate (%)"), fontsize=8.5)
        ax.grid(alpha=0.22)
        ax.set_axisbelow(True)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    panels[0].set_ylabel(T("过度澄清率（%）", "over-clarify rate (%)"), fontsize=8.5)
    panels[0].annotate(T("零能力线", "zero-skill line"), (30, 74), fontsize=7.5, color="#6B7280", ha="left")
    handles, labels = panels[0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=9, loc="center right",
               title=T("系统", "System"), title_fontsize=8.5, handletextpad=0.5)
    fig.suptitle(T("行为轴：臆测率 × 过度澄清率", "Behavior axis: presumption rate × over-clarify rate"), fontsize=11, y=0.98)
    # rect keeps room for the right-hand legend and stops tight_layout from pushing the
    # suptitle off the canvas (suptitle must stay below y = 1.0 or its top half is cut).
    fig.tight_layout(rect=[0, 0, 0.84, 0.93])
    fig.savefig(args.out / "fig4-behavior-plane.png", dpi=200)
    plt.close(fig)

    # -------------- fig 5: money and tokens side by side -----------------------------
    # Same x layout in both panels, so "does money simply track token volume?" is read
    # straight across -- and it does NOT: Qwen and V3 carry ~1,400 tokens for 1.19 vs
    # 3.33, and flash carries the same 1,406 for 1.02. Hue stays reserved for the system
    # (article-wide convention); the cached / uncached / output split of the money is
    # spelled out in §3.4.1 rather than encoded here.
    fig, p5 = plt.subplots(1, 2, figsize=(7.8, 3.5))
    for ax, key, ylab, title, fmt, dy in (
        (p5[0], "tok", T("token / 例（输入 + 输出）", "tokens / case (input + output)"), T("token 量", "token volume"), "{:,.0f}", 45),
        (p5[1], "cny", T("¥ / 千例", "CNY / 1k cases"), T("经济成本", "economic cost"), "{:.2f}", 0.08),
    ):
        for k, sname in enumerate(SYSTEMS):
            if key == "tok":
                vals = [m[n][sname]["tokens"]["per_case"] for n, _, _ in MODELS]
            else:
                vals = [m[n][sname]["cost_cny"]["per_case"] * 1000 for n, _, _ in MODELS]
            bars = ax.bar([x + (k - 1) * w for x in xs], vals, w, color=C[sname],
                          label=sname if ax is p5[0] else None)
            label_bars(ax, bars, fmt=fmt, dy=dy, size=8)
        ax.set_xticks(list(xs))
        ax.set_xticklabels([n.split("\n")[0] for n, _, _ in MODELS], fontsize=9)
        ax.set_ylabel(ylab, fontsize=9)
        ax.set_title(title, fontsize=10.5)
        ax.set_ylim(0, max(vals) * 1.24)
        ax.grid(axis="y", alpha=0.25)
        ax.set_axisbelow(True)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    p5[0].legend(frameon=False, ncol=3, loc="upper left", fontsize=8.5)
    fig.tight_layout()
    fig.savefig(args.out / "fig5-cost.png", dpi=200)
    plt.close(fig)

    # ----------------------- fig 6: latency as p50-p95 segments ----------------------
    # No bars: the bar height only repeated p50, and it pushed the p50 label under the
    # whisker line. A plain segment from the median (filled dot) to the tail (hollow dot)
    # frees both ends, so each number sits next to its own end and can be set larger.
    # Colour stays reserved for the system (article-wide convention).
    fig, ax = plt.subplots(figsize=(7.4, 3.6))
    for k, sname in enumerate(SYSTEMS):
        for xp, (n, _m, _t) in zip([x + (k - 1) * w for x in xs], MODELS):
            lo = m[n][sname]["latency_ms"]["p50_ms"] / 1000
            hi = m[n][sname]["latency_ms"]["p95_ms"] / 1000
            col = C[sname]
            ax.plot([xp, xp], [lo, hi], color=col, lw=2.8, solid_capstyle="round", zorder=2)
            ax.plot([xp], [hi], marker="o", ms=7.5, mfc="white", mec=col, mew=1.7, zorder=3)
            ax.plot([xp], [lo], marker="o", ms=7.5, color=col, zorder=3)
            ax.annotate(f"{lo:.2f}", (xp, lo - 0.14), ha="center", va="top",
                        fontsize=9, color=col)
            ax.annotate(f"{hi:.2f}", (xp, hi + 0.14), ha="center", va="bottom",
                        fontsize=9, color=col)
    ax.set_xticks(list(xs))
    ax.set_xticklabels([n.split("\n")[0] for n, _, _ in MODELS], fontsize=9.5)
    ax.set_ylabel(T("延迟（秒）", "latency (s)"), fontsize=9.5)
    ax.set_xlim(-0.55, len(MODELS) - 0.45)
    ax.set_ylim(0, 8.3)
    ax.set_title(T("体验成本：延迟 p50（实心）– p95（空心）", "Experience cost: latency p50 (solid) – p95 (hollow)"), fontsize=11)
    ax.legend(handles=[plt.Line2D([], [], color=C[sname], lw=2.8, marker="o", ms=6.5,
                                  label=sname) for sname in SYSTEMS],
              frameon=False, ncol=3, loc="upper left", fontsize=9)
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(args.out / "fig6-latency.png", dpi=200)
    plt.close(fig)

    for p in sorted(args.out.glob("fig*.png")):
        print(T(f"  现有 {p.name}  ({p.stat().st_size // 1024} KB)", f"  wrote {p.name}  ({p.stat().st_size // 1024} KB)"))
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
