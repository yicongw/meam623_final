#!/usr/bin/env python3
"""Section 2 poster figure: VPP-TC vs CFC ablation under model mismatch.

Aggressive scenario: target = (0.10, -0.10, 0.20), planner_gain = 300,
no obstacles, no SDF reactive evasion -- the QP alone has to keep the arm
out of self-collision and below joint-velocity limits.

Reads:
    output/sweep_mismatch_aggr.csv
    output/run_*_aggr_a*_vpptc.csv  /  *_cfc.csv

Layout (15:6 figure):
    A. self-collision distance over time, VPP-TC vs CFC, alpha = 1.0
    B. min self-collision distance vs alpha, both controllers
    C. Gamma(t) vs CFC behaviour, plus 'who completed the task' table

Saves   C:/Users/wangy/Desktop/poster_fig2.png  (300 dpi).
"""

from __future__ import annotations

import argparse
import os
from typing import Dict

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import gridspec
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, os.pardir))
_OUTPUT_DIR  = os.path.join(_PROJECT_ROOT, "output")

C_VPPTC = "#1F4E79"
C_CFC   = "#C0392B"
C_SAFE  = "#27AE60"
C_DANG  = "#E67E22"
C_GREY  = "#888888"


def get_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=str,
                    default=os.path.join(_OUTPUT_DIR, "sweep_mismatch_aggr.csv"))
    ap.add_argument("--out", type=str,
                    default=r"C:/Users/wangy/Desktop/poster_fig2.png")
    return ap.parse_args()


def find_run(alpha: float, mode: str, tag_prefix: str = "aggr") -> str:
    tag = f"{tag_prefix}_a{alpha:0.2f}_{mode}".replace(".", "p")
    candidates = [f for f in os.listdir(_OUTPUT_DIR)
                  if f.startswith("run_") and f.endswith(f"_{tag}.csv")]
    if not candidates:
        raise FileNotFoundError(tag)
    return os.path.join(_OUTPUT_DIR,
                        max(candidates,
                            key=lambda f: os.path.getmtime(
                                os.path.join(_OUTPUT_DIR, f))))


def smooth(y, k=9):
    if len(y) < k:
        return y
    return np.convolve(y, np.ones(k) / k, mode="same")


