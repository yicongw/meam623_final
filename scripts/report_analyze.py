#!/usr/bin/env python3
"""Compute every number the final report will cite.

Reads the summary CSVs in output/ and emits a JSON with derived stats:
  - VPP-TC vs CFC head-to-head
  - Fallback ablation at low (0-20%) and high (20-50%) mass perturbation
  - epsilon-margin sweep
  - Probe-scenario summary

Prints a human-readable table for sanity-checking; also writes
output/report_numbers.json so the LaTeX template can copy-paste.
"""
from __future__ import annotations
import csv, json, os, statistics
from collections import defaultdict
from pathlib import Path

OUT = Path(r"C:\meam623_finalproj\output")
NUMS = OUT / "report_numbers.json"


def load(name):
    p = OUT / name
    if not p.exists(): return []
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def fnum(s, default=float("nan")):
    try: return float(s)
    except (TypeError, ValueError): return default

def fbool(s):
    return str(s).strip().lower() in ("true", "1", "yes")


# ---------------------------------------------------------------------------
# 1. VPP-TC vs CFC (compare_summary.csv)
# ---------------------------------------------------------------------------
def baseline_vs_vpptc():
    rows = load("compare_summary.csv")
    by_label = defaultdict(dict)
    for r in rows:
        by_label[r["label"]][r["mode"]] = r
    results = {"per_scenario": {}, "totals": {}}
    n_vpptc_safe = n_cfc_safe = 0
    n_pairs = 0
    final_d_vpptc, final_d_cfc = [], []
    for label, modes in by_label.items():
        if "vpptc" not in modes or "cfc" not in modes:
            continue
        n_pairs += 1
        v, c = modes["vpptc"], modes["cfc"]
        v_safe = not fbool(v["self_coll"])
        c_safe = not fbool(c["self_coll"])
        n_vpptc_safe += int(v_safe)
        n_cfc_safe   += int(c_safe)
        final_d_vpptc.append(fnum(v["final_d"]))
        final_d_cfc.append(fnum(c["final_d"]))
        results["per_scenario"][label] = {
            "vpptc": {"final_d_m": fnum(v["final_d"]),
                      "self_coll": fbool(v["self_coll"]),
                      "sc_min_m":  fnum(v["sc_min"]),
                      "qd_max":    fnum(v["qd_max"]),
                      "max_S":     fnum(v["max_S"]),
                      "gamma_min": fnum(v["gamma_min"])},
            "cfc":   {"final_d_m": fnum(c["final_d"]),
                      "self_coll": fbool(c["self_coll"]),
                      "sc_min_m":  fnum(c["sc_min"]),
                      "qd_max":    fnum(c["qd_max"]),
                      "max_S":     fnum(c["max_S"]),
                      "gamma_min": fnum(c["gamma_min"])},
        }
    results["totals"] = {
        "n_scenarios": n_pairs,
        "vpptc_self_coll_free": n_vpptc_safe,
        "cfc_self_coll_free":   n_cfc_safe,
        "vpptc_final_d_mean_m": statistics.mean(final_d_vpptc) if final_d_vpptc else None,
        "cfc_final_d_mean_m":   statistics.mean(final_d_cfc)   if final_d_cfc   else None,
    }
    return results


# ---------------------------------------------------------------------------
# 2. Fallback ablation -- low perturbation (fallback_compare.csv)
# ---------------------------------------------------------------------------
def fallback_low():
    rows = load("fallback_compare.csv")
    out = {"by_pct_mode": defaultdict(lambda: {"n": 0, "self_coll": 0,
                                                "final_dists": [],
                                                "min_self_dists": [],
                                                "soft_pcts": []})}
    for r in rows:
        key = (fnum(r["pct"]), r["mode"])
        b = out["by_pct_mode"][key]
        b["n"] += 1
        if fbool(r["self_collided"]): b["self_coll"] += 1
        b["final_dists"].append(fnum(r["final_dist"]))
        b["min_self_dists"].append(fnum(r["min_self_dist"]))
        b["soft_pcts"].append(fnum(r["soft_pct"]))
    serial = []
    for (pct, mode), b in sorted(out["by_pct_mode"].items()):
        serial.append({
            "pct": pct, "mode": mode, "n": b["n"],
            "self_coll": b["self_coll"],
            "final_dist_mean": statistics.mean(b["final_dists"]),
            "final_dist_max":  max(b["final_dists"]),
            "min_self_dist_min": min(b["min_self_dists"]),
            "soft_pct_mean": statistics.mean(b["soft_pcts"]),
        })
    # Totals across all rows
    totals = {"n_total": len(rows), "n_fallback": 0, "n_no_fallback": 0,
              "fb_self_coll": 0, "nofb_self_coll": 0}
    for r in rows:
        if r["mode"] == "fallback":
            totals["n_fallback"] += 1
            if fbool(r["self_collided"]): totals["fb_self_coll"] += 1
        else:
            totals["n_no_fallback"] += 1
            if fbool(r["self_collided"]): totals["nofb_self_coll"] += 1
    return {"per_cell": serial, "totals": totals}


