#!/usr/bin/env python3
"""Probe several aggressive scenarios to find one that actually exercises
the viability + Gamma constraints (i.e., where CFC and VPP-TC can diverge).

Each scenario is run headless under VPP-TC. We look at:
  * how often Gamma was below the safety threshold (gamma_active fraction)
  * how close qd got to its limit
  * whether self_collision_dist ever went negative
  * final tracking error
"""

import os
import subprocess
import sys
import time
from typing import Dict

import numpy as np
import pandas as pd

_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, os.pardir))
_OUTPUT_DIR  = os.path.join(_PROJECT_ROOT, "output")

# Franka Panda velocity limits (deg/s converted to rad/s in simulate.py)
QD_LIM = np.array([2.175, 2.175, 2.175, 2.175, 2.61, 2.61, 2.61])

# Each scenario: (label, target xyz, gain, extra args).
# We deliberately turn obstacles + reactive evasion off so the QP is in charge.
SCENARIOS = [
    ("base_target",
     [0.0, -0.6, 0.3], 50,  []),
    ("cross_body",
     [-0.4, 0.4, 0.6], 200, []),
    ("near_base",
     [0.10, 0.10, 0.30], 200, []),
    ("low_back",
     [0.20, 0.40, 0.20], 250, []),
    ("high_lift",
     [0.0, -0.7, 1.10], 250, []),
    ("under_arm",
     [0.10, -0.10, 0.20], 300, []),
    ("snap_back",
     [-0.30, 0.30, 0.30], 300, []),
]

DURATION = 5.0


def run(label: str, target, gain: float, extra) -> Dict:
    tag = f"probe_{label}"
    cmd = [
        sys.executable,
        os.path.join(_SCRIPT_DIR, "simulate.py"),
        "--no-gui",
        "--no-obstacles",
        "--no-reactive",
        "--duration", str(DURATION),
        "--planner-gain", str(gain),
        "--target-pos", *map(str, target),
        "--tag", tag,
    ] + extra
    print(f"\n[probe] {label}  target={target}  gain={gain}")
    t0 = time.time()
    res = subprocess.run(cmd, cwd=_PROJECT_ROOT,
                         capture_output=True, text=True)
    dt = time.time() - t0
    if res.returncode != 0:
        print(res.stderr[-1500:])
        return {"label": label, "ok": False}

    csvs = [f for f in os.listdir(_OUTPUT_DIR)
            if f.startswith("run_") and f.endswith(f"_{tag}.csv")]
    csv_path = max((os.path.join(_OUTPUT_DIR, f) for f in csvs),
                   key=os.path.getmtime)
    df = pd.read_csv(csv_path)

    # Fraction of timesteps where Gamma constraint was actually added
    gamma_active_frac = float(df["gamma_active"].mean())
    # qd headroom: how close did we get to the per-joint velocity limit?
    qd_max_abs = float(df["qd_max_abs"].max())
    qd_headroom_pct = (1.0 - qd_max_abs / QD_LIM.max()) * 100.0
    # Hard violations
    self_collided = bool((df["self_collision_dist"] < 0).any())
    q_violated   = bool((df["q_lim_violation"] > 1e-4).any())
    qd_violated  = bool((df["qd_lim_violation"] > 1e-3).any())

    out = dict(
        label=label, ok=True, runtime_s=dt,
        gamma_min=float(df["gamma"].min()),
        gamma_active_frac=gamma_active_frac,
        sc_dist_min=float(df["self_collision_dist"].min()),
        qd_max_abs=qd_max_abs,
        qd_headroom_pct=qd_headroom_pct,
        q_lim_max=float(df["q_lim_violation"].max()),
        qd_lim_max=float(df["qd_lim_violation"].max()),
        self_collided=self_collided,
        q_violated=q_violated,
        qd_violated=qd_violated,
        final_d=float(df["target_dist"].iloc[-1]),
        soft_frac=float(df["soft_fallback"].mean()),
        csv=os.path.basename(csv_path),
    )
    print(f"  ran {dt:.1f}s  gamma_min={out['gamma_min']:.2f}  "
          f"gamma_active_frac={out['gamma_active_frac']*100:.1f}%  "
          f"qd_max={out['qd_max_abs']:.2f}  "
          f"sc_min={out['sc_dist_min']:.4f}  "
          f"final_d={out['final_d']:.3f}")
    return out


def main():
    rows = []
    for label, target, gain, extra in SCENARIOS:
        rows.append(run(label, target, gain, extra))
    df = pd.DataFrame(rows)
    out = os.path.join(_OUTPUT_DIR, "probe_summary.csv")
    df.to_csv(out, index=False)
    print(f"\n[probe] saved -> {out}")
    print(df[["label", "gamma_min", "gamma_active_frac", "qd_max_abs",
              "sc_dist_min", "self_collided", "qd_violated", "final_d"]]
          .to_string(index=False))


if __name__ == "__main__":
    main()
