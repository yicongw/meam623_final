#!/usr/bin/env python3
"""Hand-draw 2D demonstrations and fit a stable LPV-DS.

Usage
-----
    python scripts/draw_lpvds.py --output assets/ds_models/my_demo.npz
    python scripts/draw_lpvds.py --plane xz --xlim -0.5 0.7 --ylim 0.0 1.0

Workflow
--------
    1.  A matplotlib window opens.  Click-and-drag to draw one stroke
        (one demonstration).  Release the mouse to end the stroke.
    2.  Repeat to add more demonstrations -- they should all converge to
        roughly the same end-point (the future LPV-DS attractor).
    3.  Press 'f' to fit, 'c' to clear, 'q' (or close window) to save & quit.
    4.  After fitting, the learned vector field is overlaid; you can keep
        drawing more demos and re-fit, or quit to save.

Saved keys (.npz):
    Priors (K,), Mu (D,K), Sigma (D,D,K), A (D,D,K), b (D,K), attractor (D,),
    plane ('xy'|'xz'|'yz'), origin (3,), R (3,3), demos_X (D,N), demos_V (D,N).
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List

import matplotlib.pyplot as plt
import numpy as np

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.join(_SCRIPT_DIR, os.pardir)
sys.path.insert(0, os.path.abspath(_PROJECT_ROOT))

from vpptc.lpvds_fit import fit_lpvds, positions_to_demos
from vpptc.planners import LPVDS


_PLANE_AXES = {"xy": (0, 1, 2), "xz": (0, 2, 1), "yz": (1, 2, 0)}


def plane_to_R_origin(plane: str, fixed: float, x_offset: float = 0.0) -> tuple:
    """Build a 3x3 frame R and origin so that 2D drawn coords map to 3D as
        x_3D = origin + R[:, :2] @ x_2D
    The third column of R is the out-of-plane axis (set to ``fixed`` offset)."""
    i1, i2, i3 = _PLANE_AXES[plane]
    R = np.zeros((3, 3))
    R[i1, 0] = 1
    R[i2, 1] = 1
    R[i3, 2] = 1
    origin = np.zeros(3)
    origin[i3] = fixed
    origin[0] += x_offset
    return R, origin


def get_args():
    ap = argparse.ArgumentParser(description="Hand-draw demos and fit LPV-DS")
    ap.add_argument("--output", type=str,
                    default=os.path.join(_PROJECT_ROOT, "assets", "ds_models",
                                         "drawn_demo.npz"))
    ap.add_argument("--plane", type=str, default="xz",
                    choices=["xy", "xz", "yz"],
                    help="Robot-frame plane the 2D drawing lives in")
    ap.add_argument("--fixed", type=float, default=0.0,
                    help="Out-of-plane axis offset in robot frame [m]")
    ap.add_argument("--xlim", type=float, nargs=2, default=[-0.6, 0.7],
                    help="X-axis range of the drawing canvas [m]")
    ap.add_argument("--ylim", type=float, nargs=2, default=[0.0, 1.1],
                    help="Y-axis range of the drawing canvas [m]")
    ap.add_argument("--dt", type=float, default=0.02,
                    help="Sampling period for velocity estimation [s]")
    ap.add_argument("--kmin", type=int, default=2)
    ap.add_argument("--kmax", type=int, default=6)
    ap.add_argument("--eps-hurwitz", type=float, default=0.5)
    return ap.parse_args()


class Drawer:
    def __init__(self, args):
        self.args = args
        self.curves: List[List[List[float]]] = []
        self.current: List[List[float]] = []
        self.is_drawing = False
        self.fitted_lpvds = None

        self.fig, self.ax = plt.subplots(figsize=(8, 8))
        self.ax.set_xlim(*args.xlim)
        self.ax.set_ylim(*args.ylim)
        self.ax.set_aspect("equal")
        self.ax.grid(True, alpha=0.3)
        self.ax.set_xlabel(f"{args.plane[0]} (robot frame) [m]")
        self.ax.set_ylabel(f"{args.plane[1]} (robot frame) [m]")
        self.title()

        self.fig.canvas.mpl_connect("button_press_event", self.on_press)
        self.fig.canvas.mpl_connect("motion_notify_event", self.on_move)
        self.fig.canvas.mpl_connect("button_release_event", self.on_release)
        self.fig.canvas.mpl_connect("key_press_event", self.on_key)

    def title(self):
        n = len(self.curves)
        msg = (f"Demos: {n}   "
               f"Drag = draw   |   f = fit   |   c = clear   |   q = save & quit")
        if self.fitted_lpvds is not None:
            msg += "   (vector field overlay shown)"
        self.ax.set_title(msg)

    def redraw(self):
        self.ax.cla()
        self.ax.set_xlim(*self.args.xlim)
        self.ax.set_ylim(*self.args.ylim)
        self.ax.set_aspect("equal")
        self.ax.grid(True, alpha=0.3)
        self.ax.set_xlabel(f"{self.args.plane[0]} (robot frame) [m]")
        self.ax.set_ylabel(f"{self.args.plane[1]} (robot frame) [m]")

        if self.fitted_lpvds is not None:
            xs = np.linspace(*self.args.xlim, 25)
            ys = np.linspace(*self.args.ylim, 25)
            XX, YY = np.meshgrid(xs, ys)
            UU = np.zeros_like(XX)
            VV = np.zeros_like(YY)
            for i in range(XX.shape[0]):
                for j in range(XX.shape[1]):
                    v = self.fitted_lpvds(np.array([XX[i, j], YY[i, j]]))
                    UU[i, j], VV[i, j] = v
            self.ax.streamplot(XX, YY, UU, VV, density=1.4, color="gray",
                               linewidth=0.7, arrowsize=0.8)
            att = self.fitted_lpvds.attractor
            if att is None:
                att = -np.linalg.solve(self.fitted_lpvds.A.sum(axis=2),
                                       self.fitted_lpvds.b.sum(axis=1))
            self.ax.plot(att[0], att[1], marker="*", color="red",
                         markersize=18, label="attractor")
            self.ax.legend(loc="upper right")

        for c in self.curves:
            arr = np.asarray(c)
            self.ax.plot(arr[:, 0], arr[:, 1], "-", color="C0", alpha=0.8, lw=1.5)
            self.ax.plot(arr[0, 0], arr[0, 1], "o", color="C0", ms=6)
            self.ax.plot(arr[-1, 0], arr[-1, 1], "s", color="C3", ms=8)

        if self.is_drawing and self.current:
            arr = np.asarray(self.current)
            self.ax.plot(arr[:, 0], arr[:, 1], "-", color="C1", lw=1.0)

        self.title()
        self.fig.canvas.draw_idle()

    # ---- mouse ----
    def on_press(self, ev):
        if ev.inaxes != self.ax or ev.button != 1:
            return
        self.is_drawing = True
        self.current = [[ev.xdata, ev.ydata]]

    def on_move(self, ev):
        if not self.is_drawing or ev.inaxes != self.ax:
            return
        self.current.append([ev.xdata, ev.ydata])
        self.redraw()

    def on_release(self, ev):
        if not self.is_drawing:
            return
        self.is_drawing = False
        if len(self.current) >= 5:
            self.curves.append(self.current)
            print(f"[draw] demo {len(self.curves)} captured ({len(self.current)} pts)")
        else:
            print("[draw] stroke too short, discarded")
        self.current = []
        self.redraw()

    # ---- keyboard ----
    def on_key(self, ev):
        if ev.key == "c":
            self.curves = []
            self.fitted_lpvds = None
            print("[draw] cleared")
            self.redraw()
        elif ev.key == "f":
            self.fit()
        elif ev.key == "q":
            plt.close(self.fig)

    def fit(self):
        if len(self.curves) == 0:
            print("[fit] no demos yet")
            return
        X, V, att, _ = positions_to_demos(self.curves, dt=self.args.dt)
        params = fit_lpvds(X, V, att,
                           k_min=self.args.kmin, k_max=self.args.kmax,
                           eps_hurwitz=self.args.eps_hurwitz)
        self.fitted_lpvds = LPVDS(**params)
        print(f"[fit] OK   K={params['Priors'].size}   att={att.round(3)}")
        self.redraw()

    def save(self):
        if not self.curves:
            print("[save] no demos drawn -- nothing to save")
            return
        if self.fitted_lpvds is None:
            print("[save] auto-fitting before save...")
            self.fit()
        if self.fitted_lpvds is None:
            print("[save] fit failed -- nothing saved")
            return
        X, V, att, _ = positions_to_demos(self.curves, dt=self.args.dt)
        R, origin = plane_to_R_origin(self.args.plane, self.args.fixed)
        out = self.args.output
        os.makedirs(os.path.dirname(out), exist_ok=True)
        np.savez(
            out,
            Priors=self.fitted_lpvds.Priors,
            Mu=self.fitted_lpvds.Mu,
            Sigma=self.fitted_lpvds.Sigma,
            A=self.fitted_lpvds.A,
            b=self.fitted_lpvds.b,
            attractor=self.fitted_lpvds.attractor if self.fitted_lpvds.attractor is not None else att,
            plane=np.array(self.args.plane),
            R=R,
            origin=origin,
            demos_X=X,
            demos_V=V,
        )
        print(f"[save] -> {out}")


def main():
    args = get_args()
    drawer = Drawer(args)
    plt.show()
    drawer.save()


if __name__ == "__main__":
    main()
