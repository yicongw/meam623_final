#!/usr/bin/env python3
"""Search for an 'edge' scenario where CFC barely passes at alpha=1 but
collides under inertia mismatch, while VPP-TC stays safe across alpha.

Strategy: vary the planner gain on the same under_arm target. Lower gain
slows the EE down -> CFC has more headroom at alpha=1 but is still
sensitive to model error. We test alpha = {0.5, 1.0, 1.5} per gain and
pick the gain where:

    CFC sc_min @ alpha=1.0  >  +0.5 cm   (passes with margin)
    AND  ( CFC sc_min @ alpha=0.5  <  0  OR  CFC sc_min @ alpha=1.5 < 0 )
                                                  (fails under mismatch)
    AND  VPP-TC sc_min @ every alpha > +1 cm
"""

import os
import subprocess
import sys
import time

import numpy as np
import pandas as pd

_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, os.pardir))
_OUTPUT_DIR  = os.path.join(_PROJECT_ROOT, "output")

TARGET = [0.10, -0.10, 0.20]
GAINS = [150, 200, 250]
ALPHAS = [0.5, 1.0, 1.5]
DURATION = 5.0


def run_one(target, gain, alpha, mode):
    tag = f"edge_g{gain}_a{alpha:0.2f}_{mode}".replace(".", "p")
    cmd = [
        sys.executable,
        os.path.join(_SCRIPT_DIR, "simulate.py"),
        "--no-gui",
        "--no-obstacles",
        "--no-reactive",
        "--duration", str(DURATION),
        "--planner-gain", str(gain),
        "--qp-mass-scale", str(alpha),
        "--target-pos", *map(str, target),
        "--tag", tag,
    ]
    if mode == "cfc":
        cmd += ["--no-viability", "--no-gamma"]
    res = subprocess.run(cmd, cwd=_PROJECT_ROOT,
                         capture_output=True, text=True)
    if res.returncode != 0:
        print(f"\n!!! FAILED rc={res.returncode}  tag={tag}")
        print("STDOUT[-2000:]\n" + res.stdout[-2000:])
        print("STDERR[-2000:]\n" + res.stderr[-2000:])
        raise RuntimeError(tag)
    csvs = [f for f in os.listdir(_OUTPUT_DIR)
            if f.startswith("run_") and f.endswith(f"_{tag}.csv")]
    csv_path = max((os.path.join(_OUTPUT_DIR, f) for f in csvs),
                   key=os.path.getmtime)
    df = pd.read_csv(csv_path)
    return {
        "gain": gain, "alpha": alpha, "mode": mode,
        "sc_min":   float(df["self_collision_dist"].min()),
        "gamma_min":float(df["gamma"].min()),
        "qd_max":   float(df["qd_max_abs"].max()),
        "self_coll":bool((df["self_collision_dist"] < 0).any()),
        "final_d":  float(df["target_dist"].iloc[-1]),
        "csv":      os.path.basename(csv_path),
    }


def main():
    rows = []
    for gain in GAINS:
        for alpha in ALPHAS:
            for mode in ("vpptc", "cfc"):
                t0 = time.time()
                row = run_one(TARGET, gain, alpha, mode)
                dt = time.time() - t0
                print(f"  gain={gain} a={alpha} {mode:5s}  "
                      f"sc_min={row['sc_min']*100:6.2f} cm  "
                      f"\u0393_min={row['gamma_min']:6.2f}  "
                      f"final_d={row['final_d']*1000:6.2f} mm  "
                      f"collided={row['self_coll']}  ({dt:.1f}s)")
                rows.append(row)
    df = pd.DataFrame(rows)
    out = os.path.join(_OUTPUT_DIR, "edge_search.csv")
    df.to_csv(out, index=False)
    print(f"\n[edge] saved -> {out}")

    # Score each gain
    print("\n--- Scoring ---")
    for gain in GAINS:
        sub = df[df["gain"] == gain]
        v = sub[sub["mode"] == "vpptc"].set_index("alpha")
        c = sub[sub["mode"] == "cfc"  ].set_index("alpha")
        v_min = v["sc_min"].min() * 100
        c_at1 = c.loc[1.0, "sc_min"] * 100
        c_low = c.loc[0.5, "sc_min"] * 100
        c_hi  = c.loc[1.5, "sc_min"] * 100
        c_collisions = int(c["self_coll"].sum())
        v_collisions = int(v["self_coll"].sum())
        print(f"gain={gain}: VPP-TC min sc={v_min:5.2f}cm (collisions: {v_collisions})  "
              f"CFC sc(0.5/1.0/1.5)={c_low:5.2f}/{c_at1:5.2f}/{c_hi:5.2f}cm "
              f"(collisions: {c_collisions})")


if __name__ == "__main__":
    main()
