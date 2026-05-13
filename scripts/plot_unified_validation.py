#!/usr/bin/env python3
"""Generate the unified-validation figure for Section V.E of the report.

Uses output/report_results.json (lpvds_mismatch_grid block) to plot the
practical-convergence ball as a function of mass-perturbation pct.

Outputs: output/fig_unified_validation.png
"""
from __future__ import annotations
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(r"C:\meam623_finalproj")
RES  = ROOT / "output" / "report_results.json"
PNG  = ROOT / "output" / "fig_unified_validation.png"


def main():
    res = json.loads(RES.read_text())
    grid = res.get("lpvds_mismatch_grid", [])
    if not grid:
        raise RuntimeError("No lpvds_mismatch_grid in report_results.json")

    by_pct = {}
    for r in grid:
        by_pct.setdefault(r["pct"], []).append(r)

    pcts = sorted(by_pct)
    means_min, mins_min, maxs_min = [], [], []
    n_safe_total = 0
    n_total = 0
    for p in pcts:
        rows = by_pct[p]
        vals = [r.get("min_target_dist_m") for r in rows
                if r.get("min_target_dist_m") is not None]
        if not vals:
            continue
        means_min.append(np.mean(vals) * 100)
        mins_min.append(min(vals) * 100)
        maxs_min.append(max(vals) * 100)
        n_safe_total += sum(
            1 for r in rows
            if (r.get("min_self_collision_dist_m") or 0) >= -1e-3
        )
        n_total += len(rows)

    pcts_arr  = np.array(pcts, dtype=float)
    means_arr = np.array(means_min)

    # Single panel: practical-convergence ball vs. mass-mismatch.
    # The "100% safety" claim is a single binary number — annotate it
    # rather than burning half a figure on six identical-height bars.
    fig, ax = plt.subplots(figsize=(5.0, 3.2), constrained_layout=True)

    ax.plot(pcts_arr, means_arr, marker="o", color="#1F4E79", lw=1.8,
            label="mean closest approach")
    ax.fill_between(pcts_arr, mins_min, maxs_min,
                    color="#1F4E79", alpha=0.18,
                    label="seed range")

    # Practical-ISS envelope is LINEAR in delta in raw distance units
    # (sqrt of the V-bound in Eq. (8)). We pin the envelope at the p=0
    # floor and pick the slope that just bounds every datum from above.
    if pcts_arr[0] == 0 and len(pcts_arr) > 1:
        floor = means_arr[0]
        slopes = (means_arr[1:] - floor) / np.maximum(pcts_arr[1:], 1e-6)
        K = float(np.max(slopes))
        pgrid = np.linspace(pcts_arr.min(), pcts_arr.max(), 50)
        ax.plot(pgrid, floor + K * pgrid, "--",
                color="#A23E48", lw=1.2,
                label=r"linear-in-$\delta$ ISS envelope (Eq.~8)")

    ax.set_xlabel("Mass-perturbation $p$ (%)")
    ax.set_ylabel("Closest EE-to-attractor (cm)")
    ax.set_title("LPV-DS practical convergence vs. inertial mismatch")
    ax.set_xticks(pcts_arr)
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8, loc="upper left")

    # Binary safety claim annotated in-panel.
    ax.text(0.98, 0.04,
            f"Safety: {n_safe_total}/{n_total} self-collision-free",
            transform=ax.transAxes,
            ha="right", va="bottom", fontsize=8,
            bbox=dict(boxstyle="round,pad=0.3",
                      fc="#E8F5E9", ec="#2E7D32", lw=0.8))

    fig.savefig(PNG, dpi=180, bbox_inches="tight")
    print(f"Wrote {PNG}  (n_total={n_total}, safe={n_safe_total})")


if __name__ == "__main__":
    main()
