#!/usr/bin/env python3
"""
make_diagrams.py — Generate all anatomy-alive visual artifacts:
  1. sequence_with_timing.png     — matplotlib Gantt-style sequence timeline
  2. receipt_dag.png              — NetworkX receipt dependency DAG
  3. receipt_dag.html             — Plotly interactive DAG
  4. formula_witness_flow.png     — 5 formulas × 7 layers heatmap + Lean refs

SPDX-License-Identifier: Apache-2.0
SZL Holdings — 2026-05-30
"""

from __future__ import annotations
import json, math, hashlib, base64, hmac, os
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.patheffects as pe
import numpy as np

OUT = Path(__file__).parent

# ── Colour palette (publication-grade) ───────────────────────────────────────
C = {
    "PASS":           "#1a7f37",   # forest green
    "STAGED":         "#9a6700",   # amber
    "NOT-YET-WIRED":  "#636e7b",   # slate
    "FAIL":           "#cf222e",   # red
    "bg":             "#0d1117",   # GitHub dark bg
    "card":           "#161b22",
    "border":         "#30363d",
    "text":           "#e6edf3",
    "muted":          "#8b949e",
    "formula": {
        "adversarial_robustness": "#388bfd",
        "liu_hui_pi":             "#da3633",
        "madhava_bound":          "#a371f7",
        "false_position":         "#3fb950",
        "summation_invariant":    "#e3b341",
    },
}

LAYER_DATA = [
    {"layer": 1, "organ": "lutar-lean",  "status": "PASS",          "t_start": 0,     "t_end": 1018,  "action": "gh API blob check + sorry grep"},
    {"layer": 2, "organ": "ouroboros",   "status": "PASS",          "t_start": 1018,  "t_end": 2118,  "action": "TS source confirm + Python parity"},
    {"layer": 3, "organ": "ouroboros",   "status": "STAGED",        "t_start": 2118,  "t_end": 5730,  "action": "6 test file blobs confirmed"},
    {"layer": 4, "organ": "vsp-otel",    "status": "STAGED",        "t_start": 5730,  "t_end": 6890,  "action": "signSpan() simulated λ=0.9208"},
    {"layer": 5, "organ": "uds-mesh",    "status": "PASS",          "t_start": 6890,  "t_end": 7960,  "action": "DSSE receipt emitted + HMAC verified"},
    {"layer": 6, "organ": "a11oy",       "status": "PASS",          "t_start": 7960,  "t_end": 10580, "action": "adversarialRobustnessGate allow=true"},
    {"layer": 7, "organ": "sentra",      "status": "NOT-YET-WIRED", "t_start": 10580, "t_end": 14338, "action": "witnessed.py absent; no receipt input"},
]

FORMULAS = [
    {"id": "adversarial_robustness", "label": "Adversarial\nRobustness",
     "lean_theorem": "robustness_preserved_by_composition",
     "lean_file": "Lutar/Composition/AdversarialRobustness.lean"},
    {"id": "liu_hui_pi", "label": "Liu Hui Pi",
     "lean_theorem": "sideSquared_bounds",
     "lean_file": "Lutar/Banach/LiuHuiPi.lean"},
    {"id": "madhava_bound", "label": "Madhava\nBound",
     "lean_theorem": "madhavaRemainderBound_nonneg",
     "lean_file": "Lutar/PACBayes/MadhavaBound.lean"},
    {"id": "false_position", "label": "False\nPosition",
     "lean_theorem": "false_position_correct",
     "lean_file": "Lutar/Calibration/FalsePosition.lean"},
    {"id": "summation_invariant", "label": "Summation\nInvariant",
     "lean_theorem": "khipuReceipt_checksum_invariant",
     "lean_file": "Lutar/Khipu/SummationInvariant.lean"},
]

# Formula × Layer firing matrix (based on what's wired on main + what harness exercises)
# 1=fired_pass, 0.5=staged, 0=not_yet, -1=N/A
FORMULA_LAYER_MATRIX = {
    "adversarial_robustness": [1, 1, 0.5, 0.5, 1, 1, 0],
    "liu_hui_pi":             [1, 1, 0.5, 0,   0, 1, 0],
    "madhava_bound":          [1, 1, 0.5, 0,   1, 1, 0],
    "false_position":         [1, 1, 0.5, 0,   1, 1, 0],
    "summation_invariant":    [1, 1, 0.5, 0,   1, 1, 0],
}


