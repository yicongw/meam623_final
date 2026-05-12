#!/usr/bin/env python3
"""Cross-scenario robustness check for the fallback-vs-no-fallback trade-off.

Question: is the counter-intuitive finding from sweep_fallback_compare —
  * with-fallback   → higher q-limit overshoot, NO self-collisions
  * no-fallback     → lower  q-limit overshoot, MORE self-collisions
— a general phenomenon, or specific to the obstacle scenario?

We sweep:
  4 scenarios × 3 perturbation levels × 3 seeds × 2 modes = 72 cells

Scenarios cover different geometric/inertial regimes:
  obs        — proposal default (target near base, low gain, with obstacles)
  low_reach  — long forward stretch, high gain, no obstacles  (qd-saturating)
  reach_far  — far x-axis reach, high gain, no obstacles      (joint-limit prone)
  snake      — low-z workspace, mid gain, no obstacles         (self-collision prone)

Perturbation: 15 / 20 / 25 % link-mass perturbation (where the differences live).
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

# (label, target, gain, no_obstacles)
SCENARIOS = [
    ("obs",       [0.00, -0.60, 0.30],  50, False),
    ("low_reach", [0.45, -0.20, 0.10], 400, True),
    ("reach_far", [0.55,  0.00, 0.40], 400, True),
    ("snake",     [0.30,  0.20, 0.15], 500, True),
]
PCTS  = [15.0, 20.0, 25.0]
SEEDS = [11, 22, 33]
MODES = ["fallback", "no_fallback"]
DURATION = 5.0
CRASH_RCS = (3221226505, 3221225477, -1073740791,
             0xC0000005, 0xC0000409 & 0xffffffff)


def run_one(label, target, gain, no_obs, pct, seed, mode):
    tag = f"rob_{label}_{mode}_p{int(pct):02d}_s{seed:02d}"
    cmd = [
        sys.executable,
        os.path.join(_SCRIPT_DIR, "simulate.py"),
        "--no-gui",
        "--no-reactive",
        "--duration", str(DURATION),
        "--planner-gain", str(gain),
        "--mass-perturb-pct", str(pct),
        "--mass-perturb-seed", str(seed),
        "--epsilon-margin", "0.0",
        "--target-pos", *map(str, target),
        "--tag", tag,
    ]
    if no_obs:
        cmd.append("--no-obstacles")
    if mode == "no_fallback":
        cmd.append("--no-fallback")

    crashed = False
    last_err = None
    for attempt in range(3):
        res = subprocess.run(cmd, cwd=_PROJECT_ROOT,
                             capture_output=True, text=True)
        if res.returncode == 0:
            break
        last_err = res.stderr[-1500:]
        if "torch_cuda.dll" in last_err or "WinError 193" in last_err:
            time.sleep(2.0 * (attempt + 1))
            continue
        if res.returncode in CRASH_RCS:
            crashed = True
        break

    csvs = [f for f in os.listdir(_OUTPUT_DIR)
            if f.startswith("run_") and f.endswith(f"_{tag}.csv")]
    if not csvs:
        return {
            "label": label, "pct": pct, "seed": seed, "mode": mode,
            "crashed": True, "self_collided": True,
            "min_self_dist": float("nan"), "min_gamma": float("nan"),
            "max_q_violation": float("nan"), "max_qd_abs": float("nan"),
            "soft_pct": float("nan"), "final_dist": float("nan"),
        }
    csv_path = max((os.path.join(_OUTPUT_DIR, f) for f in csvs),
                   key=os.path.getmtime)
    df = pd.read_csv(csv_path)
    return {
        "label": label, "pct": pct, "seed": seed, "mode": mode,
        "crashed": crashed,
        "self_collided": bool((df["self_collision_dist"] < 0).any()),
        "min_self_dist":   float(df["self_collision_dist"].min()),
        "min_gamma":       float(df["gamma"].min()),
        "max_q_violation": float(df["q_lim_violation"].max()),
        "max_qd_abs":      float(df["qd_max_abs"].max()),
        "soft_pct":        float(df["soft_fallback"].mean()) * 100.0,
        "final_dist":      float(df["target_dist"].iloc[-1]),
    }


def main():
    rows: List[dict] = []
    n_total = len(SCENARIOS) * len(PCTS) * len(SEEDS) * len(MODES)
    n_done = 0
    for label, target, gain, no_obs in SCENARIOS:
        for pct in PCTS:
            for seed in SEEDS:
                for mode in MODES:
                    t0 = time.time()
                    row = run_one(label, target, gain, no_obs, pct, seed, mode)
                    dt = time.time() - t0
                    n_done += 1
                    marker = ""
                    if row["crashed"]:        marker += " ***CRASH***"
                    if row["self_collided"] and not row["crashed"]:
                        marker += " ***COLL***"
                    sc = row["min_self_dist"]
                    sc_s = f"{sc*100:6.2f}cm" if sc == sc else "  nan"
                    print(f"[{n_done:2d}/{n_total}] {label:10s} "
                          f"{mode:11s} pct={pct:>4.1f}% s={seed:>2d}  "
                          f"sc={sc_s}  Γ={row['min_gamma']:7.2f}  "
                          f"q_over={row['max_q_violation']*1000:6.2f}mm  "
                          f"qd_max={row['max_qd_abs']:6.2f}"
                          f"{marker}  ({dt:.1f}s)")
                    rows.append(row)

    df = pd.DataFrame(rows)
    out = os.path.join(_OUTPUT_DIR, "fallback_robustness.csv")
    df.to_csv(out, index=False)
    print(f"\n[rob] saved -> {out}")

    # ---- Summaries ----
    print("\n=== Per-scenario collision counts (mode × pct, /3 seeds) ===")
    for label, *_ in SCENARIOS:
        sub = df[df["label"] == label]
        piv = sub.pivot_table(index="pct", columns="mode",
                              values="self_collided", aggfunc="sum")
        print(f"\n[{label}]")
        print(piv.to_string())

    print("\n=== Mean q-limit overshoot (mm) by mode (across all cells) ===")
    print(df.pivot_table(index="pct", columns="mode",
                         values="max_q_violation", aggfunc="mean") * 1000)

    # The reverse-trade-off check: per-(scenario, pct, seed) does
    # fallback have HIGHER q_over but LOWER collision risk?
    print("\n=== Per-cell q_over diff (fallback − no_fallback) ===")
    print("(positive = fallback q_over higher; bigger = stronger reversal)")
    for label, *_ in SCENARIOS:
        sub = df[df["label"] == label]
        for pct in PCTS:
            f = sub[(sub["mode"]=="fallback")    & (sub["pct"]==pct)]\
                  .set_index("seed")["max_q_violation"]
            n = sub[(sub["mode"]=="no_fallback") & (sub["pct"]==pct)]\
                  .set_index("seed")["max_q_violation"]
            diff = (f - n) * 1000  # mm
            print(f"  {label:10s} pct={pct:>4.1f}%  diffs (mm) = "
                  f"{diff.values.round(2).tolist()}  mean={diff.mean():+.2f}")


if __name__ == "__main__":
    main()
