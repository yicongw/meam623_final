"""Cartesian-velocity DS motion planners used by the VPP-TC controller.

All planners expose the same interface:

    v_des = planner(x)          # x: (D,) position, v_des: (D,) velocity

So they are drop-in replacements for the linear potential field
``fx = -k * (end_pos - target_pos)`` used in scripts/simulate.py.
"""

from __future__ import annotations

import pickle
from typing import Optional

import numpy as np


# ---------------------------------------------------------------------------
# Baseline: linear attractor DS (the original VPP-TC planner)
# ---------------------------------------------------------------------------

class LinearDS:
    """v(x) = -k * (x - x*)."""

    def __init__(self, target: np.ndarray, gain: float = 50.0):
        self.target = np.asarray(target, dtype=np.float64)
        self.gain = float(gain)

    def __call__(self, x: np.ndarray) -> np.ndarray:
        return -self.gain * (np.asarray(x, dtype=np.float64) - self.target)


# ---------------------------------------------------------------------------
# LPV-DS (Figueroa & Billard, CoRL 2018)
# ---------------------------------------------------------------------------

class LPVDS:
    """Linear Parameter-Varying DS with a PC-GMM mixing function.

        f(x) = Σ_k γ_k(x) [ A_k (x - x*) ]                     (default, b absorbed)
        f(x) = Σ_k γ_k(x) [ A_k x + b_k ]                      (if ``b`` provided)
        γ_k(x) = π_k N(x | μ_k, Σ_k) / Σ_j π_j N(x | μ_j, Σ_j)

    Parameters
    ----------
    Priors : (K,)            GMM mixing weights π_k
    Mu     : (D, K)          GMM means μ_k
    Sigma  : (D, D, K)       GMM covariances Σ_k
    A      : (D, D, K)       linear sub-DS matrices A_k (must be Hurwitz)
    attractor : (D,)         equilibrium x* (used when ``b`` is None)
    b      : (D, K), optional  bias vectors b_k (alt parameterisation)
    v_max  : float, optional   if set, output speed is clamped to this value

    Notes
    -----
    The arrays follow the convention used in Nadia Figueroa's Python/MATLAB
    ``ds-opt`` reference implementation. If your training pipeline uses a
    different shape (e.g. (K, D) means), transpose before passing in.
    """

    def __init__(
        self,
        Priors: np.ndarray,
        Mu: np.ndarray,
        Sigma: np.ndarray,
        A: np.ndarray,
        attractor: Optional[np.ndarray] = None,
        b: Optional[np.ndarray] = None,
        v_max: Optional[float] = None,
        gain: float = 1.0,
    ):
        self.Priors = np.asarray(Priors, dtype=np.float64).reshape(-1)
        self.Mu = np.asarray(Mu, dtype=np.float64)
        self.Sigma = np.asarray(Sigma, dtype=np.float64)
        self.A = np.asarray(A, dtype=np.float64)
        self.b = None if b is None else np.asarray(b, dtype=np.float64)
        self.attractor = (None if attractor is None
                          else np.asarray(attractor, dtype=np.float64))
        self.v_max = v_max
        self.gain = float(gain)

        D, K = self.Mu.shape
        assert self.Sigma.shape == (D, D, K), f"Sigma shape {self.Sigma.shape} != ({D},{D},{K})"
        assert self.A.shape == (D, D, K), f"A shape {self.A.shape} != ({D},{D},{K})"
        assert self.Priors.shape == (K,)
        if self.b is not None:
            assert self.b.shape == (D, K)
        else:
            assert self.attractor is not None and self.attractor.shape == (D,)

        # Pre-compute Cholesky factors for fast Gaussian eval
        self._chol = np.empty_like(self.Sigma)
        self._log_norm = np.empty(K)
        for k in range(K):
            L = np.linalg.cholesky(self.Sigma[:, :, k])
            self._chol[:, :, k] = L
            self._log_norm[k] = (-0.5 * D * np.log(2 * np.pi)
                                 - np.log(np.diag(L)).sum())

    # ---------------- mixing function ----------------
    def _gamma(self, x: np.ndarray) -> np.ndarray:
        K = self.Priors.size
        log_p = np.empty(K)
        for k in range(K):
            diff = x - self.Mu[:, k]
            y = np.linalg.solve(self._chol[:, :, k], diff)
            log_p[k] = self._log_norm[k] - 0.5 * y @ y
        log_w = np.log(self.Priors + 1e-300) + log_p
        log_w -= log_w.max()
        w = np.exp(log_w)
        return w / w.sum()

    # ---------------- velocity field ----------------
    def __call__(self, x: np.ndarray) -> np.ndarray:
        x = np.asarray(x, dtype=np.float64)
        gamma = self._gamma(x)
        if self.b is not None:
            v = sum(gamma[k] * (self.A[:, :, k] @ x + self.b[:, k])
                    for k in range(gamma.size))
        else:
            xe = x - self.attractor
            v = sum(gamma[k] * (self.A[:, :, k] @ xe)
                    for k in range(gamma.size))
        v = self.gain * v
        if self.v_max is not None:
            speed = np.linalg.norm(v)
            if speed > self.v_max:
                v *= self.v_max / speed
        return v

    # ---------------- shift attractor to a new target ----------------
    def translate(self, new_attractor: np.ndarray) -> "LPVDS":
        """Return a copy whose equilibrium is at ``new_attractor``.

        Both the GMM means ``Mu`` and (if present) the bias vectors ``b_k``
        are shifted by ``Δ = new_attractor − old_attractor`` so the velocity
        field has the same shape but a translated fixed point.
        """
        old_att = (self.attractor if self.attractor is not None
                   else -np.linalg.solve(self.A.sum(axis=2),
                                         self.b.sum(axis=1)))
        delta = np.asarray(new_attractor, dtype=np.float64) - old_att
        Mu_new = self.Mu + delta[:, None]
        if self.b is not None:
            # f_new(x) = Σ β_new(x) (A_k x + b_k_new); β shifts with Mu so β_new(x)=β_old(x-δ)
            # Want f_new(att_new) = 0  ⇒  b_k_new = b_k - A_k δ
            b_new = self.b - np.einsum("ijk,j->ik", self.A, delta)
            return LPVDS(self.Priors, Mu_new, self.Sigma, self.A,
                         attractor=None, b=b_new,
                         v_max=self.v_max, gain=self.gain)
        return LPVDS(self.Priors, Mu_new, self.Sigma, self.A,
                     attractor=np.asarray(new_attractor, dtype=np.float64),
                     b=None, v_max=self.v_max, gain=self.gain)

    # ---------------- I/O helper ----------------
    @classmethod
    def from_npz(cls, path: str, **overrides) -> "LPVDS":
        """Load from an ``.npz`` with keys matching the constructor."""
        d = dict(np.load(path, allow_pickle=False))
        # numpy treats scalar attractor/v_max specially
        if "v_max" in d and d["v_max"].shape == ():
            d["v_max"] = float(d["v_max"])
        if "gain" in d and d["gain"].shape == ():
            d["gain"] = float(d["gain"])
        d.update(overrides)
        return cls(**d)

    @classmethod
    def from_pickle(cls, path: str, **overrides) -> "LPVDS":
        """Load from a pickle dict with keys matching the constructor."""
        with open(path, "rb") as f:
            d = pickle.load(f)
        d.update(overrides)
        return cls(**d)

    @classmethod
    def from_mat(cls, path: str, **overrides) -> "LPVDS":
        """Load a model saved by ``save_lpvDS_to_Mat.m`` (Figueroa ds-opt).

        Expected struct fields: ``ds_gmm.{Priors, Mu, Sigma}``, ``A_k``,
        ``b_k`` (optional), ``att``.
        """
        from scipy.io import loadmat
        m = loadmat(path, squeeze_me=False, struct_as_record=False)
        g = m["ds_gmm"][0, 0]
        d = dict(
            Priors=np.asarray(g.Priors).reshape(-1),
            Mu=np.asarray(g.Mu),
            Sigma=np.asarray(g.Sigma),
            A=np.asarray(m["A_k"]),
            attractor=np.asarray(m["att"]).reshape(-1),
        )
        if "b_k" in m and m["b_k"].size > 0:
            d["b"] = np.asarray(m["b_k"])
        d.update(overrides)
        return cls(**d)

    @classmethod
    def from_yaml(cls, path: str, **overrides) -> "LPVDS":
        """Load a model saved by ``save_lpvDS_to_Yaml.m``.

        YAML stores all matrices as MATLAB column-major flattened vectors;
        we reshape with ``order='F'`` to recover the original arrays.
        """
        import yaml
        with open(path, "r") as f:
            d_raw = yaml.safe_load(f)
        K, D = int(d_raw["K"]), int(d_raw["M"])
        d = dict(
            Priors=np.asarray(d_raw["Priors"], dtype=float).reshape(-1),
            Mu=np.asarray(d_raw["Mu"], dtype=float).reshape((D, K), order="F"),
            Sigma=np.asarray(d_raw["Sigma"], dtype=float).reshape((D, D, K), order="F"),
            A=np.asarray(d_raw["A"], dtype=float).reshape((D, D, K), order="F"),
            attractor=np.asarray(d_raw["attractor"], dtype=float).reshape(-1),
        )
        d.update(overrides)
        return cls(**d)


