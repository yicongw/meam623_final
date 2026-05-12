#!/usr/bin/env python3
"""Replace <<...>> placeholders in final_report.tex with real numbers.

Reads:
  output/report_results.json  (driver output: multi-platform + LPV-DS sweep)
  output/report_numbers.json  (analyzer output: existing-CSV stats)

Edits in-place: report/final_report.tex.
"""
from __future__ import annotations
import json, re, statistics
from pathlib import Path

ROOT = Path(r"C:\meam623_finalproj")
TEX  = ROOT / "report" / "final_report.tex"
RES  = ROOT / "output" / "report_results.json"
NUM  = ROOT / "output" / "report_numbers.json"


def fmt(x, n=1, dash_if_nan=True):
    try:
        if x is None: return "--"
        v = float(x)
        if v != v: return "--" if dash_if_nan else "nan"
        # Clip values within ±1e-2 cm (= 0.1 mm) to 0 -- PyBullet's contact
        # resolver returns ~10-50 um numerical noise even for clean contact.
        if -1e-2 <= v <= 1e-2:
            v = 0.0
        return f"{v:.{n}f}"
    except (TypeError, ValueError):
        return "--"


def main():
    res = json.loads(RES.read_text())
    nums = json.loads(NUM.read_text())

    # ----- Multi-platform numbers -----
    mp = res.get("multi_platform", {})
    sp = mp.get("single_panda", {})
    dp = mp.get("dual_panda",   {})
    op = mp.get("dual_openarm", {})

    repl = {
        "<<HZ_SINGLE>>":    fmt(sp.get("loop_hz_mean"), 1),
        "<<HZ_DUAL>>":      fmt(dp.get("loop_hz_mean"), 1),
        "<<HZ_OPENARM>>":   fmt(op.get("loop_hz_mean"), 1),
        "<<MS_SINGLE>>":    fmt(sp.get("step_ms_p50"),  1),
        "<<MS_DUAL>>":      fmt(dp.get("step_ms_p50"),  1),
        "<<MS_OPENARM>>":   fmt(op.get("step_ms_p50"),  1),
        "<<DSC_SINGLE>>":   fmt((sp.get("min_self_collision_dist_m") or 0)*100, 2),
        "<<DI_DUAL>>":      fmt((dp.get("min_inter_arm_dist_m")  or 0)*100, 2),
        "<<DI_OPENARM>>":   fmt((op.get("min_inter_arm_dist_m")  or 0)*100, 2),
        "<<XF_SINGLE>>":    fmt((sp.get("final_target_dist_m")   or 0)*100, 2),
        "<<LC_DUAL>>":      fmt((dp.get("mean_lc_dist_left_m")   or 0)*100, 2),
        "<<LC_OPENARM>>":   fmt((op.get("mean_lc_dist_left_m")   or 0)*100, 2),
    }

    # ----- Unified LPV-DS x mass-mismatch sweep -----
    grid = res.get("lpvds_mismatch_grid", [])
    by_pct = {}
    for r in grid:
        by_pct.setdefault(r["pct"], []).append(r)

    def stats_at(pct_list):
        mins = []
        finals = []
        for pct in pct_list:
            for r in by_pct.get(pct, []):
                v = r.get("min_target_dist_m")
                f = r.get("final_target_dist_m")
                if v is not None: mins.append(v * 100)
                if f is not None: finals.append(f * 100)
        return mins, finals

    for pct in (0, 10, 20, 30):
        mins, finals = stats_at([float(pct)])
        m_mean = statistics.mean(mins) if mins else float("nan")
        m_max  = max(mins) if mins else float("nan")
        repl[f"<<U{pct:02d}_M>>"] = fmt(m_mean, 1)
        repl[f"<<U{pct:02d}_X>>"] = fmt(m_max,  1)
    # 40-50 combined
    mins, finals = stats_at([40.0, 50.0])
    repl["<<U45_M>>"] = fmt(statistics.mean(mins) if mins else float("nan"), 1)
    repl["<<U45_X>>"] = fmt(max(mins) if mins else float("nan"), 1)

    # ----- Apply -----
    tex = TEX.read_text(encoding="utf-8")
    n_replaced = 0
    for k, v in repl.items():
        # The .tex file escapes underscores for \texttt{} -- search for both
        # the bare form (<<HZ_SINGLE>>) and the LaTeX-escaped form
        # (<<HZ\_SINGLE>>).
        sk = k.replace("_", r"\_")
        for variant in (sk, k):
            if variant in tex:
                n_replaced += tex.count(variant)
                tex = tex.replace(variant, v)
                break
    TEX.write_text(tex, encoding="utf-8")
    print(f"Replaced {n_replaced} placeholders in {TEX}")
    # Report which keys still appear in the file (might be missing data)
    leftover = []
    for k in repl:
        if k in tex or k.replace("_", r"\_") in tex:
            leftover.append(k)
    if leftover:
        print("WARNING: the following placeholders still in file:")
        for k in leftover: print(" ", k)
    # Quick echo of numbers
    print("\nValues used:")
    for k, v in repl.items():
        print(f"  {k:>16s} -> {v}")


if __name__ == "__main__":
    main()
