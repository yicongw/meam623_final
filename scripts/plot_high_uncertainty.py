#!/usr/bin/env python3
"""Slide-ready figures from high_uncertainty.csv (96 cells).

Output (output/):
  fig_hu_collisions.png   — collision counts vs pct (reactive on/off, fallback/no)
  fig_hu_qover.png        — boxplot of q-limit overshoot (the reversal)
  fig_hu_sc_dist.png      — min self-collision distance vs pct (line + band)
  fig_hu_metrics.png      — 2x2 panel summary
"""

from __future__ import annotations

import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, os.pardir))
_OUTPUT_DIR = os.path.join(_PROJECT_ROOT, "output")
CSV = os.path.join(_OUTPUT_DIR, "high_uncertainty.csv")

# Midnight Executive-ish palette
COL_FBK   = "#1E2761"  # deep navy   = with fallback
COL_NFB   = "#D7263D"  # coral red   = no fallback
EDGECOL   = "#0B0B2B"

plt.rcParams.update({
    "font.family":      "DejaVu Sans",
    "axes.titleweight": "bold",
    "axes.titlesize":   13,
    "axes.labelsize":   12,
    "legend.fontsize":  11,
    "xtick.labelsize":  11,
    "ytick.labelsize":  11,
    "figure.dpi":       110,
})


# -----------------------------------------------------------------
def fig_collisions(df, out):
    pcts   = sorted(df["pct"].unique())
    modes  = ["fallback", "no_fallback"]
    reacts = ["obs_react", "obs_noreact"]
    n_seeds = df["seed"].nunique()

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True)
    width = 0.35

    for ax, react in zip(axes, reacts):
        x = np.arange(len(pcts))
        fbk = [int(df[(df["label"]==react)&(df["pct"]==p)
                      &(df["mode"]=="fallback")]["self_collided"].sum())
               for p in pcts]
        nfb = [int(df[(df["label"]==react)&(df["pct"]==p)
                      &(df["mode"]=="no_fallback")]["self_collided"].sum())
               for p in pcts]
        b1 = ax.bar(x-width/2, fbk, width,
                    label="With fallback",
                    color=COL_FBK, edgecolor=EDGECOL, linewidth=0.7)
        b2 = ax.bar(x+width/2, nfb, width,
                    label="No fallback",
                    color=COL_NFB, edgecolor=EDGECOL, linewidth=0.7,
                    hatch="//")
        ax.set_xticks(x)
        ax.set_xticklabels([f"{int(p)}%" for p in pcts])
        ax.set_xlabel("Link-mass perturbation")
        # Tight y-axis: max collisions seen across the data
        y_max = max(max(fbk + nfb), 2)
        ax.set_ylim(0, y_max + 0.5)
        ax.set_yticks(range(0, y_max + 1))
        title = ("With reactive evasion (default)" if react == "obs_react"
                 else "Reactive evasion disabled")
        ax.set_title(title)
        ax.grid(axis="y", linestyle=":", alpha=0.6)
        for bar, v in list(zip(b1, fbk)) + list(zip(b2, nfb)):
            ax.text(bar.get_x()+bar.get_width()/2, v+0.08, str(v),
                    ha="center", va="bottom", fontsize=10)

    axes[0].set_ylabel(f"# self-collisions  (of {n_seeds} seeds)")
    axes[0].legend(loc="upper left", frameon=True)
    fig.suptitle("Self-collision count under mass perturbation",
                 fontsize=14, y=1.00, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out, dpi=180, bbox_inches="tight")
    print(f"  saved -> {out}")


