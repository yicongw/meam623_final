#!/usr/bin/env python3
"""VPP-TC: main simulation script.

Runs a Franka Panda robot in PyBullet with viability-preserving torque control.
Both self-collision avoidance (via the TransformerGamma model) and external
collision avoidance (via RDF signed distance fields) are active.

Usage
-----
    python scripts/simulate.py
    python scripts/simulate.py --duration 10 --stepsize 2e-3 --seed 42
"""

import argparse
import math
import os
import sys
import time

import cvxpy as cp
import numpy as np
import pandas as pd
import pybullet as p

# Ensure the project root is on ``sys.path`` so that ``vpptc`` and
# ``third_party`` are importable regardless of where we run from.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.join(_SCRIPT_DIR, os.pardir)
sys.path.insert(0, os.path.abspath(_PROJECT_ROOT))

from vpptc.robot import Panda
from vpptc.safety import (
    compute_gamma_and_grad,
    compute_joint_acceleration_bounds_vec,
)
from vpptc.sdf import query_sdf_batch
from vpptc.utils import compute_min_center_distance, compute_qe
from vpptc.planners import LinearDS, LPVDS, PlanarLift


# ======================================================================
# Argument parsing
# ======================================================================

def get_args():
    parser = argparse.ArgumentParser(
        description="VPP-TC simulation with self- and external collision avoidance",
    )
    # Simulation
    parser.add_argument("--duration", type=float, default=6.0,
                        help="Simulation duration in seconds (default: 6.0)")
    parser.add_argument("--stepsize", type=float, default=2e-3,
                        help="Simulation time step (default: 2e-3)")
    parser.add_argument("--seed", type=int, default=28,
                        help="Random seed (default: 28)")

    # Obstacle
    parser.add_argument("--obstacle-pos", type=float, nargs=3,
                        default=[0.0, -0.4, 0.5],
                        help="Obstacle 1 centre [x y z]")
    parser.add_argument("--obstacle-radius", type=float, default=0.05,
                        help="Obstacle sphere radius (default: 0.05)")

    # Target
    parser.add_argument("--target-pos", type=float, nargs=3,
                        default=[0.0, -0.6, 0.3],
                        help="End-effector target position [x y z]")

    # Safety
    parser.add_argument("--gamma-threshold", type=float, default=2.5,
                        help="Self-collision Gamma threshold (default: 2.5)")
    parser.add_argument("--sdf-react-dist", type=float, default=0.1,
                        help="SDF distance below which reactive evasion activates")

    # Controller
    parser.add_argument("--alpha", type=float, default=1e-2,
                        help="Regularisation weight in the QP (default: 1e-2)")
    # Dynamics mismatch (Part 2)
    parser.add_argument("--qp-mass-scale", type=float, default=1.0,
                        help="Scale factor on M and tau_id seen by the QP, relative "
                             "to the true PyBullet model (1.0 = perfect model, "
                             "1.3 = controller thinks robot is 30%% heavier).")
    # ---- Proposal-aligned mismatch: perturb the SIMULATOR, not the QP ----
    parser.add_argument("--mass-perturb-pct", type=float, default=0.0,
                        help="Percent perturbation applied to each Panda link mass "
                             "in PyBullet (0 = no perturbation; 10 = each link "
                             "scaled by a random factor in [0.9, 1.1]).  The QP "
                             "controller continues to use the *nominal* (un-perturbed) "
                             "M and tau_id, matching the proposal's setting where "
                             "'the simulator uses perturbed link masses ... while "
                             "the controller uses a nominal dynamics model.'")
    parser.add_argument("--mass-perturb-seed", type=int, default=0,
                        help="Seed used to draw the per-link mass perturbation pattern. "
                             "Same seed -> reproducible perturbation.")
    parser.add_argument("--epsilon-margin", type=float, default=0.0,
                        help="ε-margin applied to the viability acceleration bounds "
                             "(fraction of |qdd_max|).  0 = no margin (proposal "
                             "baseline).  e.g. 0.10 shrinks [lb, ub] by 10%% of "
                             "qdd_max on each side.  Designed to absorb worst-case "
                             "‖M^-1 - M̂^-1‖ ≤ δ.")
    parser.add_argument("--no-viability", action="store_true",
                        help="Disable viability tightening of the joint accel bounds "
                             "(yields a naive CFC-like controller for ablation).")
    parser.add_argument("--no-gamma", action="store_true",
                        help="Drop the self-collision Gamma constraint from the QP "
                             "(ablation baseline).")
    parser.add_argument("--no-reactive", action="store_true",
                        help="Skip the SDF emergency reactive-evasion fallback so "
                             "the QP runs even when an obstacle is < sdf-react-dist.")
    parser.add_argument("--no-obstacles", action="store_true",
                        help="Spawn the obstacle spheres far away (10 m) so the "
                             "scenario isolates joint-limit / self-collision constraints.")
    parser.add_argument("--no-fallback", action="store_true",
                        help="Disable the gravity-comp + velocity-damping safety "
                             "fallback that fires when the QP is infeasible / "
                             "OSQP errors.  Without it we just submit whatever "
                             "OSQP returned (or zero torque if u.value is None) — "
                             "this exposes how much of VPP-TC's safety actually "
                             "comes from the fallback layer vs. the QP itself.")

    # Motion planner
    parser.add_argument("--planner", type=str, default="linear",
                        choices=["linear", "lpvds"],
                        help="DS planner: 'linear' (potential field) or 'lpvds'")
    parser.add_argument("--lpvds-mat", type=str,
                        default=os.path.join(
                            "C:/meam6230/libraries/book-ds-opt/models",
                            "3D-CShape-bottom",
                            "3D-CShape-bottom_pqlf_2.mat"),
                        help="Path to a Figueroa ds-opt LPV-DS .mat file")
    parser.add_argument("--lpvds-npz", type=str, default=None,
                        help="Path to an .npz saved by draw_lpvds.py (overrides --lpvds-mat)")
    parser.add_argument("--lpvds-kperp", type=float, default=8.0,
                        help="Out-of-plane restoring stiffness for 2D LPV-DS")
    parser.add_argument("--start-on-demo", action="store_true",
                        help="Teleport robot to a Q whose EE pos == first demo point")
    parser.add_argument("--no-gui", action="store_true",
                        help="Run in headless DIRECT mode (no PyBullet window)")
    parser.add_argument("--tag", type=str, default="",
                        help="Tag appended to output CSV filename")
    parser.add_argument("--planner-gain", type=float, default=None,
                        help="Velocity gain. Default 50 for linear, 80 for LPV-DS.")
    parser.add_argument("--planner-vmax", type=float, default=None,
                        help="Optional speed cap on planner output [m/s]")

    # Output
    parser.add_argument("--output-dir", type=str,
                        default=os.path.join(_PROJECT_ROOT, "output"),
                        help="Directory for result CSV files")
    return parser.parse_args()


