"""Lightweight LPV-DS fitting from demonstration data.

Pipeline (per Figueroa & Billard 2018, simplified):
    1. Fit a GMM on positions x_n via sklearn (BIC-selected K within range).
    2. For each component k, solve a weighted least-squares for A_k:
           A_k* = argmin Σ_n w_kn ‖A_k (x_n − att) − v_n‖²
       where w_kn is the responsibility γ_k(x_n).
    3. Project A_k onto the Hurwitz cone with a fixed-P=I Lyapunov margin:
           sym(A_k) ← clip eigenvalues to ≤ −ε, leaving the skew part intact.
    4. Set b_k = −A_k att so the equilibrium is exactly at *att*.

This omits the SDP from the original ds-opt (which jointly enforces a learned
Lyapunov function), but the per-component eigenvalue projection guarantees
each local DS is contractive, so the convex combination is also stable.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np
from sklearn.mixture import GaussianMixture


# ---------------------------------------------------------------------------

def _fit_gmm(X: np.ndarray, k_min: int = 2, k_max: int = 8,
             reg_cov: float = 1e-6, seed: int = 0) -> GaussianMixture:
    """BIC-selected GMM in [k_min, k_max]."""
    best_bic = np.inf
    best = None
    for k in range(k_min, k_max + 1):
        try:
            g = GaussianMixture(
                n_components=k, covariance_type="full",
                reg_covar=reg_cov, max_iter=300,
                n_init=3, random_state=seed,
            ).fit(X)
            bic = g.bic(X)
            if bic < best_bic:
                best_bic, best = bic, g
        except Exception:
            continue
    if best is None:
        raise RuntimeError("GMM fitting failed for all K")
    return best


def _project_hurwitz(A: np.ndarray, eps: float = 0.5) -> np.ndarray:
    """Clip the symmetric part of A so all eigenvalues of sym(A) ≤ −eps."""
    S = 0.5 * (A + A.T)
    K = 0.5 * (A - A.T)
    w, V = np.linalg.eigh(S)
    w = np.minimum(w, -eps)
    S_proj = V @ np.diag(w) @ V.T
    return S_proj + K


# ---------------------------------------------------------------------------

def fit_lpvds(
    X: np.ndarray,
    V: np.ndarray,
    attractor: np.ndarray,
    k_min: int = 2,
    k_max: int = 8,
    eps_hurwitz: float = 0.5,
    seed: int = 0,
) -> dict:
    """Fit a stable LPV-DS from demonstrations.

    Parameters
    ----------
    X : (D, N) positions
    V : (D, N) velocities
    attractor : (D,) common equilibrium of all demos
    k_min, k_max : GMM K search range
    eps_hurwitz : Lyapunov margin (smaller = less conservative)

    Returns
    -------
    dict with keys (Priors, Mu, Sigma, A, b, attractor) ready for
    ``LPVDS(**dict)``.
    """
    X = np.asarray(X, dtype=np.float64)
    V = np.asarray(V, dtype=np.float64)
    attractor = np.asarray(attractor, dtype=np.float64).reshape(-1)
    D, N = X.shape
    assert V.shape == X.shape
    assert attractor.shape == (D,)

    # ----- 1) GMM on positions -----
    gmm = _fit_gmm(X.T, k_min=k_min, k_max=k_max, seed=seed)
    K = gmm.n_components
    Priors = gmm.weights_                       # (K,)
    Mu = gmm.means_.T                           # (D, K)
    Sigma = np.transpose(gmm.covariances_, (1, 2, 0))  # (D, D, K)

    resp = gmm.predict_proba(X.T)               # (N, K)

    # ----- 2) Weighted LS for each A_k -----
    A = np.zeros((D, D, K))
    Xe = X - attractor[:, None]                 # (D, N)
    for k in range(K):
        w = resp[:, k] + 1e-8                   # (N,)
        Wsqrt = np.sqrt(w)
        # Solve  A_k Xe = V  in weighted LS sense:  V W = A_k (Xe W)
        Xw = Xe * Wsqrt[None, :]                # (D, N)
        Vw = V * Wsqrt[None, :]                 # (D, N)
        # A_k = Vw Xw^T (Xw Xw^T + λI)^-1
        XXt = Xw @ Xw.T + 1e-6 * np.eye(D)
        A[:, :, k] = Vw @ Xw.T @ np.linalg.inv(XXt)

    # ----- 3) Hurwitz projection -----
    for k in range(K):
        A[:, :, k] = _project_hurwitz(A[:, :, k], eps=eps_hurwitz)

    # ----- 4) Bias so equilibrium == attractor -----
    b = -np.einsum("ijk,j->ik", A, attractor)   # (D, K)

    return dict(
        Priors=Priors, Mu=Mu, Sigma=Sigma, A=A, b=b, attractor=attractor,
    )


# ---------------------------------------------------------------------------

def positions_to_demos(curves, dt: float = 0.01,
                       smooth_window: int = 5) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Convert a list of (Ti, D) hand-drawn position curves into (X, V, att, x0_all).

    - Estimates velocity via central differences with optional moving-average smoothing.
    - Common attractor = mean of last 5 samples across all curves.
    - x0_all = first sample of each curve, shape (D, M).
    """
    cleaned = []
    for c in curves:
        c = np.asarray(c, dtype=np.float64)
        if c.shape[0] < 5:
            continue
        if smooth_window > 1:
            kern = np.ones(smooth_window) / smooth_window
            c = np.stack([np.convolve(c[:, d], kern, mode="same")
                          for d in range(c.shape[1])], axis=1)
        cleaned.append(c)
    if not cleaned:
        raise ValueError("No usable demos (each must have >= 5 points)")

    Xs, Vs, x0s = [], [], []
    for c in cleaned:
        x = c.T                                  # (D, T)
        v = np.gradient(x, dt, axis=1)           # (D, T)
        # drop the last sample to ensure attractor neighbourhood has small v
        Xs.append(x)
        Vs.append(v)
        x0s.append(x[:, 0])

    X = np.concatenate(Xs, axis=1)
    V = np.concatenate(Vs, axis=1)
    x0_all = np.stack(x0s, axis=1)
    att = np.mean(np.concatenate([x[:, -5:] for x in Xs], axis=1), axis=1)
    return X, V, att, x0_all
