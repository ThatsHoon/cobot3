"""Spot locomotion + arm controller (in-process, physics-callback driven).

Binds SpotFlatTerrainPolicy to an existing /World/Robot prim (spot_with_arm).
Handles mixed DOFs: leg 12-DOF RL policy + arm stow/aim hold — single
apply_action call per step. Called via:
    world.add_physics_callback("spot_ctrl", controller.on_physics_step)

Toggle: GP_SPOT_CONTROL=0 → controller not created (observation-only debug).
"""
import math
import time
from typing import Optional, Tuple

import numpy as np

_LOG = "[spot_ctrl]"


def _log(msg: str) -> None:
    print(f"{_LOG} {msg}", flush=True)


# Arm DOF stow / aim targets (radians, Boston Dynamics spot_with_arm convention)
_STOW: dict = {
    "arm0_sh0":  0.0,
    "arm0_sh1": -3.14159,
    "arm0_el0":  3.14159,
    "arm0_el1":  0.0,
    "arm0_wr0":  0.0,
    "arm0_wr1":  0.0,
    "arm0_f1x":  0.0,
}
_AIM: dict = {
    "arm0_sh0":  0.0,
    "arm0_sh1": -0.6,
    "arm0_el0":  1.8,
    "arm0_el1":  0.0,
    "arm0_wr0":  0.0,
    "arm0_wr1":  0.0,
    "arm0_f1x":  0.0,
}

_ARM_STIFFNESS = 1000.0   # N·m/rad — PD position control for arm
_ARM_DAMPING   =   50.0   # N·m·s/rad

_LEG_PREFIXES = ("fl_", "fr_", "hl_", "hr_")
_ARM_PREFIX   = "arm0_"
_CMD_TIMEOUT  = 0.5        # seconds — teleop stale → fall through to nav/idle


