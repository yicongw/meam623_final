#!/usr/bin/env python3
"""Headless PyBullet render of the obstacle scene for the poster.

Reproduces the simulation environment seen in the GUI:
  - Franka Panda arm at the origin
  - Two red obstacle spheres
  - One green target sphere
  - Checkerboard floor + sky-blue background

Output: output/fig_poster_col3_scene.png  (1600x1000 PNG)
"""

from __future__ import annotations

import math
import os
import sys

import numpy as np
import pybullet as p
import pybullet_data

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, os.pardir))
_OUT = os.path.join(_PROJECT_ROOT, "output")
URDF = os.path.join(_PROJECT_ROOT, "assets", "urdf", "panda", "panda.urdf")

OUT_PNG = os.path.join(_OUT, "fig_poster_col3_scene.png")

# ---- scene constants (mirrors simulate.py defaults) ----
OBS_R   = 0.05
OBS_1   = [0.00, -0.40, 0.50]
OBS_2   = [0.50, -0.30, 0.50]
TGT     = [0.00, -0.60, 0.30]
TGT_R   = 0.04   # slightly larger so it's visible in the render

# Joint config close to what the GUI shows: arm bent forward, EE roughly
# horizontal, similar to the canonical "ready" Franka pose.
Q_INIT = np.array([0.0, -0.55, 0.0, -2.20, 0.0, 1.65, 0.78])


def make_sphere(centre, radius, rgba):
    vis = p.createVisualShape(p.GEOM_SPHERE, radius=radius, rgbaColor=rgba)
    return p.createMultiBody(baseMass=0, baseVisualShapeIndex=vis,
                              basePosition=list(centre))


def main():
    p.connect(p.DIRECT)
    p.setAdditionalSearchPath(pybullet_data.getDataPath())
    p.setGravity(0, 0, -9.81)

    plane = p.loadURDF("plane.urdf", useFixedBase=True)
    if not os.path.exists(URDF):
        sys.exit(f"URDF not found: {URDF}")
    robot = p.loadURDF(URDF, useFixedBase=True,
                        flags=p.URDF_USE_SELF_COLLISION)

    # Set joint angles
    n_joints = p.getNumJoints(robot)
    arm_joints = [j for j in range(n_joints)
                  if p.getJointInfo(robot, j)[2] == p.JOINT_REVOLUTE][:7]
    for q, ji in zip(Q_INIT, arm_joints):
        p.resetJointState(robot, ji, q)

    # Obstacles + target
    make_sphere(OBS_1, OBS_R, [1.0, 0.10, 0.10, 1.0])
    make_sphere(OBS_2, OBS_R, [1.0, 0.10, 0.10, 1.0])
    make_sphere(TGT,   TGT_R, [0.10, 0.85, 0.20, 1.0])

    # ---- Camera ----
    # Match the perspective from the user's GUI screenshot:
    # camera elevated, looking down toward arm + scene from the front.
    cam_target = [0.10, -0.20, 0.35]
    view = p.computeViewMatrixFromYawPitchRoll(
        cameraTargetPosition=cam_target,
        distance=1.8,
        yaw=70,         # front-quarter view (right-front)
        pitch=-25,      # looking down
        roll=0,
        upAxisIndex=2,
    )
    proj = p.computeProjectionMatrixFOV(fov=45, aspect=1.6,
                                          nearVal=0.1, farVal=10.0)

    width, height = 1600, 1000
    rgba = p.getCameraImage(width, height, view, proj,
                             renderer=p.ER_TINY_RENDERER,
                             lightDirection=[0.6, -0.8, 1.5],
                             lightAmbientCoeff=0.55,
                             lightDiffuseCoeff=0.7,
                             lightSpecularCoeff=0.4,
                             shadow=1)[2]
    img = np.array(rgba, dtype=np.uint8).reshape(height, width, 4)

    # Save as PNG
    from PIL import Image
    Image.fromarray(img).save(OUT_PNG)
    print(f"saved -> {OUT_PNG}  ({width}x{height})")

    p.disconnect()


if __name__ == "__main__":
    main()