# ---------------------------------------------------------------------------
# 3. Fallback ablation -- HIGH perturbation (high_uncertainty.csv)
# ---------------------------------------------------------------------------
def fallback_high():
    rows = load("high_uncertainty.csv")
    bins = defaultdict(lambda: {"n": 0, "self_coll": 0,
                                 "final_dists": [], "min_self_dists": [],
                                 "soft_pcts": []})
    for r in rows:
        key = (fnum(r["pct"]), r["mode"])
        b = bins[key]
        b["n"] += 1
        if fbool(r["self_collided"]): b["self_coll"] += 1
        b["final_dists"].append(fnum(r["final_dist"]))
        b["min_self_dists"].append(fnum(r["min_self_dist"]))
        b["soft_pcts"].append(fnum(r["soft_pct"]))
    serial = []
    for (pct, mode), b in sorted(bins.items()):
        serial.append({
            "pct": pct, "mode": mode, "n": b["n"],
            "self_coll": b["self_coll"],
            "final_dist_mean": statistics.mean(b["final_dists"]),
            "final_dist_max":  max(b["final_dists"]),
            "min_self_dist_min": min(b["min_self_dists"]),
            "soft_pct_mean": statistics.mean(b["soft_pcts"]),
        })
    # Totals
    totals = {"n_total": len(rows), "fb_total": 0, "fb_self_coll": 0,
              "nofb_total": 0, "nofb_self_coll": 0}
    for r in rows:
        if r["mode"] == "fallback":
            totals["fb_total"] += 1
            if fbool(r["self_collided"]): totals["fb_self_coll"] += 1
        else:
            totals["nofb_total"] += 1
            if fbool(r["self_collided"]): totals["nofb_self_coll"] += 1
    return {"per_cell": serial, "totals": totals}


# ---------------------------------------------------------------------------
# 4. Epsilon-margin sweep (proposal_mismatch.csv)
# ---------------------------------------------------------------------------
def eps_sweep():
    rows = load("proposal_mismatch.csv")
    bins = defaultdict(lambda: {"n": 0, "self_coll": 0,
                                 "final_dists": [], "min_self": [],
                                 "qd_over": [], "soft_pcts": []})
    for r in rows:
        key = (fnum(r["pct"]), fnum(r["eps"]))
        b = bins[key]
        b["n"] += 1
        if fbool(r["self_collided"]): b["self_coll"] += 1
        b["final_dists"].append(fnum(r["final_target_dist"]))
        b["min_self"].append(fnum(r["min_self_dist"]))
        b["qd_over"].append(fnum(r["max_qd_violation"]))
        b["soft_pcts"].append(fnum(r["soft_pct"]))
    serial = []
    for (pct, eps), b in sorted(bins.items()):
        serial.append({
            "pct": pct, "eps": eps, "n": b["n"],
            "self_coll": b["self_coll"],
            "final_dist_mean": statistics.mean(b["final_dists"]),
            "final_dist_max":  max(b["final_dists"]),
            "min_self_dist_min": min(b["min_self"]),
            "qd_over_mean": statistics.mean(b["qd_over"]),
            "soft_pct_mean": statistics.mean(b["soft_pcts"]),
        })
    return serial


