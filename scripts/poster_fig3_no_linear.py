#!/usr/bin/env python3
"""Generate the 3-panel Section 3 figure WITHOUT the linear-DS comparison.

Same layout / styling as scripts/poster_fig3.py, but every plot/legend
entry that referred to the linear-DS baseline is dropped.  Only the
hand-drawn LPV-DS run is shown.

Outputs: output/fig_poster_col3_lpvds_only.png
"""

from __future__ import annotations

import argparse
import os
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, os.pardir))
sys.path.insert(0, _PROJECT_ROOT)

from vpptc.planners import LPVDS

# Poster colour palette
C_LPVDS = "#C0392B"      # warm red — LPV-DS executed trajectory
C_DEMO  = "#F2B701"      # gold — drawn demos
C_OBST  = "#2C2C2C"      # near black — obstacle
C_ATT   = "#27AE60"      # green — attractor
C_FIELD = "#5A6B82"      # muted slate — vector field
C_BG    = "white"

_PLANE_AXES = {"xy": (0, 1, 2), "xz": (0, 2, 1), "yz": (1, 2, 0)}


def _smooth(a, w=25):
    if a.shape[0] < w:
        return a
    kern = np.ones(w) / w
    out = np.empty_like(a)
    for d in range(a.shape[1]):
        out[:, d] = np.convolve(a[:, d], kern, mode="same")
    out[:w//2] = a[:w//2]; out[-w//2:] = a[-w//2:]
    return out


def get_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lpvds-csv", default=os.path.join(
        _PROJECT_ROOT, "output", "run_1777847411_lpvds_v2.csv"))
    ap.add_argument("--demo-npz", default=os.path.join(
        _PROJECT_ROOT, "assets", "ds_models", "my_demo.npz"))
    ap.add_argument("--target-pos", type=float, nargs=3,
                    default=[0.0, -0.6, 0.3])
    # The simulator spawns TWO obstacles (see scripts/simulate.py:252-262):
    #   obstacle_1 (moving): centre = obstacle_pos, with z oscillating ±0.1m
    #   obstacle_2 (static): centre = obstacle_pos + [+0.5, +0.1, 0]
    ap.add_argument("--obstacle-pos", type=float, nargs=3,
                    default=[0.0, -0.4, 0.5],
                    help="Nominal centre of obstacle_1 (moving).")
    ap.add_argument("--obstacle-radius", type=float, default=0.05)
    ap.add_argument("--moving-amp", type=float, default=0.10,
                    help="Amplitude of obstacle_1's sinusoidal z motion (m).")
    ap.add_argument("--out", default=os.path.join(
        _PROJECT_ROOT, "output", "fig_poster_col3_lpvds_only.png"))
    return ap.parse_args()