# -----------------------------------------------------------------
def fig_qover(df, out):
    """Show the reversal: fallback q_over ALWAYS ≥ no_fallback q_over.

    Strip-plot: each dot = one (reactive_mode, seed) cell.  Mean shown as
    horizontal bar.  no_fallback values are exactly 0, so dots stack on
    the baseline — that's the visual punch line.
    """
    pcts = sorted(df["pct"].unique())
    rng = np.random.RandomState(0)

    fig, ax = plt.subplots(figsize=(10, 5.0))
    width = 0.34
    x = np.arange(len(pcts))

    for i, p in enumerate(pcts):
        for mode, color, dx, label in [
                ("fallback",    COL_FBK, -width/2, "With fallback"),
                ("no_fallback", COL_NFB, +width/2, "No fallback")]:
            vals = (df[(df["pct"]==p)&(df["mode"]==mode)]
                    ["max_q_violation"].dropna().values * 1000)
            jitter = (rng.rand(len(vals)) - 0.5) * width * 0.7
            ax.scatter(x[i] + dx + jitter, vals,
                       s=46, color=color, edgecolor=EDGECOL,
                       linewidth=0.6, alpha=0.85, zorder=3,
                       label=label if i == 0 else None)
            # Mean bar
            mean = vals.mean() if len(vals) else 0
            ax.plot([x[i] + dx - width*0.4, x[i] + dx + width*0.4],
                    [mean, mean], color=color, linewidth=3.0, zorder=4)
            # Mean numerical label
            ax.text(x[i] + dx, mean + 0.5, f"{mean:.1f}",
                    ha="center", va="bottom", fontsize=9.5,
                    color=color, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels([f"{int(p)}%" for p in pcts])
    ax.set_xlabel("Link-mass perturbation")
    ax.set_ylabel("Joint-position-limit overshoot  [mm]")
    ax.set_title("Joint-limit overshoot is concentrated in the fallback layer\n"
                 "(each dot = one seed × reactive-mode cell;  bar = mean)",
                 fontsize=13, fontweight="bold")
    ax.axhline(0, color="black", linewidth=0.7)
    ax.grid(axis="y", linestyle=":", alpha=0.6)
    ax.set_ylim(-1.0, None)
    # Dedup legend
    handles, labels = ax.get_legend_handles_labels()
    seen = set(); H = []; L = []
    for h, l in zip(handles, labels):
        if l not in seen:
            seen.add(l); H.append(h); L.append(l)
    ax.legend(H, L, loc="upper left", frameon=True)

    fig.tight_layout()
    fig.savefig(out, dpi=180, bbox_inches="tight")
    print(f"  saved -> {out}")


# -----------------------------------------------------------------
def fig_sc_dist(df, out):
    """min self-collision distance vs pct, lines for fallback vs no_fallback,
    split into reactive on/off subplots."""
    pcts = sorted(df["pct"].unique())
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True)

    for ax, react in zip(axes, ["obs_react", "obs_noreact"]):
        for mode, color, label in [("fallback", COL_FBK, "With fallback"),
                                    ("no_fallback", COL_NFB, "No fallback")]:
            sub = df[(df["label"]==react)&(df["mode"]==mode)]
            g = sub.groupby("pct")["min_self_dist"]
            mean = g.mean().reindex(pcts).values * 100
            mn   = g.min().reindex(pcts).values  * 100
            mx   = g.max().reindex(pcts).values  * 100
            ax.plot(pcts, mean, "-o", color=color, label=label,
                    linewidth=2.4, markersize=7)
            ax.fill_between(pcts, mn, mx, color=color, alpha=0.15)
        ax.axhline(0, color="black", linestyle="--", linewidth=0.9,
                   label="self-collision")
        ax.set_xlabel("Link-mass perturbation [%]")
        title = ("With reactive evasion (default)" if react == "obs_react"
                 else "Reactive evasion disabled")
        ax.set_title(title)
        ax.grid(linestyle=":", alpha=0.6)

    axes[0].set_ylabel("min  self-collision distance  [cm]")
    axes[0].legend(loc="lower left", frameon=True)
    fig.suptitle("Self-collision distance under mass perturbation",
                 fontsize=14, y=1.00, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out, dpi=180, bbox_inches="tight")
    print(f"  saved -> {out}")


# -----------------------------------------------------------------
def fig_metrics(df, out):
    """2×2 summary panel for the "with-reactive" sweep (the more interesting one)."""
    sub = df[df["label"]=="obs_react"].copy()
    pcts = sorted(sub["pct"].unique())

    fig, axes = plt.subplots(2, 2, figsize=(11, 7), sharex=True)

    def line(ax, col, ylabel, scale=1.0, hline=None):
        for mode, color, label in [("fallback", COL_FBK, "With fallback"),
                                    ("no_fallback", COL_NFB, "No fallback")]:
            g = sub[sub["mode"]==mode].groupby("pct")[col]
            mean = g.mean().reindex(pcts).values * scale
            mn   = g.min().reindex(pcts).values  * scale
            mx   = g.max().reindex(pcts).values  * scale
            ax.plot(pcts, mean, "-o", color=color, label=label,
                    linewidth=2.4, markersize=7)
            ax.fill_between(pcts, mn, mx, color=color, alpha=0.15)
        if hline is not None:
            ax.axhline(hline, color="black", linestyle="--", linewidth=0.8)
        ax.set_ylabel(ylabel)
        ax.grid(linestyle=":", alpha=0.6)

    line(axes[0,0], "min_self_dist", "min  $d_{sc}$  [cm]", scale=100, hline=0)
    axes[0,0].set_title("(a) Self-collision distance  (>0 safe)")
    axes[0,0].legend(loc="lower left")

    line(axes[0,1], "min_gamma", "min  $\\Gamma$", hline=0)
    axes[0,1].set_title("(b) Predicted self-collision margin")

    line(axes[1,0], "max_qd_abs", "max  $|\\dot q|$  [rad/s]", hline=2.61)
    axes[1,0].set_title("(c) Joint-velocity peak")
    axes[1,0].set_xlabel("Link-mass perturbation [%]")

    line(axes[1,1], "max_q_violation", "max  q-overshoot  [mm]",
         scale=1000, hline=0)
    axes[1,1].set_title("(d) Joint-position-limit violation")
    axes[1,1].set_xlabel("Link-mass perturbation [%]")

    fig.suptitle("VPP-TC under mass perturbation  (reactive evasion ON)",
                 fontsize=14, y=1.00, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out, dpi=180, bbox_inches="tight")
    print(f"  saved -> {out}")


def main():
    df = pd.read_csv(CSV)
    print(f"Loaded {len(df)} rows from {CSV}")
    fig_collisions(df, os.path.join(_OUTPUT_DIR, "fig_hu_collisions.png"))
    fig_qover    (df, os.path.join(_OUTPUT_DIR, "fig_hu_qover.png"))
    fig_sc_dist  (df, os.path.join(_OUTPUT_DIR, "fig_hu_sc_dist.png"))
    fig_metrics  (df, os.path.join(_OUTPUT_DIR, "fig_hu_metrics.png"))


if __name__ == "__main__":
    main()
