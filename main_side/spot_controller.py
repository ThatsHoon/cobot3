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
                # set_gains/set_limits=False: spot_env.yaml 에는 12 leg DOF 만 있어서
                # 19-DOF(spot_with_arm) articulation 에 그대로 넘기면 shape(12,) vs (1,19)
                # broadcast 오류 발생. DOF 레이아웃 확인 후 수동으로 전체 게인을 설정한다.
                self._policy.initialize(set_gains=False, set_limits=False)
                self._setup_dof_layout()
                self._patch_arm_gains()
                self._reset_to_standing()
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

    def _reset_to_standing(self) -> None:
        """서있는 자세로 teleport — gp_scene.usd 자동저장으로 넘어진 채 저장된 경우 대비."""
        try:
            robot = self._policy.robot
            default_q = np.zeros(self._n_dofs, dtype=float)
            pol_def = np.asarray(self._policy.default_pos, dtype=float)
            if len(pol_def) == len(self._leg_idx):
                for idx, val in zip(self._leg_idx, pol_def):
                    default_q[idx] = val
            else:
                default_q[self._leg_idx] = pol_def[self._leg_idx]
            for i, name in zip(self._arm_idx, self._arm_names):
                if name in _STOW:
                    default_q[i] = _STOW[name]
            robot.set_joint_positions(default_q)
            robot.set_joint_velocities(np.zeros(self._n_dofs))
            robot.set_linear_velocity(np.zeros(3))
            robot.set_angular_velocity(np.zeros(3))
            pos, ori = robot.get_world_pose()
            if float(pos[2]) < 0.4:
                robot.set_world_pose(
                    position=np.array([float(pos[0]), float(pos[1]), 0.55]),
                    orientation=ori,
                )
                _log(f"base Z 조정: {float(pos[2]):.3f} → 0.55")
            _log("서있는 자세 초기화 완료")
        except Exception as exc:
            _log(f"서있는 자세 초기화 실패: {exc!r}")

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
        """19-DOF gain 전체를 설정: leg → yaml 값, arm → 커스텀 PD.
        set_gains=False 로 initialize 했으므로 여기서 전체를 채워야 한다."""
        try:
            from isaacsim.robot.policy.examples.controllers.config_loader import (
                get_robot_joint_properties,
            )
            view  = self._policy.robot._articulation_view
            stiff = np.zeros(self._n_dofs, dtype=float)
            damp  = np.zeros(self._n_dofs, dtype=float)

            # Leg: yaml(spot_env.yaml)에 정의된 12-DOF 게인을 그대로 사용
            leg_names = [self._policy.robot.dof_names[i] for i in self._leg_idx]
            _, _, leg_stiff, leg_damp, _, _ = get_robot_joint_properties(
                self._policy.policy_env_params, leg_names
            )
            stiff[self._leg_idx] = leg_stiff
            damp[self._leg_idx]  = leg_damp

            # Arm: yaml 에 없으므로 커스텀 PD 게인
            if self._mixed_dofs:
                stiff[self._arm_idx] = _ARM_STIFFNESS
                damp[self._arm_idx]  = _ARM_DAMPING

            view.set_gains(stiff, damp)
            _log(
                f"gains OK — leg K={leg_stiff[0] if len(leg_stiff) else 0} "
                f"D={leg_damp[0] if len(leg_damp) else 0} ×{len(self._leg_idx)}, "
                f"arm K={_ARM_STIFFNESS} D={_ARM_DAMPING} ×{len(self._arm_idx)}"
            )
        except Exception as exc:
            _log(f"gain patch failed (may drift): {exc!r}")

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

        _raw = policy.robot.get_joint_positions()
        if _raw is None:
            policy._policy_counter += 1
            return  # physics simulation view 미준비 — 다음 스텝까지 대기
        all_pos = np.array(_raw, dtype=float)
        if all_pos.ndim != 1 or len(all_pos) < self._n_dofs:
            policy._policy_counter += 1
            return

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
        _rp = p.robot.get_joint_positions()
        _rv = p.robot.get_joint_velocities()
        if _rp is None or _rv is None:
            return np.zeros(48)
        all_pos = np.array(_rp, dtype=float)
        all_vel = np.array(_rv, dtype=float)
        if all_pos.ndim != 1 or all_vel.ndim != 1:
            return np.zeros(48)
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