def main():
    args = get_args()
    summary = pd.read_csv(args.csv).sort_values(["alpha", "mode"])
    alphas  = np.sort(summary["alpha"].unique())
    pct     = (alphas - 1.0) * 100.0

    # Per-alpha pivot
    s_vpptc = summary[summary["mode"] == "vpptc"].set_index("alpha").loc[alphas]
    s_cfc   = summary[summary["mode"] == "cfc"  ].set_index("alpha").loc[alphas]

    fig = plt.figure(figsize=(15, 6), dpi=300)
    gs  = gridspec.GridSpec(
        1, 3, figure=fig,
        width_ratios=[1.15, 1.0, 1.0],
        wspace=0.34,
        left=0.055, right=0.985, top=0.83, bottom=0.14,
    )

    # ------------------------------------------------------------------ #
    # Panel A: sc_dist(t) and Gamma(t) at alpha = 1.0                     #
    # ------------------------------------------------------------------ #
    axA1 = fig.add_subplot(gs[0, 0])
    df_v = pd.read_csv(find_run(1.0, "vpptc"))
    df_c = pd.read_csv(find_run(1.0, "cfc"))

    # sc_dist in cm
    axA1.plot(df_v["time"], smooth(df_v["self_collision_dist"]) * 100.0,
              color=C_VPPTC, lw=2.4, label="VPP-TC", zorder=5)
    axA1.plot(df_c["time"], smooth(df_c["self_collision_dist"]) * 100.0,
              color=C_CFC, lw=2.4, label="CFC (no viability, no $\\Gamma$)", zorder=4)

    # Mark CFC's collision instant
    cfc_collide_idx = df_c.index[df_c["self_collision_dist"] < 0]
    if len(cfc_collide_idx) > 0:
        t_coll = df_c["time"].iloc[cfc_collide_idx[0]]
        axA1.axvline(t_coll, color=C_CFC, lw=0.8, ls=":", alpha=0.6)
        axA1.annotate(f"CFC self-collision\n@ t = {t_coll:.2f} s",
                      xy=(t_coll, 0), xycoords="data",
                      xytext=(t_coll + 0.4, 1.5), textcoords="data",
                      fontsize=9, color=C_CFC,
                      arrowprops=dict(arrowstyle="->", color=C_CFC, lw=1.0),
                      bbox=dict(boxstyle="round,pad=0.3", fc="white",
                                ec=C_CFC, lw=1.0, alpha=0.95))

    axA1.axhline(0, color="k", lw=0.8, ls="--", alpha=0.55)
    axA1.set_xlabel("time [s]", fontsize=11)
    axA1.set_ylabel(r"min self-collision dist  $d_{\mathrm{sc}}(t)$  [cm]",
                    fontsize=11)
    axA1.set_title(r"A. Aggressive scenario @ $\alpha = 1$ (perfect inertia)",
                   fontsize=12, weight="bold", loc="left", pad=8)
    axA1.grid(True, alpha=0.25)
    axA1.legend(loc="upper right", fontsize=10, frameon=True)
    # Limit time axis to where both trajectories exist
    axA1.set_xlim(0, max(df_v["time"].max(), df_c["time"].max()) * 1.02)

    # ------------------------------------------------------------------ #
    # Panel B: min sc_dist vs alpha for both controllers                  #
    # ------------------------------------------------------------------ #
    axB = fig.add_subplot(gs[0, 1])

    sc_v = s_vpptc["min_self_dist"].to_numpy() * 100.0  # cm
    sc_c = s_cfc  ["min_self_dist"].to_numpy() * 100.0
    coll_v = s_vpptc["self_collided"].to_numpy()
    coll_c = s_cfc  ["self_collided"].to_numpy()

    axB.plot(pct, sc_v, "o-", color=C_VPPTC, lw=2.2, ms=8,
             label="VPP-TC")
    axB.plot(pct, sc_c, "s-", color=C_CFC, lw=2.2, ms=8,
             label="CFC")

    # Mark collision points on CFC
    if coll_c.any():
        axB.scatter(pct[coll_c], sc_c[coll_c],
                    s=220, marker="x", color="black", lw=2.5, zorder=10,
                    label="CFC collision")

    axB.axhline(0, color="k", lw=0.9, ls="--", alpha=0.7)
    axB.fill_between(pct, -1.0, 0.0, color=C_CFC, alpha=0.10)
    axB.text(pct[0] + 5, -0.55, "self-collision",
             fontsize=8.5, color=C_CFC, alpha=0.8, style="italic")

    axB.set_xlabel(r"Inertia mismatch  $(\alpha - 1)\!\times\!100\%$",
                   fontsize=11)
    axB.set_ylabel(r"min $d_{\mathrm{sc}}$  [cm]", fontsize=11)
    axB.set_title("B. Safety margin vs inertia mismatch",
                  fontsize=12, weight="bold", loc="left", pad=8)
    axB.grid(True, alpha=0.25)
    axB.set_ylim(-1.0, max(sc_v.max(), sc_c.max()) * 1.15)
    axB.axvline(0, color="k", lw=0.5, alpha=0.4)
    axB.legend(loc="lower right", fontsize=10, frameon=True)

    n_coll_v = int(coll_v.sum())
    n_coll_c = int(coll_c.sum())
    n = len(pct)
    axB.text(0.02, 0.97,
             f"VPP-TC: {n - n_coll_v}/{n} safe\n"
             f"CFC:    {n - n_coll_c}/{n} safe",
             transform=axB.transAxes, fontsize=10, va="top",
             family="monospace",
             bbox=dict(boxstyle="round,pad=0.35", fc="white",
                       ec=C_VPPTC, lw=1.2, alpha=0.95))

    # ------------------------------------------------------------------ #
    # Panel C: Gamma(t) at alpha=1.0  +  "task completed" annotation     #
    # ------------------------------------------------------------------ #
    axC = fig.add_subplot(gs[0, 2])

    axC.plot(df_v["time"], smooth(df_v["gamma"]),
             color=C_VPPTC, lw=2.2, label="VPP-TC")
    axC.plot(df_c["time"], smooth(df_c["gamma"]),
             color=C_CFC, lw=2.2, label="CFC")

    axC.axhline(2.5, color=C_DANG, lw=1.0, ls=":", alpha=0.75,
                label=r"$\Gamma$ threshold = 2.5")
    axC.axhline(0.0, color="k", lw=0.6, ls="-", alpha=0.4)

    # Shade where Gamma is below activation -> VPP-TC actually adds the constraint
    g_v = df_v["gamma"].to_numpy()
    t_v = df_v["time"].to_numpy()
    below = g_v < 2.5
    axC.fill_between(t_v, -2.5, 2.5, where=below,
                     color=C_DANG, alpha=0.10, step="mid")

    axC.set_xlabel("time [s]", fontsize=11)
    axC.set_ylabel(r"$\Gamma(t)$  (self-coll predictor)", fontsize=11)
    axC.set_title(r"C. $\Gamma$ predictor: VPP-TC stays safe, CFC dives",
                  fontsize=12, weight="bold", loc="left", pad=8)
    axC.set_xlim(0, max(df_v["time"].max(), df_c["time"].max()) * 1.02)
    axC.grid(True, alpha=0.25)
    axC.legend(loc="upper right", fontsize=9, frameon=True)
    g_lo = min(g_v.min(), df_c["gamma"].min()) - 0.5
    g_hi = max(g_v.max(), df_c["gamma"].max()) + 0.5
    axC.set_ylim(min(g_lo, -2.5), g_hi)

    # Task-completion summary box
    final_v = s_vpptc["final_target_dist"].to_numpy() * 1000.0  # mm
    final_c = s_cfc  ["final_target_dist"].to_numpy() * 1000.0
    reached_v = (final_v < 5.0).sum()
    reached_c = (final_c < 5.0).sum()
    axC.text(0.02, 0.06,
             f"reached target ($<$5 mm):\n"
             f"VPP-TC: {reached_v}/{n}   CFC: {reached_c}/{n}",
             transform=axC.transAxes, fontsize=9, va="bottom",
             family="monospace",
             bbox=dict(boxstyle="round,pad=0.35", fc="white",
                       ec=C_SAFE, lw=1.0, alpha=0.95))

    # ------------------------------------------------------------------ #
    fig.suptitle(
        "Aggressive scenario  -  target near base, gain $=$ 300, no obstacles, "
        "no reactive evasion: the QP alone keeps the arm safe",
        fontsize=13, weight="bold", y=0.965,
    )

    fig.savefig(args.out, dpi=300, bbox_inches="tight")
    print(f"[poster_fig2] saved -> {args.out}")
    print(f"[poster_fig2] VPP-TC collisions: {n_coll_v}/{n}   "
          f"CFC collisions: {n_coll_c}/{n}")
    print(f"[poster_fig2] VPP-TC reached target ({reached_v}/{n})   "
          f"CFC reached target ({reached_c}/{n})")


if __name__ == "__main__":
    main()