# =============================================================================
# 1. Sequence / timeline diagram
# =============================================================================

def make_sequence_png():
    fig, ax = plt.subplots(figsize=(16, 7))
    fig.patch.set_facecolor(C["bg"])
    ax.set_facecolor(C["card"])

    total_t = 14338
    n = len(LAYER_DATA)
    y_positions = list(range(n))
    bar_height = 0.55

    for i, ld in enumerate(LAYER_DATA):
        color = C[ld["status"]]
        y = n - 1 - i
        dur = ld["t_end"] - ld["t_start"]

        # Bar
        ax.barh(y, dur, left=ld["t_start"], height=bar_height,
                color=color, alpha=0.88, linewidth=0,
                zorder=3)
        # Bar border
        ax.barh(y, dur, left=ld["t_start"], height=bar_height,
                color="white", alpha=0.12, linewidth=1.2,
                fill=False, zorder=4)

        # Status label inside bar
        mid = ld["t_start"] + dur / 2
        ax.text(mid, y, ld["status"], ha="center", va="center",
                fontsize=8.5, fontweight="bold", color="white",
                zorder=5)

        # Action text to right
        ax.text(ld["t_end"] + 120, y, ld["action"],
                ha="left", va="center", fontsize=8, color=C["muted"],
                zorder=5)

        # trace_id propagation dots at layer boundaries
        ax.scatter([ld["t_end"]], [y], s=60, color="white", zorder=6, alpha=0.9)
        ax.text(ld["t_end"] + 20, y + 0.32, f"{ld['t_end']}ms",
                fontsize=6.5, color=C["muted"], va="bottom")

    # Vertical "trace_id flow" line
    ax.axvline(x=0, color="#58a6ff", alpha=0.4, linewidth=1.5, linestyle="--", zorder=2)

    # Y-axis labels
    ylabels = [f"L{ld['layer']}  {ld['organ']}" for ld in reversed(LAYER_DATA)]
    ax.set_yticks(y_positions)
    ax.set_yticklabels(ylabels, fontsize=10, color=C["text"])
    ax.tick_params(axis="y", length=0)
    ax.tick_params(axis="x", colors=C["muted"], labelsize=9)

    ax.set_xlabel("Elapsed time (ms)", color=C["muted"], fontsize=10)
    ax.set_xlim(-300, total_t + 3200)
    ax.set_ylim(-0.6, n - 0.4)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(C["border"])
    ax.spines["bottom"].set_color(C["border"])

    # Legend
    handles = [
        mpatches.Patch(color=C["PASS"],           label="PASS — fires on main today"),
        mpatches.Patch(color=C["STAGED"],          label="STAGED — files on main, pnpm pending"),
        mpatches.Patch(color=C["NOT-YET-WIRED"],   label="NOT-YET-WIRED — Cursor deliverable"),
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=8.5,
              facecolor=C["card"], edgecolor=C["border"],
              labelcolor=C["text"])

    fig.suptitle(
        "SZL Anatomy-Alive — 7-Layer Execution Timeline\n"
        "trace_id: anatomy-alive-trace-20260530T000000Z  |  "
        "formula: AdversarialRobustness  |  Doctrine v6",
        color=C["text"], fontsize=11, y=1.01, ha="center"
    )

    out_path = OUT / "sequence_with_timing.png"
    plt.tight_layout()
    plt.savefig(out_path, dpi=180, bbox_inches="tight",
                facecolor=C["bg"], edgecolor="none")
    plt.close()
    print(f"  ✓ {out_path}")


# =============================================================================
# 2. Receipt DAG
# =============================================================================

def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:12]