# ---------------------------------------------------------------------------
# 2D-to-3D wrapper: LASA was trained in 2D, robot lives in 3D
# ---------------------------------------------------------------------------

class PlanarLift:
    """Run a 2D planner on a plane embedded in 3D workspace.

    The 3D position is decomposed as
        x_3D = origin + R @ [x_2D[0], x_2D[1], h]
    where ``R`` is an orthonormal frame and ``h`` is the signed normal offset.
    The 2D planner produces a 2D velocity which is lifted back to 3D via R[:, :2],
    plus a normal restoring term -k_perp * h * R[:, 2].
    """

    def __init__(self, planner_2d, origin: np.ndarray, R: np.ndarray,
                 k_perp: float = 5.0):
        self.planner = planner_2d
        self.origin = np.asarray(origin, dtype=np.float64)
        self.R = np.asarray(R, dtype=np.float64)
        assert self.R.shape == (3, 3)
        self.k_perp = float(k_perp)

    def __call__(self, x3: np.ndarray) -> np.ndarray:
        local = self.R.T @ (np.asarray(x3, dtype=np.float64) - self.origin)
        x2 = local[:2]
        h = local[2]
        v2 = self.planner(x2)
        v3 = self.R[:, :2] @ v2 - self.k_perp * h * self.R[:, 2]
        return v3
