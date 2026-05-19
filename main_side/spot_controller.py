"""Spot locomotion controller (in-process, physics-callback driven).

Binds SpotFlatTerrainPolicy to an existing /World/Robot prim (spot, 12-DOF legs).
Called via:
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


_LEG_PREFIXES = ("fl_", "fr_", "hl_", "hr_")
_CMD_TIMEOUT  = 0.5        # seconds — teleop stale → fall through to nav/idle


class SpotController:
    """In-process Spot 12-DOF RL controller bound to an existing stage prim."""

    def __init__(self, prim_path: str):
        from isaacsim.robot.policy.examples.robots import SpotFlatTerrainPolicy

        _log(f"init: binding SpotFlatTerrainPolicy → {prim_path}")
        self._policy = SpotFlatTerrainPolicy(prim_path=prim_path)
        self._first_step = True
        self._initialized = False

        # DOF layout (resolved after first physics step initialize())
        self._n_dofs = 0
        self._leg_idx: Optional[np.ndarray] = None

        # Velocity command state
        self._vel_cmd = np.zeros(3)   # [vx, vy, wz]
        self._vel_ts  = 0.0

        # Nav goal (x, y) world frame — cleared on arrival
        self._nav_goal: Optional[Tuple[float, float]] = None

    # ── command API (called from camera_publisher _apply_cmd) ─────────────

    def set_cmd_vel(self, vx: float, vy: float, wz: float) -> None:
        self._vel_cmd = np.array([vx, vy, wz])
        self._vel_ts  = time.time()

    def set_nav_goal(self, x: float, y: float) -> None:
        self._nav_goal = (x, y)

    def clear_nav_goal(self) -> None:
        self._nav_goal = None

    # ── physics callback ─────────────────────────────────────────────────

    def on_physics_step(self, dt: float) -> None:
        if self._first_step:
            self._first_step = False
            try:
                self._policy.initialize(set_gains=True, set_limits=True)
                self._setup_dof_layout()
            except Exception as exc:
                _log(f"initialize failed: {exc!r}")
            return

        if not self._initialized:
            if self._try_connect_view():
                self._reset_to_standing()
                self._initialized = True
                _log(f"ready — {self._n_dofs} DOFs (legs={len(self._leg_idx)})")
            return

        base_cmd = self._arbitrate()
        self._forward(dt, base_cmd)

    # ── internals ────────────────────────────────────────────────────────

    def _try_connect_view(self) -> bool:
        """physics sim view 가 준비된 시점에 ArticulationView 를 연결.
        play() 직후 첫 callback 에서는 psv 가 None 이므로 매 스텝 재시도."""
        try:
            from isaacsim.core.simulation_manager import SimulationManager
            psv = SimulationManager.get_physics_sim_view()
            if psv is None:
                return False
            view = self._policy.robot._articulation_view
            if view is None:
                return False
            view.initialize(physics_sim_view=psv)
            ok = view.is_physics_handle_valid()
            if ok:
                _log("physics view 연결 완료")
            return ok
        except Exception as exc:
            _log(f"_try_connect_view 실패: {exc!r}")
            return False

    def _reset_to_standing(self) -> None:
        """서있는 자세로 teleport — gp_scene.usd 자동저장으로 넘어진 채 저장된 경우 대비."""
        try:
            robot = self._policy.robot
            default_q = np.asarray(self._policy.default_pos, dtype=float)
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
        """12-DOF leg policy forward step."""
        from isaacsim.core.utils.types import ArticulationAction
        policy = self._policy

        if policy._policy_counter % policy._decimation == 0:
            obs = policy._compute_observation(command)
            action = policy._compute_action(obs)
            policy._previous_action = action.copy()
            policy.action = action

        view = policy.robot._articulation_view
        if view is None or not view.is_physics_handle_valid():
            policy._policy_counter += 1
            return

        all_pos = (np.asarray(policy.default_pos, dtype=float)
                   + policy.action * policy._action_scale)
        policy.robot.apply_action(ArticulationAction(joint_positions=all_pos))
        policy._policy_counter += 1