# ---------------------------------------------------------------------------
# 5. Probe scenarios (probe_summary.csv)
# ---------------------------------------------------------------------------
def probes():
    rows = load("probe_summary.csv")
    return [{
        "label": r["label"],
        "ok": fbool(r["ok"]),
        "gamma_min": fnum(r["gamma_min"]),
        "gamma_active_frac": fnum(r["gamma_active_frac"]),
        "sc_dist_min_m": fnum(r["sc_dist_min"]),
        "qd_max_abs": fnum(r["qd_max_abs"]),
        "qd_headroom_pct": fnum(r["qd_headroom_pct"]),
        "self_collided": fbool(r["self_collided"]),
        "final_d_m": fnum(r["final_d"]),
        "soft_frac": fnum(r["soft_frac"]),
    } for r in rows]


# ---------------------------------------------------------------------------
# 6. Cross-scenario fallback robustness (fallback_robustness.csv)
# ---------------------------------------------------------------------------
def fallback_cross():
    rows = load("fallback_robustness.csv")
    bins = defaultdict(lambda: {"n": 0, "self_coll": 0, "final_dists": []})
    for r in rows:
        key = (r["label"], fnum(r["pct"]), r["mode"])
        b = bins[key]
        b["n"] += 1
        if fbool(r["self_collided"]): b["self_coll"] += 1
        b["final_dists"].append(fnum(r["final_dist"]))
    serial = []
    for (label, pct, mode), b in sorted(bins.items()):
        serial.append({
            "label": label, "pct": pct, "mode": mode, "n": b["n"],
            "self_coll": b["self_coll"],
            "final_dist_mean": statistics.mean(b["final_dists"]),
        })
    # totals per-mode
    fb_total = sum(1 for r in rows if r["mode"] == "fallback")
    fb_sc    = sum(1 for r in rows if r["mode"] == "fallback" and fbool(r["self_collided"]))
    nofb_tot = sum(1 for r in rows if r["mode"] == "no_fallback")
    nofb_sc  = sum(1 for r in rows if r["mode"] == "no_fallback" and fbool(r["self_collided"]))
    return {
        "per_cell": serial,
        "totals": {"fb_total": fb_total, "fb_self_coll": fb_sc,
                   "nofb_total": nofb_tot, "nofb_self_coll": nofb_sc},
    }


# ---------------------------------------------------------------------------
def fmt_table_eps(eps_data):
    print("\n--- epsilon-margin sweep (proposal_mismatch.csv) ---")
    print(f"{'pct':>5} {'eps':>5} {'n':>3} {'sc':>2} {'final_mean':>11} "
          f"{'final_max':>10} {'qd_over':>9}")
    for r in eps_data:
        print(f"{r['pct']:>5.1f} {r['eps']:>5.2f} {r['n']:>3} {r['self_coll']:>2} "
              f"{r['final_dist_mean']:>11.4f} {r['final_dist_max']:>10.4f} "
              f"{r['qd_over_mean']:>9.4f}")


def main():
    data = {
        "vpptc_vs_cfc": baseline_vs_vpptc(),
        "fallback_low_perturbation": fallback_low(),
        "fallback_high_perturbation": fallback_high(),
        "epsilon_margin_sweep": eps_sweep(),
        "probe_scenarios": probes(),
        "fallback_cross_scenario": fallback_cross(),
    }
    NUMS.write_text(json.dumps(data, indent=2, default=str))
    print(f"Wrote {NUMS}")
    # Quick human-readable summary
    print("\n=== VPP-TC vs CFC ===")
    print(json.dumps(data["vpptc_vs_cfc"]["totals"], indent=2))
    for label, m in data["vpptc_vs_cfc"]["per_scenario"].items():
        print(f"  {label:>15s}  vpptc safe={not m['vpptc']['self_coll']}, "
              f"final={m['vpptc']['final_d_m']:.4f}m  |  "
              f"cfc safe={not m['cfc']['self_coll']}, "
              f"final={m['cfc']['final_d_m']:.4f}m")
    print("\n=== Fallback low (0-20%) ===")
    print(json.dumps(data["fallback_low_perturbation"]["totals"], indent=2))
    print("\n=== Fallback HIGH (20-50%) ===")
    print(json.dumps(data["fallback_high_perturbation"]["totals"], indent=2))
    fmt_table_eps(data["epsilon_margin_sweep"])
    print("\n=== Cross-scenario fallback (4 scenarios) ===")
    print(json.dumps(data["fallback_cross_scenario"]["totals"], indent=2))


if __name__ == "__main__":
    main()
