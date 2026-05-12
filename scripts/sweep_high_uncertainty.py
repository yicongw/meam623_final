#!/usr/bin/env python3
"""High-uncertainty sweep — pushes mass perturbation to 20-50%.

Goals:
  (1) Confirm whether the no_fallback @ obs collision (sc=-0.01cm) from
      sweep_fallback_compare reproduces, or was a fluke from reactive
      evasion interaction.
  (2) See whether bigger uncertainty exposes more collisions in
      no_fallback mode.
  (3) Re-confirm q_over reversal at higher pct.

Speed knobs (kept here as a template for future fast sweeps):
  * DURATION = 3.0s         — failures appear by t=2s, no need for 5s
  * MAX_WORKERS = 3         — ThreadPoolExecutor; PyBullet is CPU-bound,
                              torch model on GPU is tiny, 3 fits comfortably
  * concise scenario set    — only obs (reactive-on / reactive-off)
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

import pandas as pd

_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, os.pardir))
_OUTPUT_DIR  = os.path.join(_PROJECT_ROOT, "output")

# --------- Sweep configuration ---------
# (label, target, gain, no_obstacles, no_reactive)
SCENARIOS = [
    ("obs_react",  [0.00, -0.60, 0.30],  50, False, False),  # reactive ON
    ("obs_noreact",[0.00, -0.60, 0.30],  50, False, True),   # reactive OFF
]
PCTS  = [20.0, 30.0, 40.0, 50.0]
SEEDS = [11, 22, 33, 44, 55, 66]
MODES = ["fallback", "no_fallback"]
DURATION = 3.0
MAX_WORKERS = 3
CRASH_RCS = (3221226505, 3221225477, -1073740791)

_print_lock = threading.Lock()


def run_one(label, target, gain, no_obs, no_react, pct, seed, mode):
    tag = f"hu_{label}_{mode}_p{int(pct):02d}_s{seed:02d}"
    cmd = [
        sys.executable,
        os.path.join(_SCRIPT_DIR, "simulate.py"),
        "--no-gui",
        "--duration", str(DURATION),
        "--planner-gain", str(gain),
        "--mass-perturb-pct", str(pct),
        "--mass-perturb-seed", str(seed),
        "--epsilon-margin", "0.0",
        "--target-pos", *map(str, target),
        "--tag", tag,
    ]
    if no_obs:    cmd.append("--no-obstacles")
    if no_react:  cmd.append("--no-reactive")
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


def _runner(args, idx, n_total):
    label, target, gain, no_obs, no_react, pct, seed, mode = args
    t0 = time.time()
    row = run_one(label, target, gain, no_obs, no_react, pct, seed, mode)
    dt = time.time() - t0
    marker = ""
    if row["crashed"]:
        marker += " ***CRASH***"
    if row["self_collided"] and not row["crashed"]:
        marker += " ***COLL***"
    sc = row["min_self_dist"]
    sc_s = f"{sc*100:6.2f}cm" if sc == sc else "  nan"
    with _print_lock:
        print(f"[{idx:3d}/{n_total}] {label:11s} {mode:11s} "
              f"pct={pct:>4.1f}% s={seed:>2d}  "
              f"sc={sc_s}  Γ={row['min_gamma']:7.2f}  "
              f"q_over={row['max_q_violation']*1000:6.2f}mm  "
              f"qd={row['max_qd_abs']:6.2f}{marker}  ({dt:.1f}s)",
              flush=True)
    return row


def main():
    work = []
    for label, target, gain, no_obs, no_react in SCENARIOS:
        for pct in PCTS:
            for seed in SEEDS:
                for mode in MODES:
                    work.append((label, target, gain, no_obs, no_react,
                                 pct, seed, mode))
    n_total = len(work)
    print(f"[hu] {n_total} cells, "
          f"{MAX_WORKERS} parallel workers, duration={DURATION}s")

    rows: List[dict] = []
    t_start = time.time()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_runner, w, i+1, n_total): i
                   for i, w in enumerate(work)}
        for fut in as_completed(futures):
            rows.append(fut.result())
    t_total = time.time() - t_start
    print(f"\n[hu] {n_total} cells in {t_total/60:.1f} min "
          f"({t_total/n_total:.1f}s/cell wall, "
          f"~{MAX_WORKERS*t_total/n_total:.1f}s/cell CPU)")

    df = pd.DataFrame(rows)
    out = os.path.join(_OUTPUT_DIR, "high_uncertainty.csv")
    df.to_csv(out, index=False)
    print(f"[hu] saved -> {out}")

    # ---- Summaries ----
    print("\n=== Self-collisions per (scenario, pct, mode) — /6 seeds ===")
    for label, *_ in SCENARIOS:
        sub = df[df["label"] == label]
        piv = sub.pivot_table(index="pct", columns="mode",
                              values="self_collided", aggfunc="sum")
        print(f"\n[{label}]")
        print(piv.to_string())

    print("\n=== Crashes per (scenario, pct, mode) ===")
    for label, *_ in SCENARIOS:
        sub = df[df["label"] == label]
        piv = sub.pivot_table(index="pct", columns="mode",
                              values="crashed", aggfunc="sum")
        print(f"\n[{label}]")
        print(piv.to_string())

    print("\n=== Mean min_self_dist (cm) per (scenario, pct, mode) ===")
    for label, *_ in SCENARIOS:
        sub = df[df["label"] == label]
        piv = sub.pivot_table(index="pct", columns="mode",
                              values="min_self_dist", aggfunc="mean") * 100
        print(f"\n[{label}]")
        print(piv.round(2).to_string())

    print("\n=== Per-cell q_over diff (fallback − no_fallback), mm ===")
    for label, *_ in SCENARIOS:
        sub = df[df["label"] == label]
        for pct in PCTS:
            f = sub[(sub["mode"]=="fallback")    & (sub["pct"]==pct)]\
                  .set_index("seed")["max_q_violation"].sort_index()
            n = sub[(sub["mode"]=="no_fallback") & (sub["pct"]==pct)]\
                  .set_index("seed")["max_q_violation"].sort_index()
            diff = (f - n) * 1000
            print(f"  {label:11s} pct={pct:>4.1f}%  "
                  f"diffs (mm) = {diff.values.round(2).tolist()}  "
                  f"mean={diff.mean():+.2f}")


if __name__ == "__main__":
    main()