def main():
    args = get_args()
    df = pd.read_csv(args.lpvds_csv)
    demo = dict(np.load(args.demo_npz, allow_pickle=False))

    target = np.array(args.target_pos)
    obs    = np.array(args.obstacle_pos)              # obstacle_1 (moving)
    obs2   = obs + np.array([0.5, 0.1, 0.0])          # obstacle_2 (static)
    rad    = args.obstacle_radius
    amp_z  = args.moving_amp                          # ±z oscillation

    plane = (str(demo["plane"]) if demo["plane"].dtype.kind == "U"
             else demo["plane"].item().decode())
    i1, i2, _ = _PLANE_AXES[plane]
    R = np.asarray(demo["R"])
    att2d = np.asarray(demo["attractor"]).reshape(-1)
    origin = target - R[:, :2] @ att2d

    lpvds = LPVDS(Priors=demo["Priors"], Mu=demo["Mu"], Sigma=demo["Sigma"],
                  A=demo["A"], b=demo["b"], attractor=att2d)

    ee = _smooth(df[["end_x", "end_y", "end_z"]].to_numpy())
    proj = (R.T @ (ee - origin).T).T[:, :2]
    target_2d = (R.T @ (target - origin))[:2]

    obs_local   = R.T @ (obs  - origin)
    obs2_local  = R.T @ (obs2 - origin)
    perp        = obs_local[2]
    perp2       = obs2_local[2]
    in_plane_r  = np.sqrt(max(0.0, rad ** 2 - perp  ** 2))
    in_plane_r2 = np.sqrt(max(0.0, rad ** 2 - perp2 ** 2))
    obs_2d      = obs_local[:2]
    obs2_2d     = obs2_local[:2]

    DX = np.asarray(demo["demos_X"])

    # ----------------------------------------------------------------
    # POSTER LAYOUT: 2-panel side-by-side.
    #   A. Workspace trajectory (with both obstacles, moving one labelled)
    #   B. Hand-drawn LPV-DS field (streamplot)
    # figsize aspect 10/5 = 2.0 matches the Col3Fig box (W=9.62, H=4.81).
    fig = plt.figure(figsize=(10, 5.0), facecolor=C_BG)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.05, 0.95],
                          wspace=0.28,
                          left=0.075, right=0.97, top=0.85, bottom=0.14)

    # ===== Panel A: workspace trajectory of LPV-DS only =====
    axA = fig.add_subplot(gs[0, 0])
    axA.set_facecolor(C_BG)
    axA.plot(ee[:, i1], ee[:, i2], "-", color=C_LPVDS, lw=2.6,
             label="Hand-drawn LPV-DS  (executed EE)", zorder=4)

    # demos
    demos_3d = (origin[:, None] + R[:, :2] @ DX).T
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

    # ----- obstacles -----
    th = np.linspace(0, 2 * np.pi, 60)

    # Moving obstacle: oscillates ±amp_z along the world z-axis.  Project
    # that motion into the (i1, i2) plane: only the i2 axis sees motion if
    # i2 corresponds to z, otherwise no in-plane swing is visible.
    z_axis_in_plane = (i2 == 2)              # True for yz/xz planes
    if z_axis_in_plane:
        # Translucent envelope showing the swept region
        from matplotlib.patches import Rectangle
        axA.add_patch(Rectangle(
            (obs[i1] - rad, obs[i2] - amp_z - rad),
            2 * rad, 2 * (amp_z + rad),
            facecolor=C_OBST, alpha=0.18, edgecolor="none", zorder=2,
        ))
        # Up-down arrow inside the envelope (white, high contrast)
        axA.annotate("", xy=(obs[i1], obs[i2] + amp_z),
                     xytext=(obs[i1], obs[i2] - amp_z),
                     arrowprops=dict(arrowstyle="<->", color="white",
                                     lw=1.6, shrinkA=0, shrinkB=0),
                     zorder=5)
    # Disk at the snapshot (mean) position
    axA.fill(obs[i1] + rad * np.cos(th), obs[i2] + rad * np.sin(th),
             color=C_OBST, alpha=0.92, edgecolor="none", zorder=4,
             label="Moving obstacle  ($\\pm$10 cm in $z$)")

    # Static obstacle (offset by [+0.5 x, +0.1 y] from the moving one)
    axA.fill(obs2[i1] + rad * np.cos(th), obs2[i2] + rad * np.sin(th),
             color="#7A7A7A", alpha=0.92, edgecolor="none", zorder=4,
             label="Static obstacle")

    axA.plot(target[i1], target[i2], "*", color=C_ATT, ms=22, mec="black",
             mew=0.6, label="Attractor", zorder=6)
    axA.plot(ee[0, i1], ee[0, i2], "o", color=C_LPVDS, ms=8,
             mec="white", mew=1.0, label="Start", zorder=6)

    axA.set_aspect("equal")
    axA.grid(True, alpha=0.25)
    axA.tick_params(axis="both", labelsize=12)
    axA.set_xlabel(f"{['x','y','z'][i1]} [m]", fontsize=14)
    axA.set_ylabel(f"{['x','y','z'][i2]} [m]", fontsize=14)
    axA.set_title("A.  Workspace trajectory", fontsize=16, fontweight="bold",
                  loc="left", pad=8)
    axA.legend(loc="best", fontsize=11, frameon=True, framealpha=0.9)

    # ===== Panel B: hand-drawn LPV-DS learned vector field =====
    axB = fig.add_subplot(gs[0, 1])
    axB.set_facecolor(C_BG)

    # Mesh covers demo support and the executed trajectory, with margin.
    xy_lo = np.minimum(DX.min(axis=1), proj.min(axis=0)) - 0.08
    xy_hi = np.maximum(DX.max(axis=1), proj.max(axis=0)) + 0.08
    xx = np.linspace(xy_lo[0], xy_hi[0], 40)
    yy = np.linspace(xy_lo[1], xy_hi[1], 40)
    XX, YY = np.meshgrid(xx, yy)
    UU = np.zeros_like(XX); VV = np.zeros_like(XX)
    for ii in range(XX.shape[0]):
        for jj in range(XX.shape[1]):
            v = lpvds(np.array([XX[ii, jj], YY[ii, jj]]))
            UU[ii, jj], VV[ii, jj] = float(v[0]), float(v[1])
    axB.streamplot(XX, YY, UU, VV, color=C_FIELD, density=1.3,
                   linewidth=1.0, arrowsize=1.0, arrowstyle="->")

    # Demo curves (multi-segment) in the 2D drawing plane.
    seg2 = [0]
    for kk in range(1, DX.shape[1]):
        if np.linalg.norm(DX[:, kk] - DX[:, kk-1]) > 0.05:
            seg2.append(kk)
    seg2.append(DX.shape[1])
    firstD = True
    for kk in range(len(seg2) - 1):
        s, e = seg2[kk], seg2[kk+1]
        if e - s > 3:
            axB.plot(DX[0, s:e], DX[1, s:e], "-",
                     color=C_DEMO, lw=2.2, alpha=0.9, zorder=3,
                     label="Drawn demos" if firstD else None)
            firstD = False

    # Executed end-effector trajectory, same 2D frame.
    axB.plot(proj[:, 0], proj[:, 1], "-", color=C_LPVDS, lw=2.4,
             zorder=4, label="Executed EE")

    # Both obstacles, projected into the drawing plane.
    axB.fill(obs_2d[0] + in_plane_r * np.cos(th),
             obs_2d[1] + in_plane_r * np.sin(th),
             color=C_OBST, alpha=0.92, edgecolor="none", zorder=5,
             label="Moving obstacle")
    axB.fill(obs2_2d[0] + in_plane_r2 * np.cos(th),
             obs2_2d[1] + in_plane_r2 * np.sin(th),
             color="#7A7A7A", alpha=0.92, edgecolor="none", zorder=5,
             label="Static obstacle")

    # Attractor (2D).
    axB.plot(target_2d[0], target_2d[1], "*", color=C_ATT, ms=20,
             mec="black", mew=0.6, zorder=6, label="Attractor")

    axB.set_aspect("equal")
    axB.set_xlim(xy_lo[0], xy_hi[0])
    axB.set_ylim(xy_lo[1], xy_hi[1])
    axB.grid(True, alpha=0.25)
    axB.tick_params(axis="both", labelsize=12)
    axB.set_xlabel("drawing $u$ [m]", fontsize=14)
    axB.set_ylabel("drawing $v$ [m]", fontsize=14)
    axB.set_title("B.  Hand-drawn LPV-DS field", fontsize=16,
                  fontweight="bold", loc="left", pad=8)
    axB.legend(loc="best", fontsize=10, frameon=True, framealpha=0.9)

    fig.suptitle(
        "DS-Agnostic Safety: any hand-drawn LPV-DS in the same QP + safety layer",
        fontsize=17, fontweight="bold", y=0.965,
    )

    fig.savefig(args.out, dpi=300, bbox_inches="tight", facecolor=C_BG)
    print(f"saved -> {args.out}")
    print(f"  duration={df.time.iloc[-1]:.2f}s  "
          f"min d_obs={df.real_dist.min():.4f} m  "
          f"final ||x-x*||={df.target_dist.iloc[-1]:.4f} m  "
          f"min Gamma={df.gamma.min():.2f}")


if __name__ == "__main__":
    main()
