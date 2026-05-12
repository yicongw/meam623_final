#!/usr/bin/env python3
"""Plot a simulation run vs the LPV-DS demos that produced its planner.

Usage
-----
    python scripts/plot_run.py output/run_1714605000.csv \
        --demo assets/ds_models/drawn_demo.npz

If --demo is omitted, only the executed end-effector trajectory is shown.
"""

from __future__ import annotations

import argparse
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


_PLANE_AXES = {"xy": (0, 1, 2), "xz": (0, 2, 1), "yz": (1, 2, 0)}


def get_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", type=str, help="run_*.csv produced by simulate.py")
    ap.add_argument("--demo", type=str, default=None,
                    help=".npz saved by draw_lpvds.py")
    ap.add_argument("--out", type=str, default=None,
                    help="Output figure path; if omitted shows interactively")
    return ap.parse_args()


def main():
    args = get_args()
    df = pd.read_csv(args.csv)
    end = df[["end_x", "end_y", "end_z"]].to_numpy()  # (T, 3)

    fig = plt.figure(figsize=(14, 5))

    # ---------- 3D EE trajectory ----------
    ax3d = fig.add_subplot(1, 3, 1, projection="3d")
    ax3d.plot(end[:, 0], end[:, 1], end[:, 2], "C0-", lw=2, label="executed EE")
    ax3d.scatter(*end[0], color="C0", s=60, marker="o", label="start")
    ax3d.scatter(*end[-1], color="C3", s=80, marker="s", label="final")
    ax3d.set_xlabel("x [m]"); ax3d.set_ylabel("y [m]"); ax3d.set_zlabel("z [m]")
    ax3d.set_title("End-effector trajectory (3D)")
    ax3d.legend(loc="upper left", fontsize=8)

    # ---------- 2D in the demo plane ----------
    ax2d = fig.add_subplot(1, 3, 2)
    if args.demo is not None and os.path.isfile(args.demo):
        d = dict(np.load(args.demo, allow_pickle=False))
        plane = str(d["plane"]) if d["plane"].dtype.kind == "U" else d["plane"].item().decode()
        i1, i2, _ = _PLANE_AXES[plane]
        # demo points
        DX = d["demos_X"]                          # (2, N)
        ax2d.plot(DX[0], DX[1], ".", color="0.6", ms=2, label="demo points")
        att2d = np.asarray(d["attractor"]).reshape(-1)
        ax2d.plot(att2d[0], att2d[1], "*", color="red", ms=18, label="DS attractor")
        # executed projected onto the demo plane via R^T (end - origin)
        R = np.asarray(d["R"])
        origin = np.asarray(d["origin"])
        local = (R.T @ (end - origin).T).T          # (T, 3)
        ax2d.plot(local[:, 0], local[:, 1], "C0-", lw=2, label="executed (in plane)")
        ax2d.plot(local[0, 0], local[0, 1], "C0o", ms=8)
        ax2d.set_xlabel(f"{plane[0]} (robot frame) [m]")
        ax2d.set_ylabel(f"{plane[1]} (robot frame) [m]")
        ax2d.set_title(f"Plane '{plane}' view")
    else:
        # fallback: top-down xy
        ax2d.plot(end[:, 0], end[:, 1], "C0-", lw=2)
        ax2d.plot(end[0, 0], end[0, 1], "C0o", ms=8)
        ax2d.set_xlabel("x [m]"); ax2d.set_ylabel("y [m]")
        ax2d.set_title("Top-down xy view")
    ax2d.set_aspect("equal"); ax2d.grid(True, alpha=0.3)
    ax2d.legend(loc="best", fontsize=8)

    # ---------- safety scalars over time ----------
    ax_s = fig.add_subplot(1, 3, 3)
    t = df["time"].to_numpy()
    ax_s.plot(t, df["gamma"], label="Gamma (self-coll)", color="C2")
    ax_s.plot(t, df["real_dist"], label="real obs dist [m]", color="C1")
    ax_s.plot(t, df["target_dist"], label="dist to target [m]", color="C3")
    ax_s.set_xlabel("time [s]"); ax_s.legend(fontsize=8); ax_s.grid(True, alpha=0.3)
    ax_s.set_title("Safety signals over time")

    plt.tight_layout()
    if args.out:
        plt.savefig(args.out, dpi=150)
        print(f"saved to {args.out}")
    else:
        plt.show()


if __name__ == "__main__":
    main()
