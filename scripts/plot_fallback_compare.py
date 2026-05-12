#!/usr/bin/env python3
"""Plot fallback vs no-fallback comparison.

Output: two side-by-side figures in output/
  fig_fallback_collisions.png
      Bar chart: # collisions out of 3 seeds, grouped by pct, two bars per
      group (fallback / no_fallback).  Shows the safety contribution of the
      fallback layer.
  fig_fallback_metrics.png
      2x2 panel:
        (a) min self-collision distance vs pct  (lines: fallback, no_fallback)
        (b) min Gamma vs pct
        (c) max |q̇|  vs pct  (clipped to 100)
        (d) max q-limit overshoot vs pct  (mm)
      Each line shows mean across 3 seeds with markers; shaded band = min/max.
"""

import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, os.pardir))
_OUTPUT_DIR = os.path.join(_PROJECT_ROOT, "output")
CSV = os.path.join(_OUTPUT_DIR, "fallback_compare.csv")

COL_FBK = "#1f77b4"   # blue   = with fallback (safe baseline)
COL_NFB = "#d62728"   # red    = no fallback   (unsafe ablation)


def make_collision_bar(df, out_path):
    pcts = sorted(df["pct"].unique())
    width = 0.35
    x = np.arange(len(pcts))

    fbk_counts = [int(df[(df["mode"] == "fallback")    & (df["pct"] == p)]
                       ["self_collided"].sum()) for p in pcts]
    nfb_counts = [int(df[(df["mode"] == "no_fallback") & (df["pct"] == p)]
                       ["self_collided"].sum()) for p in pcts]

    fig, ax = plt.subplots(figsize=(7, 4))
    bars1 = ax.bar(x - width/2, fbk_counts, width,
                   label="With fallback", color=COL_FBK,
                   edgecolor="black", linewidth=0.6)
    bars2 = ax.bar(x + width/2, nfb_counts, width,
                   label="No fallback",   color=COL_NFB,
                   edgecolor="black", linewidth=0.6, hatch="//")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{int(p)}%" for p in pcts])
    ax.set_xlabel("Link-mass perturbation")
    ax.set_ylabel("# self-collisions  (of 3 seeds)")
    ax.set_yticks(range(0, 4))
    ax.set_ylim(0, 3.6)
    ax.set_title("Self-collisions vs. mass perturbation\n"
                 "(VPP-TC obstacle scenario, ε=0)")
    ax.legend(loc="upper left", frameon=True)
    ax.grid(True, axis="y", linestyle=":", alpha=0.5)

    for bar, v in list(zip(bars1, fbk_counts)) + list(zip(bars2, nfb_counts)):
        ax.text(bar.get_x() + bar.get_width()/2, v + 0.05, str(v),
                ha="center", va="bottom", fontsize=9)

    fig.tight_layout()
    fig.savefig(out_path, dpi=180)
    print(f"  saved -> {out_path}")


def _agg(df, mode, col):
    sub = df[df["mode"] == mode].copy()
    g = sub.groupby("pct")[col]
    return g.mean().to_numpy(), g.min().to_numpy(), g.max().to_numpy()


def make_metrics_panel(df, out_path):
    pcts = sorted(df["pct"].unique())

    fig, axes = plt.subplots(2, 2, figsize=(11, 7), sharex=True)

    # (a) min_self_dist (cm)
    ax = axes[0, 0]
    for mode, color, label in [("fallback", COL_FBK, "With fallback"),
                                ("no_fallback", COL_NFB, "No fallback")]:
        m, lo, hi = _agg(df, mode, "min_self_dist")
        ax.plot(pcts, m * 100, "-o", color=color, label=label, linewidth=2)
        ax.fill_between(pcts, lo * 100, hi * 100, color=color, alpha=0.15)
    ax.axhline(0, color="black", linestyle="--", linewidth=0.8)
    ax.set_ylabel("min  $d_{sc}$  [cm]")
    ax.set_title("(a) Self-collision distance  (>0 safe)")
    ax.legend(loc="lower left")
    ax.grid(True, linestyle=":", alpha=0.5)

    # (b) min_gamma
    ax = axes[0, 1]
    for mode, color, label in [("fallback", COL_FBK, "With fallback"),
                                ("no_fallback", COL_NFB, "No fallback")]:
        m, lo, hi = _agg(df, mode, "min_gamma")
        ax.plot(pcts, m, "-o", color=color, label=label, linewidth=2)
        ax.fill_between(pcts, lo, hi, color=color, alpha=0.15)
    ax.axhline(0, color="black", linestyle="--", linewidth=0.8)
    ax.set_ylabel("min  $\\Gamma$")
    ax.set_title("(b) Predicted self-collision margin  (>0 safe)")
    ax.grid(True, linestyle=":", alpha=0.5)

    # (c) max |q̇|
    ax = axes[1, 0]
    for mode, color, label in [("fallback", COL_FBK, "With fallback"),
                                ("no_fallback", COL_NFB, "No fallback")]:
        m, lo, hi = _agg(df, mode, "max_qd_abs")
        ax.plot(pcts, m, "-o", color=color, label=label, linewidth=2)
        ax.fill_between(pcts, lo, hi, color=color, alpha=0.15)
    ax.axhline(2.61, color="green", linestyle="--", linewidth=0.8,
               label="hardware $\\dot q_{lim}$")
    ax.set_xlabel("link-mass perturbation [%]")
    ax.set_ylabel("max  $|\\dot q|$  [rad/s]")
    ax.set_title("(c) Joint-velocity peak")
    ax.legend(loc="upper left")
    ax.grid(True, linestyle=":", alpha=0.5)

    # (d) max q overshoot (mm)
    ax = axes[1, 1]
    for mode, color, label in [("fallback", COL_FBK, "With fallback"),
                                ("no_fallback", COL_NFB, "No fallback")]:
        m, lo, hi = _agg(df, mode, "max_q_violation")
        ax.plot(pcts, m * 1000, "-o", color=color, label=label, linewidth=2)
        ax.fill_between(pcts, lo * 1000, hi * 1000, color=color, alpha=0.15)
    ax.axhline(0, color="black", linestyle="--", linewidth=0.8)
    ax.set_xlabel("link-mass perturbation [%]")
    ax.set_ylabel("max  $q$-limit overshoot  [mm]")
    ax.set_title("(d) Joint-position limit violation")
    ax.grid(True, linestyle=":", alpha=0.5)

    fig.suptitle("VPP-TC under mass perturbation: with vs without "
                 "gravity-comp + damping fallback",
                 fontsize=12, y=1.00)
    fig.tight_layout()
    fig.savefig(out_path, dpi=180)
    print(f"  saved -> {out_path}")


def main():
    if not os.path.exists(CSV):
        raise SystemExit(f"missing {CSV} — run sweep_fallback_compare.py first")
    df = pd.read_csv(CSV)
    print(f"Loaded {len(df)} rows from {CSV}")

    out_bar = os.path.join(_OUTPUT_DIR, "fig_fallback_collisions.png")
    out_panel = os.path.join(_OUTPUT_DIR, "fig_fallback_metrics.png")

    make_collision_bar(df, out_bar)
    make_metrics_panel(df, out_panel)


if __name__ == "__main__":
    main()