def build_receipt_dag():
    """
    Generate synthetic DSSE receipt chain for one anatomy-alive trace.
    Receipts form a DAG: each receipt references the hash of its predecessor.
    """
    HMAC_KEY = b"szl-formula-hmac-dev-v1"

    def make_receipt(layer, formula, inputs, prev_hash, lean_theorem, lean_file):
        ih = _sha(json.dumps(inputs, sort_keys=True))
        ts = "2026-05-30T00:00:00.000Z"
        payload = {
            "layer": layer,
            "formula": formula,
            "inputs_hash": ih,
            "lean_theorem": lean_theorem,
            "lean_file": lean_file,
            "lean_commit_sha": "1dca00032dfc9aa8559cc6c2e4b63192fcf52371",
            "prev_receipt_hash": prev_hash,
            "timestamp": ts,
        }
        h = _sha(json.dumps(payload, sort_keys=True))
        return {**payload, "receipt_hash": h}

    receipts = []
    prev = "0" * 12  # genesis

    chain = [
        (1, "AdversarialRobustness",  {"theorem": "robustness_preserved_by_composition"},
         "robustness_preserved_by_composition", "Lutar/Composition/AdversarialRobustness.lean"),
        (2, "adversarialRobustness",  {"l1": 2.0, "l2": 1.5, "delta": 0.1},
         "robustness_preserved_by_composition", "Lutar/Composition/AdversarialRobustness.lean"),
        (4, "OTelSpan",               {"spanId": "aa-span-0001", "lambda": 0.9208},
         "robustness_preserved_by_composition", "Lutar/Composition/AdversarialRobustness.lean"),
        (5, "DSSEReceipt",            {"formula": "AdversarialRobustness", "epsilon2": 0.3},
         "robustness_preserved_by_composition", "Lutar/Composition/AdversarialRobustness.lean"),
        (6, "PolicyGate",             {"gate": "adversarialRobustnessGate", "allow": True},
         "robustness_preserved_by_composition", "Lutar/Composition/AdversarialRobustness.lean"),
    ]
    for layer, formula, inputs, lt, lf in chain:
        r = make_receipt(layer, formula, inputs, prev, lt, lf)
        receipts.append(r)
        prev = r["receipt_hash"]

    return receipts


def make_receipt_dag_png():
    receipts = build_receipt_dag()

    fig, ax = plt.subplots(figsize=(16, 5))
    fig.patch.set_facecolor(C["bg"])
    ax.set_facecolor(C["card"])

    node_x = [i * 2.8 for i in range(len(receipts))]
    node_y = [0] * len(receipts)
    colors = [C["PASS"], C["PASS"], C["STAGED"], C["PASS"], C["PASS"]]
    labels = [
        f"L{r['layer']}\n{r['formula'][:12]}\n#{r['receipt_hash'][:8]}…"
        for r in receipts
    ]

    for i, (x, y, col, lab) in enumerate(zip(node_x, node_y, colors, labels)):
        circle = plt.Circle((x, y), 0.75, color=col, alpha=0.85, zorder=3)
        ax.add_patch(circle)
        ax.text(x, y, lab, ha="center", va="center",
                fontsize=7.5, color="white", fontweight="bold", zorder=4,
                linespacing=1.4)
        # prev_hash arrow
        if i > 0:
            ax.annotate("",
                xy=(x - 0.76, y), xytext=(node_x[i-1] + 0.76, y),
                arrowprops=dict(
                    arrowstyle="->", color="#58a6ff",
                    lw=2.0, connectionstyle="arc3,rad=0"
                ), zorder=5)
            # hash label on arrow
            prev_h = receipts[i]["prev_receipt_hash"]
            mid_x = (node_x[i-1] + x) / 2
            ax.text(mid_x, 0.85, f"prev={prev_h[:8]}…",
                    ha="center", va="bottom", fontsize=7,
                    color=C["muted"])

        # Layer label below
        ax.text(x, -1.1,
                f"L{receipts[i]['layer']} · {receipts[i]['formula'][:18]}",
                ha="center", va="top", fontsize=8, color=C["muted"])

        # Lean ref above
        lt = receipts[i].get("lean_theorem", "")[:28]
        ax.text(x, 1.05, lt, ha="center", va="bottom",
                fontsize=6.5, color="#a371f7", style="italic")

    # Genesis marker
    ax.text(node_x[0] - 2.0, 0, "GENESIS\n(prev=000…)", ha="center", va="center",
            fontsize=8, color=C["muted"], style="italic")
    ax.annotate("",
        xy=(node_x[0] - 0.77, 0), xytext=(node_x[0] - 1.5, 0),
        arrowprops=dict(arrowstyle="->", color=C["muted"], lw=1.5))

    ax.set_xlim(-2.8, node_x[-1] + 1.8)
    ax.set_ylim(-1.8, 1.8)
    ax.axis("off")

    fig.suptitle(
        "SZL Anatomy-Alive — DSSE Receipt Dependency DAG\n"
        "Each receipt carries SHA-256(prev_receipt) for tamper evidence  |  "
        "Lean theorem: robustness_preserved_by_composition  |  Doctrine v6",
        color=C["text"], fontsize=10, y=1.04
    )

    out_path = OUT / "receipt_dag.png"
    plt.tight_layout()
    plt.savefig(out_path, dpi=180, bbox_inches="tight",
                facecolor=C["bg"], edgecolor="none")
    plt.close()
    print(f"  ✓ {out_path}")
    return receipts


