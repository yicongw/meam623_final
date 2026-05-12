#!/usr/bin/env python3
"""Search for an 'overshoot' scenario:

    CFC sc_min @ alpha=1.0   >  +1.0 cm   (safe with margin)
    CFC self_coll @ alpha=1.3 OR 1.5      (over-command -> overshoot fail)
    VPP-TC safe everywhere.

Idea: pick targets that require a long sweep across the workspace.  The QP
gets through cleanly with the correct inertia.  When alpha > 1 the controller
commands ~alpha times more torque than needed, the true arm accelerates too
fast, swings past, and clips a self-collision configuration.
"""

import os
import subprocess
import sys
import time

import pandas as pd

_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, os.pardir))
_OUTPUT_DIR  = os.path.join(_PROJECT_ROOT, "output")

# (label, target, gain)
SCENARIOS = [
    ("reach_x",   [0.40, 0.00, 0.30], 400),
    ("reach_xy",  [0.30, 0.20, 0.25], 400),
    ("reach_far", [0.45, -0.10, 0.30], 500),
    ("snake_lo",  [0.30, 0.20, 0.15], 400),
    ("snake_hi",  [0.30, 0.20, 0.15], 600),
    ("twist",     [0.20, -0.25, 0.30], 500),
]
ALPHAS = [1.0, 1.3, 1.5]
DURATION = 5.0


def run_one(label, target, gain, alpha, mode):
    tag = f"ovs_{label}_a{alpha:0.2f}_{mode}".replace(".", "p")
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
    last_err = None
    for attempt in range(3):
        res = subprocess.run(cmd, cwd=_PROJECT_ROOT,
                             capture_output=True, text=True)
        if res.returncode == 0:
            break
        last_err = res.stderr[-1500:]
        # Transient torch DLL load races on Win — back off and retry.
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
        "label": label, "gain": gain, "alpha": alpha, "mode": mode,
        "sc_min":   float(df["self_collision_dist"].min()),
        "gamma_min":float(df["gamma"].min()),
        "self_coll":bool((df["self_collision_dist"] < 0).any()),
        "final_d":  float(df["target_dist"].iloc[-1]),
    }


def main():
    rows = []
    for label, target, gain in SCENARIOS:
        for alpha in ALPHAS:
            for mode in ("vpptc", "cfc"):
                t0 = time.time()
                row = run_one(label, target, gain, alpha, mode)
                dt = time.time() - t0
                print(f"  {label:10s} g={gain} a={alpha} {mode:5s}  "
                      f"sc={row['sc_min']*100:6.2f}cm  "
                      f"\u0393={row['gamma_min']:5.2f}  "
                      f"final={row['final_d']*1000:6.2f}mm  "
                      f"coll={row['self_coll']}  ({dt:.1f}s)")
                rows.append(row)
    df = pd.DataFrame(rows)
    out = os.path.join(_OUTPUT_DIR, "overshoot_search.csv")
    df.to_csv(out, index=False)
    print(f"\n[ovs] saved -> {out}")

    # Score
    print("\n--- Scoring (looking for: CFC safe @ 1.0, fail @ 1.3 or 1.5) ---")
    for label, target, gain in SCENARIOS:
        sub = df[(df["label"] == label) & (df["gain"] == gain)]
        v = sub[sub["mode"] == "vpptc"].set_index("alpha")
        c = sub[sub["mode"] == "cfc"  ].set_index("alpha")
        v_coll = int(v["self_coll"].sum())
        c_at1  = c.loc[1.0]
        c_13   = c.loc[1.3]
        c_15   = c.loc[1.5]
        flag = ""
        if (c_at1["sc_min"] > 0.01 and
            (c_13["self_coll"] or c_15["self_coll"]) and
            v_coll == 0):
            flag = "  <-- CANDIDATE"
        print(f"  {label:10s} g={gain}: "
              f"VPP-TC coll={v_coll}/3   "
              f"CFC sc(1.0/1.3/1.5)="
              f"{c_at1['sc_min']*100:5.2f}/"
              f"{c_13['sc_min']*100:5.2f}/"
              f"{c_15['sc_min']*100:5.2f} cm  "
              f"final={c_at1['final_d']*1000:5.1f}/"
              f"{c_13['final_d']*1000:5.1f}/"
              f"{c_15['final_d']*1000:5.1f} mm{flag}")


if __name__ == "__main__":
    main()
