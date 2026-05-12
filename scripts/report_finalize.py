#!/usr/bin/env python3
"""Post-driver finalization step.

Steps:
  1. If multi_platform.dual_openarm is missing in report_results.json, re-run
     simulate_dual_openarm.py (now patched to recover from OSQP errors) and
     splice the resulting per-cell stats back into the JSON.
  2. Render fig_unified_validation.png from the grid.
  3. Substitute <<...>> placeholders in final_report.tex.
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"C:\meam623_finalproj")
PY = sys.executable
RES = ROOT / "output" / "report_results.json"
SIM_DUAL_OPENARM = "scripts/simulate_dual_openarm.py"

# Re-use parser/runner helpers from the driver.
sys.path.insert(0, str(ROOT / "scripts"))
from report_experiments import (  # noqa: E402
    parse_run_csv, latest_run_csv, run_sim,
)


def _re_run(script: str, tag: str, base: str,
            extra: list = None, timeout: int = 420):
    """Force a fresh run of <script> with --tag <tag> and return its stats."""
    args = [script, "--no-gui", "--duration", "6.0", "--tag", tag]
    if extra:
        args.extend(extra)
    print(f"[finalize] running {script} (tag={tag}) ...")
    rc, _ = run_sim(args, timeout=timeout)
    csvp = latest_run_csv(tag, base=base)
    if csvp is None:
        print(f"[finalize] WARN: no CSV produced for {script}")
        return None
    stats = parse_run_csv(csvp)
    stats["csv"] = csvp.name
    stats["rc"]  = rc
    return stats


def ensure_dual_panda(res: dict) -> dict:
    """Re-run dual_panda with the contact-filter patch applied.

    The original dual_panda CSV reported a 0.24 cm "min inter-arm distance"
    that was actually a contact-breaking-threshold artifact, not real
    penetration. simulate_dual.py is now patched to filter c[8] < 0; the
    re-run yields the correct number.
    """
    mp = res.setdefault("multi_platform", {})
    tag = "rep2_dual_panda"
    stats = _re_run("scripts/simulate_dual.py", tag, "dual_run_",
                    extra=["--model-path",
                           "assets/models/transformer_gamma_dual.pt"])
    if stats is None:
        print("[finalize] keeping previous dual_panda block")
        return res
    # Pass the explicit model path the same way the original driver did
    # (default model path is wrong; we rely on the dual_panda call here).
    mp["dual_panda"] = stats
    print(f"[finalize] dual_panda stats refreshed:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return res


def ensure_openarm(res: dict) -> dict:
    mp = res.setdefault("multi_platform", {})
    if mp.get("dual_openarm"):
        print("[finalize] dual_openarm already present, skipping re-run")
        return res
    stats = _re_run(SIM_DUAL_OPENARM, "rep2_dual_openarm",
                    "openarm_dual_run_")
    if stats is None:
        print("[finalize] WARN: no OpenArm CSV; leaving block empty")
        return res
    mp["dual_openarm"] = stats
    print(f"[finalize] OpenArm stats:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return res


def main() -> None:
    res = json.loads(RES.read_text())
    res = ensure_dual_panda(res)
    res = ensure_openarm(res)
    RES.write_text(json.dumps(res, indent=2, default=str))
    print(f"[finalize] updated {RES}")

    # Plot Figure 4
    print("[finalize] generating fig_unified_validation.png ...")
    subprocess.check_call([PY, "scripts/plot_unified_validation.py"],
                          cwd=str(ROOT))

    # Fill placeholders
    print("[finalize] substituting placeholders in final_report.tex ...")
    subprocess.check_call([PY, "scripts/report_fill_placeholders.py"],
                          cwd=str(ROOT))

    print("[finalize] DONE")


if __name__ == "__main__":
    main()