def make_receipt_dag_html(receipts):
    import plotly.graph_objects as go

    n = len(receipts)
    xs = [i * 300 for i in range(n)]
    ys = [0] * n
    status_colors = ["#1a7f37", "#1a7f37", "#9a6700", "#1a7f37", "#1a7f37"]

    node_trace = go.Scatter(
        x=xs, y=ys, mode="markers+text",
        marker=dict(size=60, color=status_colors, opacity=0.9,
                    line=dict(color="white", width=2)),
        text=[f"L{r['layer']}<br>{r['formula'][:14]}<br>#{r['receipt_hash'][:8]}…"
              for r in receipts],
        textposition="middle center",
        textfont=dict(color="white", size=10, family="monospace"),
        hovertemplate=[
            f"<b>Layer {r['layer']}</b><br>"
            f"Formula: {r['formula']}<br>"
            f"Lean: {r['lean_theorem']}<br>"
            f"Receipt: {r['receipt_hash']}<br>"
            f"Prev: {r['prev_receipt_hash']}<br>"
            f"<extra></extra>"
            for r in receipts
        ],
        name="Receipt nodes",
    )

    edge_traces = []
    for i in range(1, n):
        edge_traces.append(go.Scatter(
            x=[xs[i-1], xs[i]], y=[0, 0],
            mode="lines",
            line=dict(color="#58a6ff", width=2.5),
            showlegend=False,
            hoverinfo="skip",
        ))
        edge_traces.append(go.Scatter(
            x=[(xs[i-1]+xs[i])/2], y=[18],
            mode="text",
            text=[f"prev={receipts[i]['prev_receipt_hash'][:8]}…"],
            textfont=dict(size=9, color="#8b949e"),
            showlegend=False,
            hoverinfo="skip",
        ))

    lean_traces = [go.Scatter(
        x=[xs[i]], y=[-42],
        mode="text",
        text=[f"{receipts[i]['lean_theorem'][:30]}…"],
        textfont=dict(size=9, color="#a371f7", family="monospace"),
        showlegend=False, hoverinfo="skip",
    ) for i in range(n)]

    fig = go.Figure(data=edge_traces + lean_traces + [node_trace])
    fig.update_layout(
        title=dict(
            text="SZL Anatomy-Alive — DSSE Receipt Dependency DAG (interactive)<br>"
                 "<sup>Hover nodes for full receipt fields  |  "
                 "Doctrine v6  |  trace_id: anatomy-alive-trace-20260530T000000Z</sup>",
            font=dict(color="#e6edf3", size=14),
        ),
        paper_bgcolor="#0d1117",
        plot_bgcolor="#161b22",
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False,
                   range=[-100, xs[-1]+200]),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False,
                   range=[-80, 60]),
        showlegend=False,
        margin=dict(l=20, r=20, t=100, b=20),
        height=420,
    )
    out_path = OUT / "receipt_dag.html"
    fig.write_html(str(out_path), include_plotlyjs="cdn")
    print(f"  ✓ {out_path}")


# =============================================================================
# 3. Formula-witness flow chart
# =============================================================================

