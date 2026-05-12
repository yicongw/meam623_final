#!/usr/bin/env python3
"""Poster figure for Col2: time-series of min self-collision distance.

Single representative cell:  obs_react,  pct = 20 %,  seed = 33.
- With fallback:    arm stays away from self-collision throughout 3 s.
- No fallback:      QP infeasibility -> momentum carries the arm into a
                    self-collision around t ~ 1.4 s, simulation aborts.

This is the most narrative figure for the poster: one X-axis (time),
one Y-axis (sc distance), zero-crossing = self-collision moment.

Output: output/fig_poster_col2_timeseries.png
"""

from __future__ import annotations

import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_OUT  = os.path.abspath(os.path.join(_HERE, os.pardir, "output"))

CSV_FBK = os.path.join(_OUT, "run_1777871035_hu_obs_react_fallback_p20_s33.csv")
CSV_NFB = os.path.join(_OUT, "run_1777870990_hu_obs_react_no_fallback_p20_s11.csv")
# choose the colliding NFB:
import glob
nfb_candidates = glob.glob(os.path.join(_OUT, "*hu_obs_react_no_fallback_p20_s33.csv"))
if nfb_candidates:
    CSV_NFB = nfb_candidates[0]

OUT_PNG = os.path.join(_OUT, "fig_poster_col2_timeseries.png")

# Poster colors (consistent w/ the existing poster's Col2)
NAVY  = "#011F5B"
RED   = "#C62828"
GRAY  = "#999999"
DARK  = "#333333"

plt.rcParams.update({
    "font.family":      "Arial",
    "axes.titleweight": "bold",
    "axes.titlesize":   18,
    "axes.labelsize":   16,
    "legend.fontsize":  14,
    "xtick.labelsize":  13,
    "ytick.labelsize":  13,
})


def main():
    df_fbk = pd.read_csv(CSV_FBK)
    df_nfb = pd.read_csv(CSV_NFB)

    t_fbk = df_fbk["time"].values
    sc_fbk = df_fbk["self_collision_dist"].values * 100  # m -> cm
    t_nfb = df_nfb["time"].values
    sc_nfb = df_nfb["self_collision_dist"].values * 100

    # Find collision moment in NFB
    coll_mask = sc_nfb < 0
    t_coll = t_nfb[np.argmax(coll_mask)] if coll_mask.any() else None

    fig, ax = plt.subplots(figsize=(8.5, 5.0))

    # ---- danger zone ----
    ax.axhspan(-3, 0, color="#FFE0E0", alpha=0.7, zorder=0)
    ax.text(0.05, -1.4, "self-collision zone",
            fontsize=12, color="#A00", style="italic", zorder=1)

    # ---- with-fallback line ----
    ax.plot(t_fbk, sc_fbk, color=NAVY, linewidth=3.0,
            label="With fallback  (default VPP-TC)", zorder=4)

    # ---- no-fallback line, with marker at collision ----
    ax.plot(t_nfb, sc_nfb, color=RED, linewidth=3.0,
            label="No fallback  (ablation)", zorder=4)

    # ---- collision annotation ----
    if t_coll is not None:
        ax.scatter([t_coll], [0], s=180, marker="X", color=RED,
                   edgecolor="black", linewidth=1.4, zorder=6)
        ax.annotate(f"self-collision\nat t = {t_coll:.2f} s",
                    xy=(t_coll, 0), xytext=(t_coll + 0.30, 2.8),
                    fontsize=14, color=RED, fontweight="bold",
                    arrowprops=dict(arrowstyle="->", color=RED, lw=1.4),
                    zorder=7)
        # Vertical guide line where NFB sim aborts
        ax.axvline(t_coll, color=RED, linestyle=":", alpha=0.5, zorder=2)

    # ---- styling ----
    ax.set_xlabel("Time  [s]")
    ax.set_ylabel("Min self-collision distance  [cm]")
    ax.set_title("Same disturbance, two controllers — only the fallback survives\n"
                 "(20 % link-mass perturbation, reactive evasion ON, seed = 33)",
                 pad=12, fontsize=15)
    ax.set_xlim(0, max(t_fbk.max(), t_nfb.max()) * 1.02)
    ax.set_ylim(-2.5, max(sc_fbk.max(), sc_nfb.max()) * 1.10)
    ax.axhline(0, color="black", linewidth=1.0, zorder=2)
    ax.grid(linestyle=":", alpha=0.5)
    ax.legend(loc="upper right", frameon=True, framealpha=0.95)

    # Tight, no white border
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=200, bbox_inches="tight",
                facecolor="white")
    print(f"saved -> {OUT_PNG}")
    print(f"  fbk: t=[{t_fbk[0]:.2f}, {t_fbk[-1]:.2f}]s, min={sc_fbk.min():.2f}cm")
    print(f"  nfb: t=[{t_nfb[0]:.2f}, {t_nfb[-1]:.2f}]s, min={sc_nfb.min():.3f}cm "
          f"(collision at t={t_coll:.3f}s)")


if __name__ == "__main__":
    main()
