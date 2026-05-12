# MEAM 6230 Final Project — VPP-TC Extensions

**Author:** Yicong Wang (`yicongw@seas.upenn.edu`)
**Course:** MEAM 6230 — Topics in Robotics (Spring 2026), Prof. Nadia Figueroa
**Base codebase:** [zhang-zizhe/VPP-TC](https://github.com/zhang-zizhe/VPP-TC)

---

## What this repo contains

This is the working repository for my MEAM 6230 final project, which extends Viability-Preserving Passive Torque Control (VPP-TC) along three axes:

- **(C1)** Planner-agnostic interface; ports the same controller (no re-tuning) from single-arm Panda → dual-arm Panda → dual-arm OpenArm humanoid.
- **(C2)** ε-margin tightening of the viability acceleration bounds under bounded inertial mismatch `‖ΔM·M⁻¹‖ ≤ δ`, with an honest negative-result ablation showing why a *constant* ε is insufficient.
- **(C3)** A unified safety + practical-ISS-convergence theorem (Theorem 1 in the report) that holds whenever the upstream planner is a Hurwitz-projected LPV-DS.

**The full report is `report/final_report.tex`.** Compile with `pdflatex` (twice for refs).

---

## Repository layout

```
meam623_final/
├── README.md, LICENSE, requirements.txt, setup.py
│
├── report/
│   ├── final_report.tex      # The 8-page IEEEtran final report
│   └── README.md             # Notes on report regeneration
│
├── docs/
│   ├── prob.pdf              # Project proposal
│   └── theory.pdf            # Background derivations (VPP-TC viability bounds)
│
├── vpptc/                    # Core Python library
│   ├── model.py              # TransformerGamma self-collision predictor
│   ├── safety.py             # Algorithm 1/2/3: viability acc bounds + Γ-CBF
│   ├── safety_openarm.py     # OpenArm-specific safety layer
│   ├── sdf.py                # External-collision SDF (RDF wrapper)
│   ├── robot.py              # Single-arm Panda PyBullet wrapper
│   ├── robot_openarm.py      # Dual-arm OpenArm PyBullet wrapper
│   ├── planners.py           # LPV-DS planner interface (replaces linear DS)
│   ├── lpvds_fit.py          # Hand-drawn 2D demos → Hurwitz-projected LPV-DS
│   ├── utils.py / utils_openarm.py
│   └── blacklist_openarm.py  # Permanent-overlap link pairs to ignore
│
├── scripts/                  # Drivers, sweeps, analyzers, plotters
│   ├── simulate.py                       # Single Panda + obstacle (linear DS)
│   ├── simulate_dual.py                  # Dual Panda (Hopf-oscillator DS)
│   ├── simulate_dual_openarm.py          # Dual OpenArm (Hopf-oscillator DS)
│   │
│   ├── compare_vpptc_cfc.py              # V-B head-to-head baseline
│   ├── probe_scenarios.py                # V-F automatic scenario probing
│   ├── sweep_proposal_mismatch.py        # V-C low-regime sweep (30 cells)
│   ├── sweep_high_uncertainty.py         # V-C high-regime sweep (96 cells)
│   ├── explore_eps_helpful.py            # V-C ε-margin ablation (24 cells)
│   ├── search_edge_scenario.py
│   ├── search_overshoot_scenario.py
│   │
│   ├── train.py / train_dual.py / train_dual_openarm.py   # TransformerGamma training
│   ├── sample.py / sample_dual.py / sample_dual_openarm.py # Training-set generation
│   ├── draw_lpvds.py                     # GUI to draw LPV-DS demos
│   │
│   ├── report_experiments.py             # Driver: re-run the four sweeps end-to-end
│   ├── report_analyze.py                 # Driver: aggregate stats from existing CSVs
│   ├── report_finalize.py                # Driver: refresh dual-arm rows + figures
│   ├── report_fill_placeholders.py       # Substitute <<...>> in final_report.tex
│   ├── plot_unified_validation.py        # Fig. 4 (unified LPV-DS × mass mismatch)
│   ├── plot_poster_col2_timeseries.py    # Fig. 2 (storage / Γ / fallback time series)
│   ├── poster_fig3.py                    # Fig. 3 (LPV-DS workspace + vector field)
│   └── plot_run.py / plot_openarm.py     # Generic per-run plotters
│
├── assets/
│   ├── urdf/panda/                       # Single + dual Panda URDFs (committed)
│   ├── urdf/plane/                       # Ground plane URDF
│   ├── urdf/openarm_description/         # NOT committed (~120 MB) — see Setup below
│   ├── ds_models/                        # Hand-drawn LPV-DS pickle (K=6 components)
│   └── models/
│       ├── transformer_gamma.pt              # Single-arm Panda Γ predictor weights
│       ├── transformer_gamma_dual.pt         # Dual-arm Panda Γ
│       └── transformer_gamma_dual_openarm.pt # Dual-arm OpenArm Γ
│
└── output/                               # All cached experiment results
    ├── report_results.json               # Aggregated stats consumed by the report
    ├── report_numbers.json               # Stats from existing-CSV runs
    ├── fig_unified_validation.png        # Figure 4 in report
    ├── fig_poster_col2_timeseries.png    # Figure 2 in report
    └── fig_poster_col3_lpvds_only.png    # Figure 3 in report
```

Per-run CSVs (~400 files, ~400 MB) are *not* committed; only the aggregated JSON
summaries that the report and figures actually consume. To regenerate every CSV
from scratch, see [Reproducing the experiments](#reproducing-the-experiments)
below.

---

## Setup

```bash
# 1. Clone
git clone https://github.com/yicongw/meam623_final.git
cd meam623_final

# 2. Python env
python -m venv venv
venv\Scripts\activate         # (Linux/macOS: source venv/bin/activate)
pip install -r requirements.txt
pip install -e .

# 3. (Required for dual-OpenArm experiments only) fetch upstream URDFs:
git clone https://github.com/enactic/openarm_description.git \
    assets/urdf/openarm_description

# 4. (Required for external-obstacle SDF only) fetch RDF library:
git clone https://github.com/Yimingli94/RDF.git third_party/rdf
```

Tested with Python 3.8.10 on Windows 11 (i7-12700H, no GPU at runtime).
PyBullet, CVXPY+OSQP, PyTorch (CPU), NumPy, Matplotlib are the heavy deps.

---

## Reproducing the experiments

Every figure and table number in `report/final_report.tex` can be regenerated
from the scripts in this repo. Wall-clock estimates are for the i7-12700H above.

| Report section | Driver | Output | Time |
|---|---|---|---|
| Table I (multi-platform porting) | `python scripts/simulate.py --no-gui --tag rep_single` | `output/run_*.csv` | ~10 s |
| | `python scripts/simulate_dual.py --no-gui --tag rep_dual --model-path assets/models/transformer_gamma_dual.pt` | `output/dual_run_*.csv` | ~30 s |
| | `python scripts/simulate_dual_openarm.py --no-gui --tag rep_openarm` | `output/openarm_dual_run_*.csv` | ~60 s |
| Table II (VPP-TC vs CFC baseline) | `python scripts/compare_vpptc_cfc.py` | `output/compare_summary.csv` | ~5 min |
| Table III (ε-margin ablation, 24 cells) | `python scripts/explore_eps_helpful.py` | `output/explore_eps.csv` | ~8 min |
| Table IV (unified LPV-DS × mass-mismatch, 18 cells) | `python scripts/report_experiments.py --skip-existing` | `output/report_results.json` | ~10 min |
| Figure 2 (storage / Γ / fallback time series) | `python scripts/plot_poster_col2_timeseries.py` | `output/fig_poster_col2_timeseries.png` | ~3 s |
| Figure 3 (LPV-DS workspace + vector field) | `python scripts/poster_fig3.py` | `output/fig_poster_col3_lpvds_only.png` | ~5 s |
| Figure 4 (unified validation summary) | `python scripts/plot_unified_validation.py` | `output/fig_unified_validation.png` | ~3 s |
| V-F probing scenarios | `python scripts/probe_scenarios.py` | `output/probe_summary.csv` | ~2 min |

End-to-end driver that runs the full grid and refreshes the report's numbers:

```bash
python scripts/report_experiments.py     # ~30 min total
python scripts/report_finalize.py        # re-runs dual rows + plots Fig 4 +
                                          # fills <<...>> placeholders in .tex
```

---

## Where the three contributions live in the code

### (C1) Planner-agnostic interface and multi-platform porting

- `vpptc/planners.py` — the upstream planner only needs `f(x) → ẋ_des`; the
  safety layer (Γ + acceleration bounds + QP) does not see anything else.
- `vpptc/lpvds_fit.py` — fits a hand-drawn 2D demo to a K=6 mixture of linear
  systems, then projects each `A_k ← ½(A_k + A_kᵀ) − (η + 0.5)·I` until
  eigenvalues are negative (Hurwitz).
- `vpptc/robot_openarm.py` + `vpptc/safety_openarm.py` — same VPP-TC pipeline
  on the 14-DoF OpenArm; the only platform-specific input is the URDF and one
  re-trained TransformerGamma weight file.

### (C2) ε-margin under inertial mismatch

- `vpptc/safety.py:compute_joint_acceleration_bounds_vec` — accepts an
  `eps` keyword that tightens both the upper and lower acceleration bound by
  `eps · |q̈_max|` (Equation (5) in the report).
- `scripts/sweep_proposal_mismatch.py`, `scripts/sweep_high_uncertainty.py` —
  perturb each link mass by `1 + Uniform(−p, +p)`, with the controller
  keeping the nominal masses.
- `scripts/explore_eps_helpful.py` — 24-cell ablation of constant ε vs no
  margin (Table III in the report).

### (C3) Unified safety + ISS convergence

- The theorem is stated in `report/final_report.tex` Sec. IV-C (Theorem 1).
- `scripts/report_experiments.py` (and `report_finalize.py`) instantiate the
  theorem empirically: LPV-DS planner + 6 mass-mismatch levels × 3 seeds = 18
  cells, recording the closest end-effector approach to the attractor along
  each rollout.
- `scripts/plot_unified_validation.py` produces Fig. 4 (left: empirical
  practical-convergence ball vs. predicted ISS envelope; right: 100%
  self-collision-free fraction across all 18 cells).

---

## License

MIT (see `LICENSE`). The upstream VPP-TC codebase, the RDF library, the Panda
and OpenArm URDFs, and the IEEEtran LaTeX class retain their original licenses.