def make_formula_witness_flow():
    """
    5 anchor formulas (rows) × 7 layers (columns) firing matrix.
    Color coded: green=PASS, amber=STAGED, grey=NOT-YET-WIRED.
    Lean theorem name displayed as annotation below each active cell.
    """
    n_formulas = len(FORMULAS)
    n_layers   = 7
    layer_labels = [f"L{i+1}\n{ld['organ']}" for i, ld in enumerate(LAYER_DATA)]
    formula_labels = [f["label"] for f in FORMULAS]

    # Build value matrix
    matrix = np.array([FORMULA_LAYER_MATRIX[f["id"]] for f in FORMULAS])

    fig, ax = plt.subplots(figsize=(18, 8))
    fig.patch.set_facecolor(C["bg"])
    ax.set_facecolor(C["bg"])

    cell_w, cell_h = 1.0, 1.0
    pad = 0.06

    for fi in range(n_formulas):
        for li in range(n_layers):
            val = matrix[fi, li]
            x   = li * cell_w
            y   = (n_formulas - 1 - fi) * cell_h

            if val == 1:
                fc  = C["formula"][FORMULAS[fi]["id"]]
                alpha = 0.88
                status_text = "PASS"
            elif val == 0.5:
                fc  = C["STAGED"]
                alpha = 0.75
                status_text = "STAGED"
            elif val == 0:
                fc  = "#21262d"
                alpha = 0.7
                status_text = "—"
            else:
                fc  = C["NOT-YET-WIRED"]
                alpha = 0.5
                status_text = "N/A"

            rect = FancyBboxPatch(
                (x + pad, y + pad),
                cell_w - 2*pad, cell_h - 2*pad,
                boxstyle="round,pad=0.02",
                facecolor=fc, alpha=alpha,
                edgecolor="white" if val > 0 else C["border"],
                linewidth=1.0, zorder=3
            )
            ax.add_patch(rect)

            # Status label
            ax.text(x + cell_w/2, y + cell_h*0.62,
                    status_text, ha="center", va="center",
                    fontsize=8, fontweight="bold",
                    color="white" if val > 0 else C["muted"], zorder=4)

            # Lean theorem ref (abbreviated) only for fired cells
            if val >= 0.5:
                lt = FORMULAS[fi]["lean_theorem"]
                # Wrap at 18 chars
                if len(lt) > 18:
                    lt_disp = lt[:16] + "…"
                else:
                    lt_disp = lt
                ax.text(x + cell_w/2, y + cell_h*0.28,
                        lt_disp, ha="center", va="center",
                        fontsize=5.5, color="white", alpha=0.85,
                        style="italic", zorder=4)

    # Axis labels
    ax.set_xlim(-0.05, n_layers * cell_w + 0.05)
    ax.set_ylim(-0.8, n_formulas * cell_h + 0.3)

    ax.set_xticks([i + 0.5 for i in range(n_layers)])
    ax.set_xticklabels(layer_labels, fontsize=9, color=C["text"],
                       linespacing=1.3)
    ax.set_yticks([(n_formulas - 1 - i) + 0.5 for i in range(n_formulas)])
    ax.set_yticklabels(formula_labels, fontsize=10, color=C["text"],
                       fontweight="bold")
    ax.tick_params(length=0)
    ax.spines[:].set_visible(False)

    # Lean file refs below the chart
    ax.set_xlabel("")
    for fi, fm in enumerate(FORMULAS):
        fc = C["formula"][fm["id"]]
        y_text = -0.55
        x_text = -0.02 + fi * (n_layers * cell_w + 0.1) / n_formulas
        ax.text(0 + fi * 0.01, -0.55 - fi * 0.12,
                f"{'·'*2} {fm['lean_file']}",
                ha="left", va="top", fontsize=6.5,
                color=fc, alpha=0.8, style="italic")

    # Legend
    handles = [
        mpatches.Patch(color=C["formula"]["adversarial_robustness"], label="Formula fires — PASS"),
        mpatches.Patch(color=C["STAGED"],                             label="Formula staged — STAGED"),
        mpatches.Patch(color="#21262d", label="Not exercised at this layer"),
    ]
    ax.legend(handles=handles, loc="upper right",
              fontsize=8.5, facecolor=C["card"],
              edgecolor=C["border"], labelcolor=C["text"],
              bbox_to_anchor=(1.0, 1.12))

    fig.suptitle(
        "SZL Anatomy-Alive — Formula Witness Flow: 5 Anchor Formulas × 7 Layers\n"
        "Lean theorem ref shown in each active cell  |  Doctrine v6",
        color=C["text"], fontsize=11, y=1.04
    )

    out_path = OUT / "formula_witness_flow.png"
    plt.tight_layout(pad=1.5)
    plt.savefig(out_path, dpi=180, bbox_inches="tight",
                facecolor=C["bg"], edgecolor="none")
    plt.close()
    print(f"  ✓ {out_path}")


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    print("Generating anatomy-alive visual artifacts...")
    print()

    print("1/4  Sequence timeline PNG...")
    make_sequence_png()

    print("2/4  Receipt DAG PNG + HTML...")
    receipts = make_receipt_dag_png()
    make_receipt_dag_html(receipts)

    print("3/4  Formula witness flow PNG...")
    make_formula_witness_flow()

    print()
    print("All diagrams written to:", OUT)