# ======================================================================
# Helper: create a sphere obstacle in PyBullet
# ======================================================================

def create_sphere(centre, radius, rgba=(1, 0, 0, 1)):
    """Create a static sphere in PyBullet and return its body id."""
    col = p.createCollisionShape(p.GEOM_SPHERE, radius=radius)
    vis = p.createVisualShape(p.GEOM_SPHERE, radius=radius, rgbaColor=rgba)
    return p.createMultiBody(
        baseMass=0,
        baseCollisionShapeIndex=col,
        baseVisualShapeIndex=vis,
        basePosition=centre,
    )


# ======================================================================
# Main
# ======================================================================

def main():
    args = get_args()
    np.random.seed(args.seed)
    os.makedirs(args.output_dir, exist_ok=True)

    # Hardware limits for Franka Panda
    acc_max = np.array([15, 7.5, 10, 12.5, 15, 20, 20], dtype=np.float32)
    qd_lim = np.array([2.175, 2.175, 2.175, 2.175, 2.61, 2.61, 2.61], dtype=np.float32)
    q_min_hw = np.array([-2.8973, -1.7628, -2.8973, -3.0718, -2.8973, -0.0175, -2.8973])
    q_max_hw = np.array([2.8973, 1.7628, 2.8973, -0.0698, 2.8973, 3.7525, 2.8973])
    # Franka joint torque limits (Nm). Used to clamp QP outputs so that
    # numerically inaccurate solver returns can't blow the system up.
    tau_max = np.array([87, 87, 87, 87, 12, 12, 12], dtype=np.float32)

    # Impedance gains
    lambda1, lambda2, lambda3 = 5, 100, 100

    # ----- Initialise robot -----
    robot = Panda(stepsize=args.stepsize, gui=not args.no_gui)
    robot.setControlMode("torque")
    _GUI = not args.no_gui

    # ----- (Part 2) Perturb PyBullet link masses to make the SIMULATOR's
    #       dynamics differ from what the controller assumes.
    # nominal_link_masses[link] is the un-perturbed mass; perturbed_link_masses
    # is what PyBullet currently has applied.  We toggle between them so the
    # QP can query the *nominal* M(q) and tau_id while PyBullet integrates
    # under the perturbed dynamics. ----------------------------------------
    n_links = p.getNumJoints(robot.robot)               # incl. virtual flange
    nominal_link_masses = []
    for li in range(-1, n_links):                       # -1 = base
        info = p.getDynamicsInfo(robot.robot, li)
        nominal_link_masses.append((li, info[0]))       # (linkIdx, mass)

    if args.mass_perturb_pct > 0.0:
        rng = np.random.RandomState(args.mass_perturb_seed)
        perturb_factors = []
        for li, m in nominal_link_masses:
            if m <= 0:        # fixed/virtual link or massless flange
                perturb_factors.append((li, m, m, 1.0))
                continue
            # Uniform random factor in [1 - p, 1 + p].
            f = 1.0 + rng.uniform(-args.mass_perturb_pct,
                                  args.mass_perturb_pct) / 100.0
            new_m = m * f
            p.changeDynamics(robot.robot, li, mass=new_m)
            perturb_factors.append((li, m, new_m, f))
        # Pretty-print summary
        print(f"[mismatch] perturbed {len([1 for _,_,_,f in perturb_factors if f != 1.0])} "
              f"link masses by U[-{args.mass_perturb_pct:.0f}%, +{args.mass_perturb_pct:.0f}%] "
              f"(seed={args.mass_perturb_seed})")
        for li, m_old, m_new, f in perturb_factors:
            if f != 1.0:
                print(f"            link {li:>2d}: {m_old:.4f} -> {m_new:.4f} kg "
                      f"(x{f:.3f})")

    def restore_nominal_masses():
        for li, m in nominal_link_masses:
            p.changeDynamics(robot.robot, li, mass=m)

    def restore_perturbed_masses():
        for li, m_old, m_new, _ in perturb_factors:
            p.changeDynamics(robot.robot, li, mass=m_new)

    def query_nominal_dynamics(q, qd):
        """Return (M_nom, tau_id_nom) using the un-perturbed link masses,
        regardless of what PyBullet currently has applied. Restores the
        perturbed masses before returning so simulation isn't affected."""
        if args.mass_perturb_pct == 0.0:
            return (np.array(robot.getMassMatrix(q)),
                    np.array(robot.solveInverseDynamics(q, qd, [0] * 7)))
        restore_nominal_masses()
        try:
            M_nom = np.array(robot.getMassMatrix(q))
            tau_nom = np.array(robot.solveInverseDynamics(q, qd, [0] * 7))
        finally:
            restore_perturbed_masses()
        return M_nom, tau_nom

    # ----- Create obstacles -----
    x_obs = list(args.obstacle_pos)
    if args.no_obstacles:
        # Park the spheres 10m away so they're effectively absent.
        x_obs = [10.0, 10.0, 10.0]
    obstacle_1 = create_sphere(x_obs, args.obstacle_radius, rgba=(1, 0, 0, 1))
    obstacle_2 = create_sphere(
        [x_obs[0] + 0.5, x_obs[1] + 0.1, x_obs[2]],
        args.obstacle_radius,
        rgba=(1, 0, 0, 1),
    )

    # Target marker (green)
    target_pos = np.array(args.target_pos)

    # ----- Motion planner (DS) -----
    if args.planner == "lpvds":
        gain = 80.0 if args.planner_gain is None else args.planner_gain
        if args.lpvds_npz is not None:
            data = dict(np.load(args.lpvds_npz, allow_pickle=False))
            R = np.asarray(data["R"])
            origin = np.asarray(data["origin"])
            ds_args = dict(Priors=data["Priors"], Mu=data["Mu"], Sigma=data["Sigma"],
                           A=data["A"], b=data["b"],
                           attractor=np.asarray(data["attractor"]).reshape(-1),
                           v_max=args.planner_vmax, gain=gain)
            ds2d = LPVDS(**ds_args)
            # Place attractor at the user-specified target_pos by shifting origin
            att2d = ds2d.attractor
            origin = target_pos - R[:, :2] @ att2d
            planner = PlanarLift(ds2d, origin=origin, R=R, k_perp=args.lpvds_kperp)
            print(f"[planner] 2D LPV-DS from {os.path.basename(args.lpvds_npz)}, "
                  f"K={ds2d.Priors.size}, plane={data['plane']}, "
                  f"attractor3D -> {target_pos.round(3)}, gain={gain}")
            # Draw the demo curves into the PyBullet scene (yellow)
            demos_2d = np.asarray(data["demos_X"])  # (2, N) concatenated
            demos_3d = (origin[:, None] + R[:, :2] @ demos_2d).T  # (N, 3)
            if _GUI:
                for i in range(1, demos_3d.shape[0]):
                    if np.linalg.norm(demos_3d[i] - demos_3d[i-1]) < 0.05:
                        p.addUserDebugLine(demos_3d[i-1].tolist(),
                                           demos_3d[i].tolist(),
                                           lineColorRGB=[1.0, 0.85, 0.0],
                                           lineWidth=1.5, lifeTime=0)

            # Optionally start the EE on/near the first demo point (robust to plane offset)
            if args.start_on_demo:
                start_xyz = demos_3d[0].tolist()
                # Use IK to find a Q that puts EE at the first demo point;
                # neutral downward orientation works for most reachable points.
                q_start = p.calculateInverseKinematics(
                    robot.robot, 7, start_xyz,
                    targetOrientation=p.getQuaternionFromEuler([math.pi, 0, 0]),
                    maxNumIterations=200, residualThreshold=1e-4,
                )[:7]
                for j in range(7):
                    p.resetJointState(robot.robot, j, q_start[j])
                ee_actual = np.array(robot.solveForwardKinematics()[0])
                print(f"[start-on-demo] target {np.array(start_xyz).round(3)}  "
                      f"reached {ee_actual.round(3)}  err={np.linalg.norm(ee_actual-start_xyz):.4f} m")
        else:
            ds = LPVDS.from_mat(args.lpvds_mat, v_max=args.planner_vmax, gain=gain)
            planner = ds.translate(target_pos)
            print(f"[planner] 3D LPV-DS from {os.path.basename(args.lpvds_mat)}, "
                  f"K={planner.Priors.size}, attractor -> {target_pos.round(3)}, "
                  f"gain={gain}")
    else:
        gain = 50.0 if args.planner_gain is None else args.planner_gain
        planner = LinearDS(target=target_pos, gain=gain)
        print(f"[planner] Linear DS, gain={gain}")
    if _GUI:
        target_vis = p.createVisualShape(
            p.GEOM_SPHERE, radius=0.02, rgbaColor=[0, 1, 0, 1]
        )
        p.createMultiBody(baseMass=0, baseVisualShapeIndex=target_vis,
                          basePosition=target_pos.tolist())

    # ----- Data loggers -----
    log = {k: [] for k in [
        "time", "self_collision_dist", "gamma", "real_dist",
        "target_dist", "pred_dist", "pred_dist_viability", "runtime_ms",
        "end_x", "end_y", "end_z",
        "kinetic_energy", "task_pot", "storage",
        # Joint state (worst-of-7 summaries; full vectors via *_max)
        "q_lim_violation",   # max( max(q-q_max,0), max(q_min-q,0) ) over 7 joints
        "qd_lim_violation",  # max( |qd| - qd_lim, 0 )                   over 7 joints
        "qd_max_abs",        # max |qd|
        "gamma_active",      # 1 if Gamma constraint was added this step
        "soft_fallback",     # 1 if QP failed and we fell back to bang-bang
        "reactive_used",     # 1 if SDF emergency took over (vs QP)
    ]}

    # Initial EE position for the trail
    prev_end_pos = np.array(robot.solveForwardKinematics()[0])
    trail_color = [0.1, 0.4, 1.0]  # blue
    trail_decimate = max(1, int(0.005 / args.stepsize))  # ~one segment / 5 ms

    if _GUI:
        time.sleep(2)
    wall_start = time.time()
    num_steps = int(args.duration / args.stepsize)

    for step_i in range(num_steps):
        t0 = time.perf_counter()

        if step_i % int(1.0 / args.stepsize) == 0:
            print(f"[sim] t = {robot.t:.3f} s")

        # --- End-effector impedance force ---
        end_pos = np.array(robot.solveForwardKinematics()[0])
        fx = planner(end_pos)
        e1 = fx / np.linalg.norm(fx)
        e2 = np.array([1, 0, 0]) - np.dot([1, 0, 0], e1) * e1
        e2 /= np.linalg.norm(e2)
        e3 = np.cross(e1, e2)
        Q = np.column_stack((e1, e2, e3))
        D = Q @ np.diag([lambda1, lambda2, lambda3]) @ Q.T
        xdot = np.array(robot.getEndVelocity())
        fc = -D @ (xdot - fx)

        dist_to_target = np.linalg.norm(end_pos - target_pos)

        # --- Move obstacle sinusoidally ---
        new_z = math.sin(step_i / 180.0 * math.pi) * 0.1
        new_pos = [x_obs[0], x_obs[1], x_obs[2] + new_z]
        p.resetBasePositionAndOrientation(obstacle_1, new_pos, [0, 0, 0, 1])

        # --- Joint state & viability stopping position ---
        q, qd = robot.getJointStates()
        qe = compute_qe(q, qd)

        # --- Batch SDF query (2 configs x 2 points) ---
        x0 = np.array(x_obs, dtype=np.float32).reshape(1, 3)
        x_query = np.array(new_pos, dtype=np.float32).reshape(1, 3)
        pose = np.eye(4, dtype=np.float32)

        theta_np = np.stack([q, qe], axis=0).astype(np.float32)
        points_np = np.stack([
            x_query.squeeze(),
            (x0 + np.array([0.5, 0.1, 0.0], dtype=np.float32)).squeeze(),
        ], axis=0).astype(np.float32)
        pose_np = np.broadcast_to(pose, (2, 4, 4)).astype(np.float32)

        dsts, grad_qs = query_sdf_batch(points_np, pose_np, theta_np)

        dst, grad = dsts[0, 0], grad_qs[0, 0]
        dst2, grad2 = dsts[1, 0], grad_qs[1, 0]
        dst3, grad3 = dsts[0, 1], grad_qs[0, 1]
        dst4, grad4 = dsts[1, 1], grad_qs[1, 1]

        # --- Real PyBullet distance (ground-truth check) ---
        real_dist1 = compute_min_center_distance(
            robot.robot, obstacle_1, args.obstacle_radius, 2.0)
        real_dist2 = compute_min_center_distance(
            robot.robot, obstacle_2, args.obstacle_radius, 2.0)

        # --- Self-collision safety ---
        Gamma, grad_gamma = compute_gamma_and_grad(
            q, qd, threshold=args.gamma_threshold)

        # --- Acceleration bounds ---
        qdd_lb, qdd_ub = compute_joint_acceleration_bounds_vec(
            q, qd, q_min_hw, q_max_hw, qd_lim, acc_max, dt=0.02,
            viability=not args.no_viability)

        # ε-margin: shrink the acceleration interval on each side by
        #   eps_i = epsilon_margin * acc_max[i]
        # to absorb worst-case dynamics-mismatch perturbations on q̈.
        if args.epsilon_margin > 0.0:
            eps_vec = args.epsilon_margin * acc_max
            qdd_lb_eps = qdd_lb + eps_vec
            qdd_ub_eps = qdd_ub - eps_vec
            # Only apply where the tightening still leaves a non-empty interval;
            # otherwise fall back to the un-tightened bound on that joint.
            for i in range(7):
                if qdd_lb_eps[i] <= qdd_ub_eps[i]:
                    qdd_lb[i] = qdd_lb_eps[i]
                    qdd_ub[i] = qdd_ub_eps[i]

        # --- Select gradient for the closest obstacle configuration ---
        all_dsts = [dst, dst2, dst3, dst4]
        all_grads = [grad, grad2, grad3, grad4]
        min_idx = int(np.argmin(all_dsts))
        sel_grad = all_grads[min_idx]

        # --- Reactive evasion or QP controller ---
        used_reactive = 0
        used_gamma    = 0
        used_soft     = 0
        if (not args.no_reactive) and min(all_dsts) < args.sdf_react_dist:
            # Emergency: directly steer away from obstacle
            used_reactive = 1
            dt = 0.02
            g_eff = 0.5 * sel_grad * dt ** 2
            qdd_cmd = np.where(g_eff > 0, qdd_ub, qdd_lb)
            tau = np.clip(np.array(robot.solveInverseDynamics(q, qd, qdd_cmd.tolist())),
                          -tau_max, tau_max)
            robot.setTargetTorques(tau.tolist())
            robot.step()
        else:
            # Ensure feasibility
            for idx in range(7):
                if qdd_lb[idx] > qdd_ub[idx]:
                    qdd_lb[idx] = qdd_ub[idx] - 1e-4

            # The model the QP *thinks* the robot has.  Two sources of mismatch:
            #
            #   (a) `--mass-perturb-pct > 0`  ⇒ PyBullet integrates with perturbed
            #        link masses; query_nominal_dynamics() returns the un-perturbed
            #        (nominal) M and tau_id, exactly the proposal's setting:
            #        "the controller uses a nominal dynamics model while the
            #         simulator uses perturbed link masses."
            #
            #   (b) `--qp-mass-scale != 1.0`  ⇒ multiplies the (already nominal)
            #        M and tau_id by a uniform scalar (legacy ablation flag).
            M_nom, tau_id_nom = query_nominal_dynamics(q, qd)
            M        = M_nom        * args.qp_mass_scale
            tau_id   = tau_id_nom   * args.qp_mass_scale
            M_inv    = np.linalg.inv(M)

            u = cp.Variable(7)
            J = np.array(robot.getJacobian())
            JT_pinv = np.linalg.pinv(J.T)

            objective = (cp.sum_squares(JT_pinv @ u - fc)
                         + args.alpha * cp.sum_squares(u))
            constraints = [
                M_inv @ u >= qdd_lb + M_inv @ tau_id,
                M_inv @ u <= qdd_ub + M_inv @ tau_id,
            ]

            soft = False
            if grad_gamma is not None and not args.no_gamma:
                used_gamma = 1
                dt = 0.02
                gq = grad_gamma[:7]
                gqd = grad_gamma[7:]
                g_eff = 0.5 * gq * dt ** 2 + gqd * dt
                c_const = gq.dot(qd) * dt
                eps = 4e-1
                constraints.append(
                    g_eff @ M_inv @ u >= eps - c_const + g_eff @ M_inv @ tau_id
                )
                prob = cp.Problem(cp.Minimize(objective), constraints)
                try:
                    prob.solve(solver=cp.OSQP)
                except cp.SolverError:
                    soft = True

                while prob.status != cp.OPTIMAL and eps > 1e-3:
                    eps -= 1e-1
                    constraints[-1] = (
                        g_eff @ M_inv @ u >= eps - c_const + g_eff @ M_inv @ tau_id
                    )
                    prob = cp.Problem(cp.Minimize(objective), constraints)
                    try:
                        prob.solve(solver=cp.OSQP)
                    except cp.SolverError:
                        soft = True
                        break

                if eps < 1e-3:
                    soft = True

                if soft:
                    used_soft = 1
                    if args.no_fallback:
                        # No safety net: submit whatever OSQP returned, or zero
                        # torque if it returned None.  Exposes the bare-QP
                        # behaviour without the gravity-comp/damping rescue.
                        if u.value is None:
                            tau = np.zeros(7)
                        else:
                            tau = np.clip(np.array(u.value), -tau_max, tau_max)
                    else:
                        # Safe fallback: gravity-compensation + velocity damping.
                        # Guarantees passive (energy-dissipating) action even when
                        # the QP can't find a feasible solution.
                        K_damp = 5.0
                        tau = (np.array(robot.solveInverseDynamics(q, qd, [0]*7))
                               - K_damp * np.asarray(qd))
                        tau = np.clip(tau, -tau_max, tau_max)
                    robot.setTargetTorques(tau.tolist())
                    robot.step()
            else:
                prob = cp.Problem(cp.Minimize(objective), constraints)
                try:
                    prob.solve(solver=cp.OSQP)
                except cp.SolverError:
                    soft = True
                if u.value is None:
                    soft = True
                if soft:
                    used_soft = 1
                    if args.no_fallback:
                        if u.value is None:
                            tau = np.zeros(7)
                        else:
                            tau = np.clip(np.array(u.value), -tau_max, tau_max)
                    else:
                        # Safe fallback: gravity-comp + velocity damping.
                        K_damp = 5.0
                        tau = (np.array(robot.solveInverseDynamics(q, qd, [0]*7))
                               - K_damp * np.asarray(qd))
                        tau = np.clip(tau, -tau_max, tau_max)
                    robot.setTargetTorques(tau.tolist())
                    robot.step()

            if not soft:
                tau_cmd = np.clip(np.array(u.value), -tau_max, tau_max)
                robot.setTargetTorques(tau_cmd.tolist())
                robot.step()

        t1 = time.perf_counter()

        # --- Self-collision distance check ---
        sc_dist = math.inf
        collision = False
        for l1 in range(7):
            for l2 in range(7):
                if abs(l1 - l2) > 1 and {l1, l2} != {4, 6}:
                    pts = robot.getClosestPoints(l1, l2)
                    dmin = min(pt[8] for pt in pts)
                    sc_dist = min(sc_dist, dmin)
                    if dmin < 0:
                        collision = True

        # --- Log ---
        log["time"].append(robot.t)
        log["self_collision_dist"].append(sc_dist)
        log["gamma"].append(Gamma)
        log["real_dist"].append(min(real_dist1, real_dist2))
        log["target_dist"].append(dist_to_target)
        log["pred_dist"].append(min(dst, dst3))
        log["pred_dist_viability"].append(min(dst2, dst4))
        log["runtime_ms"].append((t1 - t0) * 1e3)
        log["end_x"].append(float(end_pos[0]))
        log["end_y"].append(float(end_pos[1]))
        log["end_z"].append(float(end_pos[2]))
        # Storage function for empirical passivity check:
        #   T_kin = 1/2 q̇ᵀ M(q) q̇  (mechanical KE, computed from pybullet M)
        #   V_pot = 1/2 ‖x − x*‖²    (workspace task potential, DS-agnostic surrogate)
        #   S = T_kin + λ V_pot
        try:
            M_log = np.asarray(robot.getMassMatrix(q))
            qd_log = np.asarray(qd)
            T_kin = float(0.5 * qd_log @ M_log @ qd_log)
        except Exception:
            T_kin = float("nan")
        V_pot = float(0.5 * (dist_to_target ** 2))
        log["kinetic_energy"].append(T_kin)
        log["task_pot"].append(V_pot)
        log["storage"].append(T_kin + 50.0 * V_pot)

        # Joint-limit / velocity-limit overshoot (per-step worst over 7 joints).
        q_arr  = np.asarray(q)
        qd_arr = np.asarray(qd)
        q_over = np.maximum(
            np.maximum(q_arr - q_max_hw, 0.0),
            np.maximum(q_min_hw - q_arr, 0.0),
        )
        qd_over = np.maximum(np.abs(qd_arr) - qd_lim, 0.0)
        log["q_lim_violation"].append(float(q_over.max()))
        log["qd_lim_violation"].append(float(qd_over.max()))
        log["qd_max_abs"].append(float(np.abs(qd_arr).max()))
        log["gamma_active"].append(used_gamma)
        log["soft_fallback"].append(used_soft)
        log["reactive_used"].append(used_reactive)

        # Draw EE trail in PyBullet
        if _GUI and step_i % trail_decimate == 0:
            seg = end_pos - prev_end_pos
            if np.linalg.norm(seg) > 1e-5:
                p.addUserDebugLine(prev_end_pos.tolist(), end_pos.tolist(),
                                   lineColorRGB=trail_color,
                                   lineWidth=3.0, lifeTime=0)
                prev_end_pos = end_pos.copy()

        if collision:
            print(f"[sim] t={robot.t:.3f}s  COLLISION  dist={sc_dist:.5f}")
            break

        if _GUI:
            time.sleep(args.stepsize)

    # --- Summary ---
    elapsed = time.time() - wall_start
    runtimes = np.array(log["runtime_ms"][1:])
    print(f"\n{'='*50}")
    print(f"Simulation finished in {elapsed:.2f}s wall-clock")
    print(f"  Steps         : {len(log['time'])}")
    print(f"  Mean step     : {runtimes.mean():.3f} ms")
    print(f"  Median step   : {np.median(runtimes):.3f} ms")
    print(f"  95th pct      : {np.percentile(runtimes, 95):.3f} ms")
    print(f"  Max step      : {runtimes.max():.3f} ms")

    # --- Save ---
    df = pd.DataFrame(log)
    suffix = f"_{args.tag}" if args.tag else ""
    csv_path = os.path.join(args.output_dir, f"run_{int(time.time())}{suffix}.csv")
    df.to_csv(csv_path, index=False)
    print(f"Results saved to {csv_path}")


if __name__ == "__main__":
    main()
