#!/usr/bin/env python3
"""Generate the 3-panel figure for poster Section 3 (DS-Agnostic Safety).

Panel A: workspace top/side view -- linear vs LPV-DS executed EE trajectories,
         drawn demo, obstacle, attractor.
Panel B: 2D LPV-DS streamplot in the drawing plane, with executed EE projection.
Panel C: two stacked time series -- min obstacle distance d_obs(t) and
         storage function S(t) = T_kin + 50 * 1/2 ‖x − x*‖².

Usage
-----
    python scripts/poster_fig3.py \
        --linear-csv  output/run_*_linear.csv \
        --lpvds-csv   output/run_*_lpvds.csv \
        --demo-npz    assets/ds_models/my_demo.npz \
        --target-pos 0.0 -0.6 0.3 \
        --obstacle-pos 0.0 -0.4 0.5 --obstacle-radius 0.05 \
        --out poster_fig3.png
"""

from __future__ import annotations

import argparse
import os
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.join(_SCRIPT_DIR, os.pardir)
sys.path.insert(0, os.path.abspath(_PROJECT_ROOT))

from vpptc.planners import LPVDS


# Poster colour palette -- tuned to look distinct on a white background
C_LINEAR = "#1F4E79"      # dark blue
C_LPVDS  = "#C0392B"      # warm red
C_DEMO   = "#F2B701"      # gold
C_OBST   = "#2C2C2C"      # near black
C_ATT    = "#27AE60"      # green
C_BG     = "white"


_PLANE_AXES = {"xy": (0, 1, 2), "xz": (0, 2, 1), "yz": (1, 2, 0)}


def get_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--linear-csv", type=str, required=True)
    ap.add_argument("--lpvds-csv", type=str, required=True)
    ap.add_argument("--demo-npz", type=str, required=True)
    ap.add_argument("--target-pos", type=float, nargs=3, required=True)
    ap.add_argument("--obstacle-pos", type=float, nargs=3, required=True)
    ap.add_argument("--obstacle-radius", type=float, default=0.05)
    ap.add_argument("--out", type=str, default="poster_fig3.png")
    return ap.parse_args()


