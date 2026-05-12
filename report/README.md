# MEAM 6230 Final Report

LaTeX source for the final report. Single-file `final_report.tex` using
the IEEEtran conference template.

## How to compile

### Option 1: Overleaf (recommended, no install needed)

1. Go to https://www.overleaf.com → New Project → Upload Project
2. Create a zip with:
   - `final_report.tex`
   - `figures/fig_poster_col2_timeseries.png`
   - `figures/fig_poster_col3_lpvds_only.png`
3. Inside `final_report.tex`, change the two `\includegraphics` paths
   from `../output/fig_poster_col2_timeseries.png` → `figures/fig_poster_col2_timeseries.png`
   (same for col3).
4. Set the compiler to **pdfLaTeX** (Menu → Settings) and hit Recompile.

### Option 2: Local (MiKTeX/TeX Live)

```powershell
cd C:\meam623_finalproj\report
pdflatex final_report.tex
pdflatex final_report.tex   # second pass for refs
```

The two `\includegraphics` paths assume the figures live at
`C:\meam623_finalproj\output\fig_poster_col2_timeseries.png` and
`...\fig_poster_col3_lpvds_only.png`, which they already do.

## Page-count check

Aim: **8 pages** of body text (refs not counted).
Current draft is ~7-7.5 pages. If it overflows by a hair, the easiest
shrink is to:

- Combine subsections V.A "Setup and metrics" into V.B as a paragraph.
- Drop the explicit reproduction commands from Section VI
  (move to README on GitHub instead).
- Use `\IEEEtriggeratref{6}` to start a 2-column reference list mid-page.

## Things you must edit before submitting

1. **GitHub URL** in Section VI (`<your-username>` placeholder).
2. **Figure 3 (Section V.E)**: currently described as "conceptual sketch -- 
   full grid still running". If you actually run the unified-validation
   sweep before the deadline, drop in the real plot; if not, either
   (a) add a `\todo` placeholder figure or (b) trim Section V.E to
   2-3 sentences and move to Future Work.
3. **Repository link** at the bottom of Section VI.
4. **Acknowledgments**: confirm Nadia is OK with being acknowledged for
   the suggestion (she said it openly at the poster session, so this
   should be fine).

## Companion submissions

- **Individual report**: 5 pts, separate file. For solo project, write
  one paragraph self-evaluation: "I performed all of the proposal,
  implementation, experimentation, and writing. I assign myself 5/5."
- **GitHub repo**: must be linked in the PDF and submitted alongside.
  Make sure the README in the repo root explains how to reproduce each
  figure.

## Section ↔ rubric mapping

| Rubric item                | Pts | Section           |
|----------------------------|-----|-------------------|
| Motivation                 | 2.5 | I (Introduction)  |
| Goal                       | 2.5 | I  (Contributions list) |
| Method/Approach            | 25  | III + IV          |
| Evaluation                 | 15  | V                 |
| Implementation Details     | 7.5 | VI                |
| Conclusions/Lessons        | 2.5 | VII + VIII        |
| **Total**                  | 55  |                   |