class SpotController:
    """In-process Spot RL + arm controller bound to an existing stage prim.

    PolicyController.__init__ checks prim validity before AddReference, so
    passing prim_path of an existing /World/Robot skips USD reference injection.
    """

    def __init__(self, prim_path: str):
        from isaacsim.robot.policy.examples.robots import SpotFlatTerrainPolicy

        _log(f"init: binding SpotFlatTerrainPolicy → {prim_path}")
        self._policy = SpotFlatTerrainPolicy(prim_path=prim_path)
        self._first_step = True
        self._initialized = False

        # DOF layout (resolved after first physics step initialize())
        self._n_dofs = 0
        self._leg_idx: Optional[np.ndarray] = None
        self._arm_idx: Optional[np.ndarray] = None
        self._arm_names: list = []
        self._mixed_dofs = False   # True when arm DOFs detected

        # Velocity command state
        self._vel_cmd = np.zeros(3)   # [vx, vy, wz]
        self._vel_ts  = 0.0

        # Nav goal (x, y) world frame — cleared on arrival
        self._nav_goal: Optional[Tuple[float, float]] = None

        # Event flags
        self._arm_aim  = False
        self._fire_req = False
        self._speaker: Optional[str] = None

    # ── command API (called from camera_publisher _apply_cmd) ─────────────

    def set_cmd_vel(self, vx: float, vy: float, wz: float) -> None:
        self._vel_cmd = np.array([vx, vy, wz])
        self._vel_ts  = time.time()

    def set_nav_goal(self, x: float, y: float) -> None:
        self._nav_goal = (x, y)

    def clear_nav_goal(self) -> None:
        self._nav_goal = None

    def trigger_fire(self) -> None:
        self._fire_req = True
        self._arm_aim  = True

    def set_speaker(self, payload: str) -> None:
        self._speaker = payload

    # ── physics callback ─────────────────────────────────────────────────

    def on_physics_step(self, dt: float) -> None:
        if self._first_step:
            self._first_step = False
            try:
                self._policy.initialize()
                self._setup_dof_layout()
                self._patch_arm_gains()
                self._initialized = True
                _log(f"ready — {self._n_dofs} DOFs "
                     f"(legs={len(self._leg_idx)}, arm={len(self._arm_idx)})")
            except Exception as exc:
                _log(f"initialize failed: {exc!r}")
            return

        if not self._initialized:
            return

        base_cmd = self._arbitrate()
        self._forward(dt, base_cmd)
        self._handle_events()

    # ── internals ────────────────────────────────────────────────────────

    def _setup_dof_layout(self) -> None:
        names = list(self._policy.robot.dof_names or [])
        self._n_dofs = len(names)
        self._leg_idx = np.array(
            [i for i, n in enumerate(names)
             if any(n.startswith(p) for p in _LEG_PREFIXES)], dtype=np.int32)
        self._arm_idx = np.array(
            [i for i, n in enumerate(names) if n.startswith(_ARM_PREFIX)],
            dtype=np.int32)
        self._arm_names = [names[i] for i in self._arm_idx]
        self._mixed_dofs = (len(self._arm_idx) > 0)

    def _patch_arm_gains(self) -> None:
        """Arm DOFs get stiffness=0 from spot_env.yaml (yaml lacks arm entries).
        Restore to usable PD gains so position targets are tracked."""
        if not self._mixed_dofs:
            return
        try:
            view = self._policy.robot._articulation_view
            gains = view.get_gains()
            stiff = np.array(gains[0], dtype=float).ravel()
            damp  = np.array(gains[1], dtype=float).ravel()
            for i in self._arm_idx:
                stiff[i] = _ARM_STIFFNESS
                damp[i]  = _ARM_DAMPING
            view.set_gains(stiff, damp)
            _log(f"arm gain patch: K={_ARM_STIFFNESS} D={_ARM_DAMPING} "
                 f"({len(self._arm_idx)} DOFs)")
        except Exception as exc:
            _log(f"arm gain patch failed (arm may drift): {exc!r}")

    def _arbitrate(self) -> np.ndarray:
        """Teleop (0.5 s timeout) > nav_goal P-ctrl > idle zeros."""
        if time.time() - self._vel_ts < _CMD_TIMEOUT:
            if np.any(np.abs(self._vel_cmd) > 1e-6):
                return self._vel_cmd.copy()
        if self._nav_goal is not None:
            return self._nav_p_ctrl()
        return np.zeros(3)

    def _nav_p_ctrl(self) -> np.ndarray:
        try:
            pos, quat = self._policy.robot.get_world_pose()
        except Exception:
            return np.zeros(3)
        gx, gy = self._nav_goal
        dx, dy = gx - float(pos[0]), gy - float(pos[1])
        dist = math.hypot(dx, dy)
        if dist < 0.15:
            self._nav_goal = None
            _log("nav_goal reached")
            return np.zeros(3)
        target_yaw = math.atan2(dy, dx)
        robot_yaw  = self._quat_to_yaw(quat)
        err = math.atan2(math.sin(target_yaw - robot_yaw),
                         math.cos(target_yaw - robot_yaw))
        vx = min(0.6, 0.5 * dist) if abs(err) < 0.4 else 0.0
        wz = max(-1.2, min(1.2, 2.0 * err))
        return np.array([vx, 0.0, wz])

    @staticmethod
    def _quat_to_yaw(q: np.ndarray) -> float:
        w, x, y, z = float(q[0]), float(q[1]), float(q[2]), float(q[3])
        return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))

    def _forward(self, dt: float, command: np.ndarray) -> None:
        """Combined leg policy + arm stow/aim in one apply_action call."""
        from isaacsim.core.utils.types import ArticulationAction
        policy = self._policy

        if policy._policy_counter % policy._decimation == 0:
            obs = (self._obs_legs(command) if self._mixed_dofs
                   else policy._compute_observation(command))
            action = policy._compute_action(obs)
            policy._previous_action = action.copy()
            policy.action = action

        all_pos = np.array(policy.robot.get_joint_positions(), dtype=float)

        if self._mixed_dofs:
            leg_def = np.asarray(policy.default_pos, dtype=float)[self._leg_idx]
            all_pos[self._leg_idx] = leg_def + policy.action * policy._action_scale
            arm_map = _AIM if self._arm_aim else _STOW
            for i, name in zip(self._arm_idx, self._arm_names):
                if name in arm_map:
                    all_pos[i] = arm_map[name]
        else:
            all_pos = (np.asarray(policy.default_pos, dtype=float)
                       + policy.action * policy._action_scale)

        policy.robot.apply_action(ArticulationAction(joint_positions=all_pos))
        policy._policy_counter += 1

    def _obs_legs(self, command: np.ndarray) -> np.ndarray:
        """48-dim observation using leg DOF positions/velocities only (12-DOF policy)."""
        from isaacsim.core.utils.rotations import quat_to_rot_matrix
        p = self._policy
        lin_I = p.robot.get_linear_velocity()
        ang_I = p.robot.get_angular_velocity()
        _, q  = p.robot.get_world_pose()
        R_BI  = quat_to_rot_matrix(q).T
        all_pos = np.array(p.robot.get_joint_positions(), dtype=float)
        all_vel = np.array(p.robot.get_joint_velocities(), dtype=float)
        leg_pos = all_pos[self._leg_idx]
        leg_vel = all_vel[self._leg_idx]
        leg_def = np.asarray(p.default_pos, dtype=float)[self._leg_idx]
        obs = np.zeros(48)
        obs[:3]   = R_BI @ lin_I
        obs[3:6]  = R_BI @ ang_I
        obs[6:9]  = R_BI @ np.array([0.0, 0.0, -1.0])
        obs[9:12] = command
        obs[12:24] = leg_pos - leg_def
        obs[24:36] = leg_vel
        obs[36:48] = p._previous_action
        return obs

    def _handle_events(self) -> None:
        if self._speaker is not None:
            _log(f"[speaker] {self._speaker}")
            self._speaker = None
        if self._fire_req:
            _log("[fire] trigger (sim-only ray-cast placeholder)")
            self._fire_req = False
            self._arm_aim  = False
