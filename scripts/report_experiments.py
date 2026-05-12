#!/usr/bin/env python3
"""Drive every experiment the final report still needs.

Output is a single JSON: output/report_results.json with one block per
experiment. Each individual run is also persisted as a per-run CSV under
output/run_*.csv (the simulate.py default).

Run *headless* and back-to-back. Total budget on Yicong's laptop:
  - LPV-DS x mass-mismatch sweep   ~ 15 min
  - Multi-platform timing          ~ 3 min
  - Aggregate                      ~ 1 s
"""
from __future__ import annotations
import csv
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(r"C:\meam623_finalproj")
PY = sys.executable
OUT = ROOT / "output"
LPVDS_NPZ = ROOT / "assets" / "ds_models" / "my_demo.npz"
RESULTS_JSON = OUT / "report_results.json"
LOG = OUT / "report_experiments.log"

LOG.parent.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_sim(args: list[str], *, timeout=300) -> tuple[int, str]:
    """Invoke simulate.py / simulate_dual.py and capture last lines of stdout."""
    cmd = [PY] + args
    log("$ " + " ".join(str(c) for c in cmd))
    t0 = time.time()
    p = subprocess.run(cmd, cwd=str(ROOT),
                       capture_output=True, text=True, timeout=timeout)
    dt = time.time() - t0
    tail = "\n".join(p.stdout.splitlines()[-10:])
    log(f"  exit={p.returncode}  wall={dt:.1f}s")
    if p.returncode != 0:
        log("  STDERR tail:\n" + "\n".join(p.stderr.splitlines()[-10:]))
    return p.returncode, tail


def latest_run_csv(prefix: str, base="run_"):
    """Return the most-recent output/<base>*<prefix>*.csv."""
    cands = sorted(OUT.glob(f"{base}*{prefix}*.csv"))
    return cands[-1] if cands else None


def parse_run_csv(path: Path) -> dict:
    """Compute summary statistics from a per-run CSV.

    Single-arm columns (simulate.py):
      time, self_collision_dist, gamma, real_dist, target_dist,
      runtime_ms, end_x, end_y, end_z (+ a few extras)
    Dual-arm columns (simulate_dual*.py):
      time, collision_dist, inter_arm_dist, gamma, lc_dist_left,
      lc_dist_right, runtime_ms (+ radius for simulate_dual.py)
    """
    times, gamma, rt = [], [], []
    sc, real_d, tgt = [], [], []
    inter, coll = [], []
    lcL, lcR = [], []
    xs, ys, zs = [], [], []
    with open(path, newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                times.append(float(row["time"]))
                rt.append(float(row["runtime_ms"]))
                gamma.append(float(row["gamma"]))
            except (KeyError, ValueError):
                continue
            for src, dst in (("self_collision_dist", sc),
                             ("real_dist", real_d),
                             ("target_dist", tgt),
                             ("inter_arm_dist", inter),
                             ("collision_dist", coll),
                             ("lc_dist_left", lcL),
                             ("lc_dist_right", lcR),
                             ("end_x", xs), ("end_y", ys), ("end_z", zs)):
                if src in row:
                    try: dst.append(float(row[src]))
                    except ValueError: pass
    if not times:
        return {}
    plen = 0.0
    for i in range(1, len(xs)):
        dx = xs[i] - xs[i - 1]; dy = ys[i] - ys[i - 1]; dz = zs[i] - zs[i - 1]
        plen += (dx * dx + dy * dy + dz * dz) ** 0.5
    out = {
        "n_steps": len(times),
        "duration_s": times[-1] - times[0],
        "step_ms_mean": statistics.mean(rt),
        "step_ms_p50": statistics.median(rt),
        "step_ms_p95": sorted(rt)[int(len(rt) * 0.95)],
        "step_ms_max": max(rt),
        "loop_hz_mean": 1000.0 / statistics.mean(rt),
        "min_gamma": min(gamma),
    }
    if sc:    out["min_self_collision_dist_m"] = min(sc)
    if real_d:out["min_obstacle_dist_m"]      = min(real_d)
    if tgt:
        out["final_target_dist_m"] = tgt[-1]
        out["min_target_dist_m"]   = min(tgt)
    if inter: out["min_inter_arm_dist_m"]     = min(inter)
    if coll:  out["min_collision_dist_m"]     = min(coll)
    if lcL:   out["mean_lc_dist_left_m"]      = statistics.mean(lcL)
    if lcR:   out["mean_lc_dist_right_m"]     = statistics.mean(lcR)
    if xs:    out["ee_path_length_m"]         = plen
    return out


# -----------------------------------------------------------------------------
# Experiment 1 -- LPV-DS x mass-mismatch unified validation grid.
# -----------------------------------------------------------------------------

LPVDS_PCTS = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0]
LPVDS_SEEDS = [11, 22, 33]


