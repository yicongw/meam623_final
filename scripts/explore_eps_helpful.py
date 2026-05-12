#!/usr/bin/env python3
"""Exploration: find a scenario where ε-margin actually helps.

Design: pick aggressive setpoints + high planner gain so that the QP's
q̈ command saturates the viability bound. Then add mass perturbation:
the controller commands q̈_cmd along the bound, but real q̈ deviates and
overshoots → joint-limit violation. ε-margin should pull the command
back into a safer region and prevent the overshoot.

Success criterion (per (scenario, pct)):
    eps=0     → q_over > 1mm   OR   self_collided
    eps=0.10  → q_over ≈ 0     AND   not self_collided

We sweep one seed for speed (this is exploration, not a final result).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

import pandas as pd

_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, os.pardir))
_OUTPUT_DIR  = os.path.join(_PROJECT_ROOT, "output")

# (label, target, gain, no_obstacles)
SCENARIOS = [
    ("far_x",       [ 0.55,  0.00, 0.40], 400, True),
    ("cross_y",     [ 0.10,  0.50, 0.40], 400, True),
    ("low_reach",   [ 0.45, -0.20, 0.10], 400, True),
    ("high_gain",   [ 0.30, -0.30, 0.35], 600, True),
    ("snake",       [ 0.30,  0.20, 0.15], 500, True),
    ("twist_high",  [ 0.20, -0.25, 0.30], 600, True),
]
PCTS    = [0.0, 5.0, 10.0]
EPSILONS = [0.0, 0.10]
SEED    = 11
DURATION = 4.0


def run_one(label, target, gain, no_obstacles, pct, eps):
    eps_tag = f"e{int(eps*100):02d}"
    tag = f"exp_{label}_p{int(pct):02d}_{eps_tag}".replace(".", "p")
    cmd = [
        sys.executable,
        os.path.join(_SCRIPT_DIR, "simulate.py"),
        "--no-gui",
        "--no-reactive",
        "--duration", str(DURATION),
        "--planner-gain", str(gain),
        "--mass-perturb-pct", str(pct),
        "--mass-perturb-seed", str(SEED),
        "--epsilon-margin", str(eps),
        "--target-pos", *map(str, target),
        "--tag", tag,
    ]
    if no_obstacles:
        cmd.append("--no-obstacles")
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
        break
    if res.returncode != 0:
        print(f"\n!!! FAILED rc={res.returncode}  tag={tag}")
        print("STDERR[-1500:]\n" + (last_err or ""))
        raise RuntimeError(tag)

    csvs = [f for f in os.listdir(_OUTPUT_DIR)
            if f.startswith("run_") and f.endswith(f"_{tag}.csv")]
    csv_path = max((os.path.join(_OUTPUT_DIR, f) for f in csvs),
                   key=os.path.getmtime)
    df = pd.read_csv(csv_path)
    return {
        "label": label, "pct": pct, "eps": eps,
        "self_collided": bool((df["self_collision_dist"] < 0).any()),
        "min_self_dist":   float(df["self_collision_dist"].min()),
        "min_gamma":       float(df["gamma"].min()),
        "max_q_violation": float(df["q_lim_violation"].max()),
        "max_qd_violation":float(df["qd_lim_violation"].max()),
        "max_qd_abs":      float(df["qd_max_abs"].max()),
        "soft_pct":        float(df["soft_fallback"].mean()) * 100.0,
        "final_dist":      float(df["target_dist"].iloc[-1]),
    }


def main():
    rows = []
    n_total = len(SCENARIOS) * len(PCTS) * len(EPSILONS)
    n_done = 0
    for label, target, gain, no_obs in SCENARIOS:
        for pct in PCTS:
            for eps in EPSILONS:
                t0 = time.time()
                row = run_one(label, target, gain, no_obs, pct, eps)
                dt = time.time() - t0
                n_done += 1
                print(f"[{n_done:2d}/{n_total}] {label:10s} g=??? "
                      f"pct={pct:>4.1f}% eps={eps:.2f}  "
                      f"sc={row['min_self_dist']*100:6.2f}cm  "
                      f"\u0393={row['min_gamma']:6.2f}  "
                      f"q_over={row['max_q_violation']*1000:6.2f}mm  "
                      f"qd_max={row['max_qd_abs']:5.2f}  "
                      f"soft={row['soft_pct']:4.1f}%  "
                      f"final={row['final_dist']*1000:5.1f}mm  "
                      f"coll={row['self_collided']}  ({dt:.1f}s)")
                rows.append(row)

    df = pd.DataFrame(rows)
    out = os.path.join(_OUTPUT_DIR, "explore_eps.csv")
    df.to_csv(out, index=False)
    print(f"\n[explore] saved -> {out}")

    # --- Score: where does eps actually help? ---
    print("\n=== Scoring: looking for (eps=0 fails, eps=0.10 ok) at pct>0 ===")
    for label, *_ in SCENARIOS:
        sub = df[df["label"] == label]
        for pct in PCTS:
            row0 = sub[(sub["pct"] == pct) & (sub["eps"] == 0.0)].iloc[0]
            row1 = sub[(sub["pct"] == pct) & (sub["eps"] == 0.10)].iloc[0]
            failed0 = (row0["self_collided"] or
                       row0["max_q_violation"] > 1e-3 or
                       row0["soft_pct"] > 5.0)
            ok1 = (not row1["self_collided"] and
                   row1["max_q_violation"] < 1e-3 and
                   row1["soft_pct"] < 5.0)
            flag = "  <-- HELPFUL" if (failed0 and ok1 and pct > 0) else ""
            if flag or failed0 or not ok1:
                print(f"  {label:10s} pct={pct:>4.1f}%  "
                      f"eps0: q_over={row0['max_q_violation']*1000:6.2f}mm "
                      f"coll={row0['self_collided']} soft={row0['soft_pct']:4.1f}%   "
                      f"eps10: q_over={row1['max_q_violation']*1000:6.2f}mm "
                      f"coll={row1['self_collided']} soft={row1['soft_pct']:4.1f}%"
                      f"{flag}")


if __name__ == "__main__":
    main()