def main():
    args = get_args()
    df_lin = pd.read_csv(args.linear_csv)
    df_lpv = pd.read_csv(args.lpvds_csv)
    demo = dict(np.load(args.demo_npz, allow_pickle=False))

    target = np.array(args.target_pos)
    obs = np.array(args.obstacle_pos)
    rad = args.obstacle_radius

    plane = str(demo["plane"]) if demo["plane"].dtype.kind == "U" else demo["plane"].item().decode()
    i1, i2, _ = _PLANE_AXES[plane]
    R = np.asarray(demo["R"])
    # Re-derive the same origin shift used by simulate.py:
    att2d = np.asarray(demo["attractor"]).reshape(-1)
    origin = target - R[:, :2] @ att2d

    # Build LPV-DS handle
    lpvds = LPVDS(Priors=demo["Priors"], Mu=demo["Mu"], Sigma=demo["Sigma"],
                  A=demo["A"], b=demo["b"], attractor=att2d)

    # Project executed EE onto the drawing plane
    ee_lin = df_lin[["end_x", "end_y", "end_z"]].to_numpy()
    ee_lpv = df_lpv[["end_x", "end_y", "end_z"]].to_numpy()

    # Light smoothing for visual clarity (running mean over 50 ms = 25 steps @ 2ms)
    def _smooth(a, w=25):
        if a.shape[0] < w:
            return a
        kern = np.ones(w) / w
        out = np.empty_like(a)
        for d in range(a.shape[1]):
            out[:, d] = np.convolve(a[:, d], kern, mode="same")
        # fix edges (convolution dampens near boundaries)
        out[:w//2] = a[:w//2]; out[-w//2:] = a[-w//2:]
        return out
    ee_lin = _smooth(ee_lin)
    ee_lpv = _smooth(ee_lpv)
    proj_lin = (R.T @ (ee_lin - origin).T).T[:, :2]
    proj_lpv = (R.T @ (ee_lpv - origin).T).T[:, :2]
    target_2d = (R.T @ (target - origin))[:2]

    # Obstacle in the drawing-plane coordinates: project + show as circle of
    # radius sqrt(radius^2 - perp_offset^2) (intersection of sphere with plane)
    obs_local = R.T @ (obs - origin)
    perp = obs_local[2]
    in_plane_r = np.sqrt(max(0.0, rad ** 2 - perp ** 2))
    obs_2d = obs_local[:2]

    # ----------------------------------------------------------------
    # Figure
    # ----------------------------------------------------------------
    fig = plt.figure(figsize=(15, 6.0), facecolor=C_BG)
    gs = fig.add_gridspec(2, 3, width_ratios=[1.0, 1.05, 0.95],
                          height_ratios=[1, 1], hspace=0.50, wspace=0.32,
                          left=0.05, right=0.985, top=0.86, bottom=0.11)

    # ===== Panel A: 3D-ish workspace, sagittal view =====
    axA = fig.add_subplot(gs[:, 0])
    # use indices i1, i2 for the plane projection (top-down or side based on plane)
    # In robot frame: x forward, y left, z up. plane='xz' --> view sagittal
    axA.set_facecolor(C_BG)
    axA.plot(ee_lin[:, i1], ee_lin[:, i2], "-", color=C_LINEAR, lw=2.4,
             label="Linear DS (baseline)", zorder=4)
    axA.plot(ee_lpv[:, i1], ee_lpv[:, i2], "-", color=C_LPVDS, lw=2.4,
             label="Hand-drawn LPV-DS", zorder=3)
    # demo
    DX = np.asarray(demo["demos_X"])
    demos_3d = (origin[:, None] + R[:, :2] @ DX).T
    # Split into segments where consecutive points are far apart (different demos)
    seg_starts = [0]
    for kk in range(1, demos_3d.shape[0]):
        if np.linalg.norm(demos_3d[kk] - demos_3d[kk-1]) > 0.05:
            seg_starts.append(kk)
    seg_starts.append(demos_3d.shape[0])
    first = True
    for kk in range(len(seg_starts) - 1):
        s, e = seg_starts[kk], seg_starts[kk+1]
        if e - s > 3:
            axA.plot(demos_3d[s:e, i1], demos_3d[s:e, i2], "-",
                     color=C_DEMO, lw=2.6, alpha=0.85, zorder=2,
                     label="Drawn demos" if first else None)
            first = False
    # obstacle (sphere -> circle of full radius in this projection plane)
    th = np.linspace(0, 2 * np.pi, 60)
    axA.fill(obs[i1] + rad * np.cos(th), obs[i2] + rad * np.sin(th),
             color=C_OBST, alpha=0.85, edgecolor="none")
    axA.plot(obs[i1], obs[i2], "x", color="white", ms=8, mew=2)
    # target
    axA.plot(target[i1], target[i2], "*", color=C_ATT, ms=22, mec="black",
             mew=0.6, label="Attractor")
    # start markers
    axA.plot(ee_lin[0, i1], ee_lin[0, i2], "o", color=C_LINEAR, ms=8,
             mec="white", mew=1.0)
    axA.plot(ee_lpv[0, i1], ee_lpv[0, i2], "o", color=C_LPVDS, ms=8,
             mec="white", mew=1.0)
    axA.set_aspect("equal")
    axA.grid(True, alpha=0.25)
    axA.set_xlabel(f"{['x','y','z'][i1]} [m]", fontsize=11)
    axA.set_ylabel(f"{['x','y','z'][i2]} [m]", fontsize=11)
    axA.set_title("A.  Workspace trajectories", fontsize=13, fontweight="bold",
                  loc="left", pad=8)
    axA.legend(loc="best", fontsize=8.5, frameon=True, framealpha=0.9)

    # ===== Panel B: 2D LPV-DS streamplot with executed traj =====
    axB = fig.add_subplot(gs[:, 1])
    # Bounds from demo + executed
    all_x = np.concatenate([proj_lpv[:, 0], DX[0]])
    all_y = np.concatenate([proj_lpv[:, 1], DX[1]])
    pad = 0.08
    xlim = (all_x.min() - pad, all_x.max() + pad)
    ylim = (all_y.min() - pad, all_y.max() + pad)
    xs = np.linspace(*xlim, 30)
    ys = np.linspace(*ylim, 30)
    XX, YY = np.meshgrid(xs, ys)
    UU = np.zeros_like(XX); VV = np.zeros_like(YY)
    for ii in range(XX.shape[0]):
        for jj in range(XX.shape[1]):
            v = lpvds(np.array([XX[ii, jj], YY[ii, jj]]))
            UU[ii, jj], VV[ii, jj] = v
    speed = np.hypot(UU, VV)
    axB.streamplot(XX, YY, UU, VV, density=0.9, color="0.55",
                   linewidth=0.7, arrowsize=0.8)
    # demos as connected segments (on top of streamplot, thick & opaque)
    seg_starts = [0]
    for kk in range(1, DX.shape[1]):
        if np.linalg.norm(DX[:, kk] - DX[:, kk-1]) > 0.05:
            seg_starts.append(kk)
    seg_starts.append(DX.shape[1])
    first = True
    for kk in range(len(seg_starts) - 1):
        s, e = seg_starts[kk], seg_starts[kk+1]
        if e - s > 3:
            axB.plot(DX[0, s:e], DX[1, s:e], "-", color=C_DEMO, lw=3.2,
                     alpha=0.95, zorder=5,
                     label="Drawn demos" if first else None)
            first = False
    axB.plot(proj_lpv[:, 0], proj_lpv[:, 1], "-", color=C_LPVDS, lw=2.2,
             label="LPV-DS executed (proj.)")
    axB.plot(target_2d[0], target_2d[1], "*", color=C_ATT, ms=22, mec="black",
             mew=0.6, label="Attractor")
    if in_plane_r > 0:
        axB.fill(obs_2d[0] + in_plane_r * np.cos(th),
                 obs_2d[1] + in_plane_r * np.sin(th),
                 color=C_OBST, alpha=0.85, edgecolor="none", label="Obstacle")
    axB.set_xlim(xlim); axB.set_ylim(ylim); axB.set_aspect("equal")
    axB.grid(True, alpha=0.25)
    axB.set_xlabel(f"{plane[0]} (drawing plane) [m]", fontsize=11)
    axB.set_ylabel(f"{plane[1]} (drawing plane) [m]", fontsize=11)
    axB.set_title("B.  Hand-drawn LPV-DS field", fontsize=13, fontweight="bold",
                  loc="left", pad=8)
    axB.legend(loc="best", fontsize=8.5, frameon=True, framealpha=0.9)

    # ===== Panel C: stacked time series =====
    axC1 = fig.add_subplot(gs[0, 2])
    axC1.plot(df_lin["time"], df_lin["real_dist"], "-", color=C_LINEAR, lw=2,
              label="Linear")
    axC1.plot(df_lpv["time"], df_lpv["real_dist"], "-", color=C_LPVDS, lw=2,
              label="LPV-DS")
    axC1.axhline(0.0, color="black", lw=0.6, ls=":")
    axC1.set_ylabel("min $d_\\mathrm{obs}$ [m]", fontsize=10)
    axC1.set_title("C.  Safety + passivity over time", fontsize=13,
                   fontweight="bold", loc="left", pad=8)
    axC1.grid(True, alpha=0.25); axC1.legend(fontsize=8, loc="best")
    axC1.set_xticklabels([])

    axC2 = fig.add_subplot(gs[1, 2])
    axC2.plot(df_lin["time"], df_lin["storage"], "-", color=C_LINEAR, lw=2,
              label="Linear")
    axC2.plot(df_lpv["time"], df_lpv["storage"], "-", color=C_LPVDS, lw=2,
              label="LPV-DS")
    axC2.set_ylabel("storage $S(t)$", fontsize=10)
    axC2.set_xlabel("time [s]", fontsize=10)
    axC2.grid(True, alpha=0.25); axC2.legend(fontsize=8, loc="best")

    fig.suptitle(
        "DS-Agnostic Safety:  same QP & safety layer, hand-drawn LPV-DS replaces linear attractor",
        fontsize=14, fontweight="bold", y=0.965,
    )

    fig.savefig(args.out, dpi=300, bbox_inches="tight", facecolor=C_BG)
    print(f"saved -> {args.out}")

    # Also dump key numbers
    print("\n--- Quantitative summary (poster caption material) ---")
    for tag, df in [("linear", df_lin), ("lpvds", df_lpv)]:
        print(f"  [{tag}]  duration={df.time.iloc[-1]:.2f}s  "
              f"min d_obs={df.real_dist.min():.4f} m  "
              f"final ‖x−x*‖={df.target_dist.iloc[-1]:.4f} m  "
              f"max S={df.storage.max():.2f}  final S={df.storage.iloc[-1]:.2f}  "
              f"min Γ={df.gamma.min():.2f}")


if __name__ == "__main__":
    main()
