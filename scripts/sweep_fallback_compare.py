#!/usr/bin/env python3
"""Compare VPP-TC with vs. without the gravity-comp/damping safety fallback.

For each (pct, seed, mode) we record:
  * self_collided  — whether the arm self-collided in the run
  * min_self_dist  — closest pair-of-links distance over the trajectory
  * min_gamma      — Γ-floor (negative = predicted self-collision)
  * max_q_violation - worst position-limit overshoot
  * max_qd_abs     — peak |q̇| (saturates at PyBullet's 100 rad/s ceiling)
  * crashed        — True if PyBullet died (numerical blow-up)

Mode:
  fallback   — current behaviour: QP failure → gravity-comp + K·q̇ damping
  no_fallback — QP failure → submit OSQP's last (likely garbage) solution,
                 or zero torque if u.value is None.  No safety net.

We use the proposal's obstacle scenario (target near base, gain=50,
duration=5s) so this is apples-to-apples with proposal_mismatch.csv.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import List

import pandas as pd

_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, os.pardir))
_OUTPUT_DIR  = os.path.join(_PROJECT_ROOT, "output")

PCTS  = [0.0, 5.0, 10.0, 15.0, 20.0]
SEEDS = [11, 22, 33]
MODES = ["fallback", "no_fallback"]
TARGET = [0.0, -0.6, 0.3]
GAIN = 50.0
DURATION = 5.0


def run_one(pct, seed, mode) -> dict:
    tag = f"fbk_{mode}_p{int(pct):02d}_s{seed:02d}"
    cmd = [
        sys.executable,
        os.path.join(_SCRIPT_DIR, "simulate.py"),
        "--no-gui",
        "--duration", str(DURATION),
        "--mass-perturb-pct", str(pct),
        "--mass-perturb-seed", str(seed),
        "--epsilon-margin", "0.0",
        "--planner-gain", str(GAIN),
        "--target-pos", *map(str, TARGET),
        "--tag", tag,
    ]
    if mode == "no_fallback":
        cmd.append("--no-fallback")

    last_err = None
    crashed = False
    for attempt in range(3):
        res = subprocess.run(cmd, cwd=_PROJECT_ROOT,
                             capture_output=True, text=True)
        if res.returncode == 0:
            break
        last_err = res.stderr[-1500:]
        if "torch_cuda.dll" in last_err or "WinError 193" in last_err:
            time.sleep(2.0 * (attempt + 1))
            continue
        # Numerical blow-up (PyBullet stack-overrun, etc.) — record & move on.
        if res.returncode in (3221226505, 3221225477, -1073740791):
            crashed = True
        break

    if crashed or res.returncode != 0:
        # Try to read whatever partial CSV exists
        csvs = [f for f in os.listdir(_OUTPUT_DIR)
                if f.startswith("run_") and f.endswith(f"_{tag}.csv")]
        if csvs:
            csv_path = max((os.path.join(_OUTPUT_DIR, f) for f in csvs),
                           key=os.path.getmtime)
            try:
                df = pd.read_csv(csv_path)
                return {
                    "pct": pct, "seed": seed, "mode": mode,
                    "crashed": True,
                    "self_collided": bool((df["self_collision_dist"] < 0).any()),
                    "min_self_dist": float(df["self_collision_dist"].min()),
                    "min_gamma":     float(df["gamma"].min()),
                    "max_q_violation":float(df["q_lim_violation"].max()),
                    "max_qd_abs":     float(df["qd_max_abs"].max()),
                    "soft_pct":       float(df["soft_fallback"].mean()) * 100.0,
                    "final_dist":     float(df["target_dist"].iloc[-1]),
                }
            except Exception:
                pass
        return {
            "pct": pct, "seed": seed, "mode": mode,
            "crashed": True,
            "self_collided": True,        # treat sim crash as a failure
            "min_self_dist": float("nan"),
            "min_gamma":     float("nan"),
            "max_q_violation": float("nan"),
            "max_qd_abs":     float("nan"),
            "soft_pct":       float("nan"),
            "final_dist":     float("nan"),
        }

    csvs = [f for f in os.listdir(_OUTPUT_DIR)
            if f.startswith("run_") and f.endswith(f"_{tag}.csv")]
    csv_path = max((os.path.join(_OUTPUT_DIR, f) for f in csvs),
                   key=os.path.getmtime)
    df = pd.read_csv(csv_path)
    return {
        "pct": pct, "seed": seed, "mode": mode,
        "crashed": False,
        "self_collided": bool((df["self_collision_dist"] < 0).any()),
        "min_self_dist": float(df["self_collision_dist"].min()),
        "min_gamma":     float(df["gamma"].min()),
        "max_q_violation":float(df["q_lim_violation"].max()),
        "max_qd_abs":     float(df["qd_max_abs"].max()),
        "soft_pct":       float(df["soft_fallback"].mean()) * 100.0,
        "final_dist":     float(df["target_dist"].iloc[-1]),
    }


def main():
    rows: List[dict] = []
    n_total = len(PCTS) * len(SEEDS) * len(MODES)
    n_done = 0
    for mode in MODES:
        for pct in PCTS:
            for seed in SEEDS:
                t0 = time.time()
                row = run_one(pct, seed, mode)
                dt = time.time() - t0
                n_done += 1
                marker = ""
                if row["crashed"]:        marker += " ***CRASH***"
                if row["self_collided"] and not row["crashed"]:
                    marker += " ***COLL***"
                print(f"[{n_done:2d}/{n_total}] mode={mode:11s} "
                      f"pct={pct:>4.1f}% seed={seed:>2d}  "
                      f"sc={row['min_self_dist']*100 if row['min_self_dist']==row['min_self_dist'] else float('nan'):6.2f}cm  "
                      f"\u0393={row['min_gamma']:7.2f}  "
                      f"qd_max={row['max_qd_abs']:6.2f}  "
                      f"final={row['final_dist']*1000:6.1f}mm"
                      f"{marker}  ({dt:.1f}s)")
                rows.append(row)

    df = pd.DataFrame(rows)
    out = os.path.join(_OUTPUT_DIR, "fallback_compare.csv")
    df.to_csv(out, index=False)
    print(f"\n[fbk] saved -> {out}")

    # Pivot: collisions per (mode, pct)
    print("\n=== Self-collisions (out of 3 seeds) per (mode, pct) ===")
    print(df.pivot_table(index="pct", columns="mode",
                         values="self_collided", aggfunc="sum").to_string())

    print("\n=== Mean min_self_dist (cm) per (mode, pct) ===")
    print((df.pivot_table(index="pct", columns="mode",
                          values="min_self_dist", aggfunc="mean")
             * 100).round(2).to_string())

    print("\n=== Mean min_gamma per (mode, pct) ===")
    print(df.pivot_table(index="pct", columns="mode",
                         values="min_gamma", aggfunc="mean").round(2).to_string())

    print("\n=== Crash count per (mode, pct) ===")
    print(df.pivot_table(index="pct", columns="mode",
                         values="crashed", aggfunc="sum").to_string())


if __name__ == "__main__":
    main()
