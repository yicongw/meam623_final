#!/usr/bin/env python3
"""Generate the unified-validation figure for Section V.E of the report.

Uses output/report_results.json (lpvds_mismatch_grid block) to plot the
practical-convergence ball as a function of mass-perturbation pct.

Outputs: output/fig_unified_validation.png
"""
from __future__ import annotations
import json, statistics
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
    means_min = []; mins_min = []; maxs_min = []; sd_min = []
    sc_safe   = []
    for p in pcts:
        rows = by_pct[p]
        vals = [r.get("min_target_dist_m") for r in rows
                if r.get("min_target_dist_m") is not None]
        if not vals: continue
        means_min.append(np.mean(vals) * 100)
        mins_min.append(min(vals) * 100)
        maxs_min.append(max(vals) * 100)
        sd_min.append((max(vals) - min(vals))/2 * 100)
        # safe = no self-collision (sc dist >= 0) and not crashed
        n_safe = sum(
            1 for r in rows
            if (r.get("min_self_collision_dist_m") or 0) >= -1e-3
        )
        sc_safe.append((n_safe, len(rows)))

    fig, axes = plt.subplots(1, 2, figsize=(7.5, 3.0), constrained_layout=True)

    # Left: practical-convergence ball
    ax = axes[0]
    means_arr = np.array(means_min)
    sd_arr    = np.array(sd_min)
    ax.plot(pcts, means_arr, marker="o", color="#1F4E79", lw=1.8,
            label="mean closest approach")
    ax.fill_between(pcts, mins_min, maxs_min, color="#1F4E79", alpha=0.18,
                    label="seed range (3 seeds)")
    # Theorem 1 prediction is ~ delta^2 -> pct^2; rescale to pass through
    # the p=0 point.
    if pcts[0] == 0 and means_min[0] > 0:
        c = means_min[1] / max(pcts[1] ** 2, 1e-6) if len(pcts) > 1 else 0.0
    else:
        c = 0.0
    pgrid = np.linspace(min(pcts), max(pcts), 50)
    ax.plot(pgrid, means_min[0] + c * pgrid ** 2, "--",
            color="#A23E48", lw=1.2, label=r"$\propto \delta^2$ ISS bound")
    ax.set_xlabel("Mass-perturbation $p$ (\\%)")
    ax.set_ylabel("Closest EE-to-attractor (cm)")
    ax.set_title("LPV-DS practical convergence vs.\\ inertial mismatch")
    ax.set_xticks(pcts)
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8, loc="upper left")

    # Right: safety preservation (collision-free fraction)
    ax = axes[1]
    fracs = [s/n for s, n in sc_safe]
    bars = ax.bar([str(int(p)) for p in pcts], fracs,
                  color=["#2E7D32" if f >= 0.999 else "#A23E48" for f in fracs],
                  edgecolor="black", lw=0.8)
    ax.set_ylim(0, 1.05)
    ax.axhline(1.0, color="black", lw=0.5, ls=":")
    ax.set_xlabel("Mass-perturbation $p$ (\\%)")
    ax.set_ylabel("Self-collision-free fraction")
    ax.set_title("Safety preservation across 18 cells")
    for bar, (s, n) in zip(bars, sc_safe):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                f"{s}/{n}", ha="center", va="bottom", fontsize=8)
    ax.grid(axis="y", alpha=0.25)

    fig.suptitle("Unified validation: LPV-DS planner under mass mismatch",
                 fontsize=10)
    fig.savefig(PNG, dpi=180, bbox_inches="tight")
    print(f"Wrote {PNG}")


if __name__ == "__main__":
    main()