def run_lpvds_mismatch_sweep() -> list[dict]:
    """Unified validation: LPV-DS planner under mass mismatch.

    Run with --no-obstacles to isolate the controller-mismatch effect from
    obstacle reactivity. Use 8 s so the LPV-DS demo path has time to graze
    the attractor before its natural overshoot/loop-back. Convergence is
    reported as min_target_dist_m (closest approach), since the demo
    overshoots the attractor by construction.
    """
    rows = []
    for pct in LPVDS_PCTS:
        for seed in LPVDS_SEEDS:
            tag = f"u2_p{int(pct):02d}_s{seed}"
            args = [
                "scripts/simulate.py", "--no-gui",
                "--duration", "8.0",
                "--planner", "lpvds",
                "--lpvds-npz", str(LPVDS_NPZ),
                "--mass-perturb-pct", str(pct),
                "--mass-perturb-seed", str(seed),
                "--start-on-demo",
                "--no-obstacles",
                "--tag", tag,
            ]
            rc, _ = run_sim(args, timeout=240)
            csvp = latest_run_csv(tag)
            if csvp is None:
                log(f"  ! no CSV for tag {tag}")
                continue
            stats = parse_run_csv(csvp)
            stats.update({"pct": pct, "seed": seed,
                          "csv": csvp.name, "ok": rc == 0})
            rows.append(stats)
            log(f"  -> p={pct:>4.1f}%  s={seed}  "
                f"min_d={stats.get('min_target_dist_m', float('nan')):.4f}m  "
                f"final={stats.get('final_target_dist_m', float('nan')):.4f}m  "
                f"min_sc={stats.get('min_self_collision_dist_m', float('nan')):.4f}m  "
                f"hz={stats.get('loop_hz_mean', 0):.1f}")
    return rows


# -----------------------------------------------------------------------------
# Experiment 2 -- Multi-platform timing
# -----------------------------------------------------------------------------

def run_multi_platform() -> dict:
    """If a fresh CSV with the rep_* tag already exists, skip the run."""
    out = {}

    # 2a. Single-arm Panda baseline
    tag = "rep_single_panda"
    csvp = latest_run_csv(tag)
    if csvp is None:
        run_sim(["scripts/simulate.py", "--no-gui", "--duration", "4.0",
                 "--tag", tag], timeout=180)
        csvp = latest_run_csv(tag)
    if csvp:
        out["single_panda"] = {**parse_run_csv(csvp), "csv": csvp.name}

    # 2b. Dual-arm Panda
    tag = "rep_dual_panda"
    csvp = latest_run_csv(tag, base="dual_run_")
    if csvp is None:
        run_sim(["scripts/simulate_dual.py", "--no-gui", "--duration", "6.0",
                 "--model-path", "assets/models/transformer_gamma_dual.pt",
                 "--tag", tag], timeout=420)
        csvp = latest_run_csv(tag, base="dual_run_")
    if csvp:
        out["dual_panda"] = {**parse_run_csv(csvp), "csv": csvp.name}

    # 2c. Dual OpenArm (the porting claim)
    tag = "rep_dual_openarm"
    csvp = latest_run_csv(tag, base="openarm_dual_run_")
    if csvp is None:
        run_sim(["scripts/simulate_dual_openarm.py", "--no-gui",
                 "--duration", "6.0", "--tag", tag], timeout=420)
        csvp = latest_run_csv(tag, base="openarm_dual_run_")
    if csvp:
        out["dual_openarm"] = {**parse_run_csv(csvp), "csv": csvp.name}

    return out


# -----------------------------------------------------------------------------
# Aggregate existing summary CSVs (so report_results.json is self-contained)
# -----------------------------------------------------------------------------

def aggregate_existing() -> dict:
    summaries = {}
    files = [
        "compare_summary.csv", "fallback_compare.csv",
        "fallback_robustness.csv", "proposal_mismatch.csv",
        "proposal_mismatch_pilot.csv", "probe_summary.csv",
        "high_uncertainty.csv", "edge_search.csv", "explore_eps.csv",
    ]
    for name in files:
        p = OUT / name
        if not p.exists():
            continue
        with open(p, newline="") as f:
            rows = list(csv.DictReader(f))
        summaries[name] = rows
    return summaries


def main() -> None:
    log("=" * 60)
    log("REPORT EXPERIMENTS DRIVER")
    log("=" * 60)

    log("Phase 1/3: aggregate existing summary CSVs")
    existing = aggregate_existing()
    for k, v in existing.items():
        log(f"  loaded {k}: {len(v)} rows")

    log("Phase 2/3: multi-platform timing (3 short runs)")
    multi = run_multi_platform()

    log("Phase 3/3: LPV-DS x mass-mismatch sweep (18 runs ~ 15 min)")
    lpvds_grid = run_lpvds_mismatch_sweep()

    out = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "existing_csvs": existing,
        "multi_platform": multi,
        "lpvds_mismatch_grid": lpvds_grid,
    }
    RESULTS_JSON.write_text(json.dumps(out, indent=2, default=str))
    log(f"Wrote {RESULTS_JSON}")
    log("DONE.")


if __name__ == "__main__":
    main()
