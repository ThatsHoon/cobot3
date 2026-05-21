"""Go2 walk-these-ways RL locomotion controller (in-process, physics-callback).

Drop-in replacement for SpotController. Binds the walk-these-ways-go2 two-stage
JIT policy (gait-conditioned-agility/pretrain-go2) to an existing stage prim
referenced to go2.usd.

Called via:  world.add_physics_callback("go2_ctrl", controller.on_physics_step)
Toggle:      GP_SPOT_CONTROL=0 → controller not created (observation-only).

Spec extracted live from the deployment code + parameters_cpu.pkl
(/tmp/wtw_go2, 2026-05-19) — NOT the stale 42/15 reference doc:
  num_observations=70, num_observation_history=30  → adapt input 70*30=2100
  num_privileged_obs(latent)=2  → body input 2100+2=2102 → action 12
  control_type=actuator_net (deploy sends PD targets) kp=20 kd=0.5
  action_scale=0.25  hip_scale_reduction=0.5 (hip idx [0,3,6,9] policy order)
  sim.dt=0.005 decimation=4 → control dt 0.02 (50 Hz)
  obs = grav(3) + cmd*cmd_scale(15) + (q-qdef)*1(12) + qd*0.05(12)
        + clip(act,pm10)(12) + last_act(12) + clock(4)
  body(obs_history(2100) + latent(2)) — NOT current obs.
  default trot cmd: freq=3 phase=0 offset=0 bound=0 duration=0.5
                    footswing=0.08 stance_w=0.33 stance_l=0.40
"""
import math
import os
import time
from typing import Optional, Tuple

import numpy as np

_LOG = "[go2_ctrl]"


def _log(msg: str) -> None:
    print(f"{_LOG} {msg}", flush=True)


_CKPT = os.environ.get(
    "GP_GO2_CKPT",
    "/home/rokey/dev_ws/isaac_sim/cobot3/main_side/go2_policy"
    "/gait-conditioned-agility/pretrain-go2/train/142238.667503/checkpoints",
)

# walk-these-ways policy joint order (deploy lcm_agent.joint_names): per-leg
# grouped leg x (hip,thigh,calf), legs FL,FR,RL,RR. hip idx = 0,3,6,9.
POLICY_JOINTS = [
    "FL_hip_joint", "FL_thigh_joint", "FL_calf_joint",
    "FR_hip_joint", "FR_thigh_joint", "FR_calf_joint",
    "RL_hip_joint", "RL_thigh_joint", "RL_calf_joint",
    "RR_hip_joint", "RR_thigh_joint", "RR_calf_joint",
]
DEFAULT_ANGLES = {
    "FL_hip_joint": 0.1,  "FL_thigh_joint": 0.8, "FL_calf_joint": -1.5,
    "FR_hip_joint": -0.1, "FR_thigh_joint": 0.8, "FR_calf_joint": -1.5,
    "RL_hip_joint": 0.1,  "RL_thigh_joint": 1.0, "RL_calf_joint": -1.5,
    "RR_hip_joint": -0.1, "RR_thigh_joint": 1.0, "RR_calf_joint": -1.5,
}
_HIP_POLICY_IDX = [0, 3, 6, 9]

# walk-these-ways 는 Unitree go2.urdf 컨벤션 학습본. NVIDIA go2.usd 의
# hip(abduction) 조인트 축이 반대 → 정책↔sim 사이 hip 부호 반전 필요.
# 근거: deploy lcm_agent.publish_action 의 주석 토글
#   # self.joint_pos_target[[0,3,6,9]] *= -1
# 증상: 기립은 안정(grav z≈-1)인데 직진 불가·표류/선회 = abduction 비대칭.
# 부호벡터 S(policy 순서): hip=-1, 그 외 +1. read(q,qd)·write(torque) 양쪽
# 대칭 적용 → 정책은 학습 컨벤션, sim 은 go2.usd 컨벤션 유지.
# 실측: hip 부호 반전 시 정책이 전복(grav z→+1) → 가설 기각. 기본 off
# (=항등). 부호 컨벤션은 hip 단순반전이 아님 — 더 깊은 asset 캘리브 필요.
_HIPFLIP = os.environ.get("GP_GO2_HIPFLIP", "0") == "1"
_SGN = np.ones(12, dtype=np.float32)
if _HIPFLIP:
    for _h in _HIP_POLICY_IDX:
        _SGN[_h] = -1.0

NUM_OBS = 70
HIST_LEN = 30
OBS_HIST = NUM_OBS * HIST_LEN          # 2100
NUM_CMD = 15
ACTION_SCALE = 0.25
HIP_SCALE = 0.5
CLIP_ACTIONS = 10.0
CONTROL_DT = 0.02                      # 50 Hz (sim.dt 0.005 x decimation 4)
DOF_POS_SCALE = 1.0
DOF_VEL_SCALE = 0.05

# control_type=actuator_net: 정책은 PD 가 아니라 학습된 Unitree Go1
# actuator network 로 토크를 만든다(파라미터 stiffness/damping 미사용).
# 입력(관절당 6): [pos_err, pos_err_l, pos_err_ll, vel, vel_l, vel_ll]
# pos_err = dof_pos - joint_pos_target. 매 physics substep 평가 + 히스토리 갱신.
_ACTUATOR_NET = os.environ.get(
    "GP_GO2_ACTNET",
    "/home/rokey/dev_ws/isaac_sim/cobot3/main_side/go2_policy"
    "/unitree_go1_actuator.pt")
# go2.urdf effort limit: hip/thigh 23.7, calf 35.55 (POLICY per-leg 순서
# [hip,thigh,calf]x4 → idx%3: 0=hip 1=thigh 2=calf)
TORQUE_LIMIT = np.array([23.7, 23.7, 35.55] * 4, dtype=np.float32)

# commands_scale[:15] (lcm_agent): lin_vel,lin_vel,ang_vel,body_height_cmd,
# 1,1,1,1,1, footswing_height_cmd, body_pitch_cmd, body_roll_cmd,
# stance_width_cmd, stance_length_cmd  (+aux trailing, sliced to 15)
CMD_SCALE = np.array(
    [2.0, 2.0, 0.25, 2.0, 1.0, 1.0, 1.0, 1.0, 1.0,
     0.15, 0.3, 0.3, 1.0, 1.0, 1.0], dtype=np.float32)

# default trot command (StateEstimator.get_command default / 'else' branch).
# idx: 0vx 1vy 2vyaw 3height 4freq 5phase 6offset 7bound 8duration
#      9footswing 10pitch 11roll 12stance_w 13stance_l 14aux
# phase=0.5 → 대각쌍 교대 = TROT (효율적 전진).
# phase=offset=bound=0 이면 4발 동위상 = PRONK(제자리 점프) → 비효율.
# foot_indices=[g+ph+of+bd, g+of, g+bd, g+ph]; ph=0.5 → {0,3}↔{1,2} 교대.
_CMD_BASE = np.array(
    [0.0, 0.0, 0.0, 0.0, 3.6, 0.5, 0.0, 0.0, 0.45,
     0.15, 0.0, 0.0, 0.33, 0.40, 0.0], dtype=np.float32)
# (idx4 step_freq 3.2→3.6: 빠른 속도 지원 위해 다리 주기 상향)
# 역동 튜닝(학습 분포 내): freq 3.0→3.2(빠른 스텝), duration 0.5→0.45
# (체공↑ 역동), footswing 0.12→0.15(발 높이↑ 과감). phase 0.5=trot 유지.

_CMD_TIMEOUT = 0.5     # s - teleop stale -> nav/idle
# ready 후 nav 개입 전 제자리 안정화 정책틱 수 (zero-history 트랜지언트
# + 기립 안정화). 50Hz 기준 ~20s. 라이브 실측: ~700-900틱에 직진 안정화.
_SETTLE_STEPS = int(os.environ.get("GP_GO2_SETTLE", "1000"))
# 최대 전진속도(m/s). 학습 샘플링은 [-1,1] 이나 limit_vel_x=[-5,5] 라
# 그 이상도 가능(분포 밖 → 거친 지형서 다소 불안정 가능). env 로 조정.
_MAX_VX = float(os.environ.get("GP_GO2_MAX_VX", "1.6"))
_VX_LIM = (-_MAX_VX, _MAX_VX)
_VY_LIM = (-0.6, 0.6)
_WZ_LIM = (-1.0, 1.0)
# 도착 판정: 목표(Cone) 중심 기준 사각형 범위(half-extent, m).
# |dx|<X and |dy|<Y 면 도착으로 간주(원형 반경 대신 사각 영역).
_ARRIVE_X = float(os.environ.get("GP_GO2_ARRIVE_X", "0.6"))
_ARRIVE_Y = float(os.environ.get("GP_GO2_ARRIVE_Y", "0.6"))
# 내부 nav_goal P-제어 활성 여부. Nav2 외부 스택을 쓸 때는 GP_GO2_NAV=0 으로
# 비활성 — Nav2 → cmd_vel_safety_filter → /robot/cmd_vel → set_cmd_vel 경로만 사용.
_NAV_ENABLED = os.environ.get("GP_GO2_NAV", "1") != "0"


def _match(a: str, b: str) -> bool:
    a, b = a.lower(), b.lower()
    return a == b or a.endswith(b) or b.endswith(a)


def _proj_gravity(qw, qx, qy, qz) -> np.ndarray:
    """legged_gym quat_rotate_inverse(base_quat, [0,0,-1]) -> projected gravity
    in body frame. Isaac get_world_pose() quat is (w,x,y,z)."""
    v = np.array([0.0, 0.0, -1.0])
    qvec = np.array([qx, qy, qz])
    a = v * (2.0 * qw * qw - 1.0)
    b = np.cross(qvec, v) * (2.0 * qw)
    c = qvec * (2.0 * np.dot(qvec, v))
    return a - b + c


class Go2WtwController:
    """In-process Go2 12-DOF walk-these-ways RL controller."""

    def __init__(self, prim_path: str):
        import torch

        self._torch = torch
        self._prim = prim_path
        self._art = None
        self._first_step = True
        self._ready = False

        self._decim = 10                 # set from real dt on first step
        self._phys_ctr = 0
        self._step_n = 0

        # teleop / nav
        self._vel_cmd = np.zeros(3)      # [vx, vy, wz]
        self._vel_ts = 0.0
        self._nav_goal: Optional[Tuple[float, float]] = None

        # policy state
        self._obs_hist = torch.zeros(1, OBS_HIST, dtype=torch.float32)
        self._actions = torch.zeros(1, 12, dtype=torch.float32)
        self._last_actions = torch.zeros(1, 12, dtype=torch.float32)
        self._clock = np.zeros(4, dtype=np.float32)
        self._gait_idx = 0.0

        # actuator-net 토크 제어 상태 (policy 순서, 12)
        self._jpt = None                 # joint_pos_target, 정책틱마다 갱신
        self._pe_l = np.zeros(12, dtype=np.float32)   # pos_err last
        self._pe_ll = np.zeros(12, dtype=np.float32)  # pos_err last_last
        self._v_l = np.zeros(12, dtype=np.float32)    # vel last
        self._v_ll = np.zeros(12, dtype=np.float32)   # vel last_last

        # fall 감지 + 자동 기립 상태 머신 (2026-05-21)
        # walk-these-ways 는 누운 상태 OOD → PD 스크립트로 4-stage 기립.
        self._fall_up_z = 1.0            # smoothed up axis (직립=1.0, 누움≈0)
        self._fallen = False
        self._fall_since: Optional[float] = None      # 첫 감지 시각
        self._recovering = False
        self._recover_t0: Optional[float] = None      # 시퀀스 시작 시각
        self._recover_kps_active = False              # gains 일시 변경 여부
        self._last_fall_event = ""                    # IPC dedup
        # FALL 임계값(직립=up_z=1.0) — 0.4 이하 1초 지속 시 fall, 0.85 이상 0.5초 복구
        self._FALL_ENTER_UPZ = 0.40
        self._FALL_ENTER_DUR = 1.0
        self._FALL_EXIT_UPZ  = 0.85
        # 4-stage 기립 시퀀스 (총 ≈3.2s). 각 stage 의 (duration, [hip,thigh,calf])
        # 정책 순서 [FL_hip,FL_thigh,FL_calf, FR_*, RL_*, RR_*] 모두 동일 패턴.
        self._RECOVER_STAGES = [
            (0.8, ( 0.00,  2.50, -2.50)),   # 1) tuck: 다리를 몸 아래로 접음
            (0.8, ( 0.00,  1.60, -2.00)),   # 2) push: 몸을 들어올림
            (0.8, ( 0.10,  1.10, -1.90)),   # 3) spread: 4발 정렬
            (0.8, ( 0.00,  0.90, -1.80)),   # 4) stand: 보행 자세 (≈DEFAULT_ANGLES)
        ]
        self._RECOVER_TIMEOUT = 5.0       # 시퀀스 후에도 미직립 → teleport fallback

        # 외부 stance/height 오버라이드 (사격 시 ramp 용, 2026-05-21).
        # _CMD_BASE 의 idx 3=body_height, 12=stance_w, 13=stance_l 에 가산.
        self._stance_override = {"body_height": 0.0, "stance_w": 0.0,
                                 "stance_l": 0.0}

        _log(f"init: walk-these-ways-go2 -> {prim_path}")
        self._adapt = torch.jit.load(_CKPT + "/adaptation_module_latest.jit")
        self._body = torch.jit.load(_CKPT + "/body_latest.jit")
        self._adapt.train(False)
        self._body.train(False)
        # actuator net (CUDA 저장본 → cpu 매핑)
        self._actnet = torch.jit.load(_ACTUATOR_NET, map_location="cpu")
        self._actnet.train(False)
        with torch.no_grad():
            lat = self._adapt(torch.zeros(1, OBS_HIST))
        self._latent_dim = int(lat.shape[-1])
        _log(f"JIT loaded - latent_dim={self._latent_dim} (expect 2), "
             f"actuator_net OK")

    # -- command API (called from camera_publisher._apply_cmd) -------------

    def set_cmd_vel(self, vx: float, vy: float, wz: float) -> None:
        self._vel_cmd = np.array([
            float(np.clip(vx, *_VX_LIM)),
            float(np.clip(vy, *_VY_LIM)),
            float(np.clip(wz, *_WZ_LIM)),
        ])
        self._vel_ts = time.time()

    def set_stance_override(self, body_height: float = 0.0,
                            stance_w: float = 0.0,
                            stance_l: float = 0.0) -> None:
        """사격·정밀작업 등 외부 자세 ramp 명령. _command() 가 _CMD_BASE 의
        idx 3/12/13 에 가산. 0,0,0 호출로 해제."""
        self._stance_override["body_height"] = float(body_height)
        self._stance_override["stance_w"] = float(stance_w)
        self._stance_override["stance_l"] = float(stance_l)

    def apply_external_impulse(self, force_world: tuple,
                               position_world: tuple,
                               torque_world: tuple = (0.0, 0.0, 0.0)) -> bool:
        """사격 반동 등 1-step 외부 힘. articulation.apply_action 이 정책
        토크와 함께 적용되므로 매우 짧은 펄스만 가능. 호출 직후 1 step 만
        인가됨. 반환 True=성공."""
        try:
            from isaacsim.core.utils.types import ArticulationAction
            # _apply_actuator 의 torque 와 합산해서 인가 (사격 임펄스를
            # 정책 토크에 더하는 방식). joint_efforts 가 아닌 별도 외부 force
            # API: dynamic_control 이 더 명확.
            from omni.isaac.dynamic_control import _dynamic_control
            dc = _dynamic_control.acquire_dynamic_control_interface()
            base = dc.get_rigid_body(self._art_root if hasattr(self, '_art_root')
                                     else self._prim)
            if not base:
                return False
            # 월드 좌표 기준 force + position 적용
            dc.apply_body_force(base, position_world, force_world, True)
            if any(abs(t) > 1e-6 for t in torque_world):
                dc.apply_body_torque(base, torque_world, True)
            return True
        except Exception as exc:
            _log(f"impulse 인가 실패: {exc!r}")
            return False

    def set_nav_goal(self, x: float, y: float) -> None:
        if not _NAV_ENABLED:
            _log(f"set_nav_goal({x:.2f},{y:.2f}) 무시: GP_GO2_NAV=0")
            return
        self._nav_goal = (x, y)

    def clear_nav_goal(self) -> None:
        self._nav_goal = None

    # -- physics callback -------------------------------------------------

    def on_physics_step(self, dt: float) -> None:
        if self._first_step:
            self._first_step = False
            self._decim = max(1, int(round(CONTROL_DT / max(dt, 1e-6))))
            # 라이브 GUI 주입 경로: 호출자가 동기 컨텍스트에서 미리
            # bind+initialize 한 _art 를 주입했으면 그대로 사용
            # (physx 콜백 내 initialize() 는 그 컨텍스트에서 실패함).
            if self._art is None:
                try:
                    from isaacsim.core.prims import SingleArticulation
                    self._art = SingleArticulation(prim_path=self._prim)
                    self._art.initialize()
                except Exception as exc:
                    _log(f"initialize failed: {exc!r}")
            return

        if not self._ready:
            if self._setup():
                self._ready = True
                self._ready_step = self._step_n
                _log(f"ready - decimation={self._decim} "
                     f"(ctrl~{1.0 / (self._decim * dt):.0f} Hz)")
            return

        # 정책: decim(=4 @200Hz → 50Hz)마다 joint_pos_target 갱신
        if self._phys_ctr % self._decim == 0:
            self._policy_tick()
        # 복구 중에는 actuator_net 우회(PD position drive 가 servo 함). 그 외엔 정상.
        if not self._recovering:
            self._apply_actuator()
        self._phys_ctr += 1

    # -- setup ------------------------------------------------------------

    def _discover_root(self) -> Optional[str]:
        """go2.usd 의 ArticulationRoot 가 self._prim 와 다른 경로에 컴포즈될 수
        있어(스폿과 구조 다름) 서브트리에서 실제 root 를 탐색."""
        try:
            import omni.usd
            from pxr import Usd, UsdPhysics
            stage = omni.usd.get_context().get_stage()
            base = stage.GetPrimAtPath(self._prim)
            if not base or not base.IsValid():
                return None
            tree, root = [], None
            for p in Usd.PrimRange(base):
                pp = str(p.GetPath())
                apis = p.GetAppliedSchemas()
                tag = ""
                if p.HasAPI(UsdPhysics.ArticulationRootAPI):
                    tag = " <ARTROOT>"
                    if root is None:
                        root = pp
                if len(tree) < 60:
                    tree.append(f"  {pp} [{p.GetTypeName()}]"
                                f"{(' ' + ','.join(apis)) if apis else ''}{tag}")
            with open('/tmp/go2_step.txt', 'a') as f:
                f.write(f"[tree {self._prim}] root={root}\n"
                        + "\n".join(tree) + "\n")
            return root
        except Exception as exc:
            _log(f"_discover_root err: {exc!r}")
            return None

    def _setup(self) -> bool:
        try:
            names = list(self._art.dof_names or [])
            if len(names) < 12:
                if not getattr(self, "_discovered", False):
                    self._discovered = True
                    root = self._discover_root()
                    if root and root != self._prim:
                        _log(f"articulation root 재바인딩: {self._prim} -> {root}")
                        try:
                            from isaacsim.core.prims import SingleArticulation
                            self._art = SingleArticulation(prim_path=root)
                            self._art.initialize()
                            self._art_root = root
                        except Exception as exc:
                            _log(f"rebind init err: {exc!r}")
                return False
            p2s = [None] * 12
            for pi, pn in enumerate(POLICY_JOINTS):
                for si, sn in enumerate(names):
                    if _match(sn, pn):
                        p2s[pi] = si
                        break
            if None in p2s:
                _log(f"joint map incomplete: {list(zip(POLICY_JOINTS, p2s))}")
                return False
            self._p2s = p2s
            self._n_dofs = len(names)
            self._default_policy = np.array(
                [DEFAULT_ANGLES[j] for j in POLICY_JOINTS], dtype=np.float32)
            self._default_sim = np.zeros(self._n_dofs, dtype=np.float32)
            for pi, si in enumerate(p2s):
                self._default_sim[si] = self._default_policy[pi]

            try:
                # actuator_net 토크 제어 → Isaac 내부 PD 비활성(0/0)
                ctrl = self._art.get_articulation_controller()
                ctrl.set_gains(kps=np.zeros(self._n_dofs),
                               kds=np.zeros(self._n_dofs))
            except Exception as exc:
                _log(f"set_gains warn: {exc!r}")

            # ── 진단(1회): 조인트 순서·게인 적용 검증 ──────────────
            try:
                _gk = _gd = None
                try:
                    _g = self._art.get_articulation_controller().get_gains()
                    _gk, _gd = _g[0], _g[1]
                except Exception as _e:
                    _gk = f"get_gains err {_e!r}"
                with open('/tmp/go2_diag.txt', 'w') as _f:
                    _f.write(f"dof_names({self._n_dofs})={names}\n")
                    _f.write(f"POLICY_JOINTS={POLICY_JOINTS}\n")
                    _f.write(f"p2s(policy->sim)={p2s}\n")
                    _f.write(f"default_policy={self._default_policy.tolist()}\n")
                    _f.write(f"default_sim={self._default_sim.tolist()}\n")
                    _f.write(f"applied kps={np.asarray(_gk).tolist() if _gk is not None and not isinstance(_gk,str) else _gk}\n")
                    _f.write(f"applied kds={np.asarray(_gd).tolist() if _gd is not None and not isinstance(_gd,str) else _gd}\n")
                self._diag_ticks = 0
            except Exception as _e:
                _log(f"diag dump err: {_e!r}")

            self._reset_stand()
            return True
        except Exception as exc:
            _log(f"_setup retry ({exc!r})")
            return False

    def _reset_stand(self) -> None:
        try:
            self._art.set_joint_positions(self._default_sim.copy())
            self._art.set_joint_velocities(np.zeros(self._n_dofs))
            pos, ori = self._art.get_world_pose()
            if float(pos[2]) < 0.30:
                self._art.set_world_pose(
                    position=np.array([float(pos[0]), float(pos[1]), 0.42]),
                    orientation=ori)
                _log(f"base Z {float(pos[2]):.3f} -> 0.42")
        except Exception as exc:
            _log(f"reset_stand warn: {exc!r}")

    # -- arbitration ------------------------------------------------------

    def _command(self) -> np.ndarray:
        cmd = _CMD_BASE.copy()
        # 캘리브레이션: GP_GO2_CMD_MODE=cal → 순수 직진(vx=0.5,wz=0).
        if os.environ.get("GP_GO2_CMD_MODE") == "cal":
            cmd[0], cmd[1], cmd[2] = 0.5, 0.0, 0.0
            if self._nav_goal is not None:
                self._nav_p_ctrl()
            return cmd
        active_teleop = (time.time() - self._vel_ts < _CMD_TIMEOUT
                         and np.any(np.abs(self._vel_cmd) > 1e-6))
        if active_teleop:
            cmd[0], cmd[1], cmd[2] = self._vel_cmd
        elif _NAV_ENABLED and self._nav_goal is not None:
            if (self._step_n - getattr(self, "_ready_step", 0)) < _SETTLE_STEPS:
                # idle 기립 (안정화 대기) — 아래 standstill clamp 으로 fallthrough
                pass
            else:
                vx, vy, wz = self._nav_p_ctrl()
                cmd[0], cmd[1], cmd[2] = vx, vy, wz
                return cmd
        # standstill clamp (2026-05-20 fix) — teleop/nav 모두 비활성이면
        # _CMD_BASE 의 stepping gait (freq 3.6, footswing 0.15) 가 zero cmd 인데도
        # 다리를 들어 yaw drift 누적 (원형 궤적). freq=0 + footswing=0 으로
        # 다리 안 들고 완전 stance 유지 → drift 차단.
        # idx 4=step_freq, idx 9=footswing
        if not active_teleop:
            cmd[4] = 0.0    # step frequency = 0 → 다리 stepping 없음
            cmd[9] = 0.0    # footswing height = 0 → 발 안 들음
        # 외부 stance override (사격 ramp 등, 2026-05-21).
        # idx 3=body_height, 12=stance_w, 13=stance_l
        so = self._stance_override
        cmd[3] += so["body_height"]
        cmd[12] += so["stance_w"]
        cmd[13] += so["stance_l"]
        return cmd

    def _nav_p_ctrl(self):
        try:
            pos, quat = self._art.get_world_pose()
        except Exception:
            return 0.0, 0.0, 0.0
        gx, gy = self._nav_goal
        dx, dy = gx - float(pos[0]), gy - float(pos[1])
        dist = math.hypot(dx, dy)
        # 도착 = Cone 중심 기준 사각형 범위(±_ARRIVE_X, ±_ARRIVE_Y) 내
        if abs(dx) < _ARRIVE_X and abs(dy) < _ARRIVE_Y:
            self._nav_goal = None
            _log(f"nav_goal reached (box dx={dx:.2f} dy={dy:.2f})")
            return 0.0, 0.0, 0.0
        w, x, y, z = (float(quat[0]), float(quat[1]),
                      float(quat[2]), float(quat[3]))
        # quat→yaw (Z). 정상상태 실측: walk-these-ways 전진(vx>0)은 raw
        # quaternion yaw 방향 (오프셋 없음).
        ryaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
        tyaw = math.atan2(dy, dx)
        err = math.atan2(math.sin(tyaw - ryaw), math.cos(tyaw - ryaw))
        vx = min(_MAX_VX, 0.8 * dist) if abs(err) < 0.4 else 0.0
        wz = max(-1.0, min(1.0, 2.0 * err))
        # 진단: ryaw vs 실제 이동방향(move heading) 직접 대조 (100틱마다)
        _nd = getattr(self, "_navdiag_n", 0)
        self._navdiag_n = _nd + 1
        if _nd % 100 == 0:
            try:
                px, py = float(pos[0]), float(pos[1])
                pp = getattr(self, "_navdiag_prev", None)
                mh = None
                if pp is not None:
                    mdx, mdy = px - pp[0], py - pp[1]
                    if (mdx * mdx + mdy * mdy) > 1e-6:
                        mh = math.degrees(math.atan2(mdy, mdx))
                self._navdiag_prev = (px, py)
                with open('/tmp/go2_nav_diag.txt', 'a') as _f:
                    _f.write(
                        f"pos=[{px:.2f},{py:.2f}] goal=[{gx:.2f},{gy:.2f}] "
                        f"dist={dist:.2f} ryaw={math.degrees(ryaw):.1f} "
                        f"tyaw={math.degrees(tyaw):.1f} "
                        f"err={math.degrees(err):.1f} "
                        f"move_hdg={('%.1f' % mh) if mh is not None else 'NA'} "
                        f"vx={vx:.2f} wz={wz:.2f}\n")
            except Exception:
                pass
        return vx, 0.0, wz

    # -- policy -----------------------------------------------------------

    def _policy_tick(self) -> None:
        torch = self._torch
        try:
            pos_sim = np.asarray(self._art.get_joint_positions(), dtype=float)
            vel_sim = np.asarray(self._art.get_joint_velocities(), dtype=float)
            _, quat = self._art.get_world_pose()      # (w,x,y,z)

            p2s = self._p2s
            # sim→policy 컨벤션: hip 부호 반전(_SGN)
            q = np.array([pos_sim[p2s[i]] for i in range(12)],
                         dtype=np.float32) * _SGN
            qd = np.array([vel_sim[p2s[i]] for i in range(12)],
                          dtype=np.float32) * _SGN
            grav = _proj_gravity(
                float(quat[0]), float(quat[1]),
                float(quat[2]), float(quat[3])).astype(np.float32)

            # FALL 감지·복구 (정책 obs 계산 전에 분기 — 복구 중이면 PD 시퀀스 실행).
            if self._tick_fall_recover(grav):
                self._step_n += 1
                return

            cmd = self._command()
            cmd_scaled = cmd * CMD_SCALE

            act_clip = np.clip(
                self._actions.numpy().ravel(), -CLIP_ACTIONS, CLIP_ACTIONS)
            last_clip = np.clip(
                self._last_actions.numpy().ravel(), -CLIP_ACTIONS, CLIP_ACTIONS)

            obs = np.concatenate([
                grav,                                          # 3
                cmd_scaled,                                    # 15
                (q - self._default_policy) * DOF_POS_SCALE,    # 12
                qd * DOF_VEL_SCALE,                            # 12
                act_clip,                                      # 12
                last_clip,                                     # 12
                self._clock,                                   # 4
            ]).astype(np.float32)                              # = 70

            obs_t = torch.from_numpy(obs).unsqueeze(0)
            self._obs_hist = torch.cat(
                [self._obs_hist[:, NUM_OBS:], obs_t], dim=-1)

            with torch.no_grad():
                latent = self._adapt(self._obs_hist)
                raw = self._body(torch.cat([self._obs_hist, latent], dim=-1))

            self._last_actions = self._actions
            self._actions = torch.clip(raw[:, :12], -CLIP_ACTIONS, CLIP_ACTIONS)

            # joint_pos_target (policy 순서) — actuator net 이 매 substep 추종.
            acts = self._actions.numpy().ravel() * ACTION_SCALE
            for h in _HIP_POLICY_IDX:
                acts[h] *= HIP_SCALE
            self._jpt = (acts + self._default_policy).astype(np.float32)
            tgt_policy = self._jpt

            self._advance_gait(cmd)

            self._step_n += 1
            # 진단: gait 동작 여부 — clock 진동·action 크기·calf(스텝
            # 지표)·base 선속도. 정책이 게이트를 내는지 vs 균형만 하는지.
            if self._step_n <= 25 or self._step_n % 97 == 2:
                try:
                    blv = self._art.get_linear_velocity()
                    blv = [round(float(v), 3) for v in np.asarray(blv).ravel()[:3]]
                except Exception:
                    blv = "NA"
                with open('/tmp/go2_gait.txt', 'a') as _gf:
                    _gf.write(
                        f"t{self._step_n} clk={np.round(self._clock,3).tolist()} "
                        f"|act|max={float(np.max(np.abs(self._actions.numpy()))):.2f} "
                        f"calf(q2,5,8,11)="
                        f"{[round(float(q[i]),3) for i in (2,5,8,11)]} "
                        f"base_vel={blv} "
                        f"cmd_vx={float(cmd[0]):.2f} gidx={self._gait_idx:.3f}\n")
            # 진단: 첫 6틱 + 이후 200틱마다 raw action·target·실측 q 덤프
            _dt = getattr(self, "_diag_ticks", None)
            if _dt is not None and (_dt < 6 or self._step_n % 200 == 1):
                self._diag_ticks = _dt + 1
                with open('/tmp/go2_diag.txt', 'a') as _f:
                    _f.write(
                        f"[t{self._step_n}] grav={grav.round(3).tolist()} "
                        f"q={q.round(3).tolist()} "
                        f"raw_act={self._actions.numpy().ravel().round(3).tolist()} "
                        f"tgt_pol={tgt_policy.round(3).tolist()}\n")
            if self._step_n % 100 == 1:
                _pos, _ = self._art.get_world_pose()
                _log(f"step={self._step_n} cmd={cmd[:3].round(2).tolist()} "
                     f"grav={grav.round(2).tolist()} "
                     f"pos={[round(float(v),2) for v in _pos]} "
                     f"gait_idx={self._gait_idx:.2f}")
        except Exception as exc:
            if self._step_n % 500 == 0:
                _log(f"policy_tick err: {exc!r}")
            self._step_n += 1

    # -- fall 감지 + 자동 기립 ------------------------------------------------

    def _write_fall_ipc(self, state: str, up_z: float,
                        stage: Optional[int] = None) -> None:
        """fall_relay 가 mtime 폴 + content 변화 시 ROS 발행. dedup 으로 IO 절약."""
        import json as _json
        evt = f"{state}|{stage if stage is not None else ''}"
        # state 변화 또는 stage 변화 시에만 기록 (heartbeat 는 별도 2Hz 로직 외부)
        if evt == self._last_fall_event:
            return
        self._last_fall_event = evt
        try:
            try:
                pos, _ = self._art.get_world_pose()
                px, py, pz = (float(pos[0]), float(pos[1]), float(pos[2]))
            except Exception:
                px = py = pz = 0.0
            payload = {
                "ts": time.time(),
                "state": state,        # "UPRIGHT" | "FALLEN" | "RECOVERING" | "RECOVERED"
                "up_z": float(up_z),
                "stage": stage,        # 0..3 in RECOVERING, else null
                "pose": {"x": px, "y": py, "z": pz},
            }
            with open('/tmp/cobot3_fall_state.json.tmp', 'w') as _f:
                _json.dump(payload, _f)
            os.replace('/tmp/cobot3_fall_state.json.tmp',
                       '/tmp/cobot3_fall_state.json')
        except Exception as exc:
            _log(f"fall IPC write err: {exc!r}")

    def _tick_fall_recover(self, grav: np.ndarray) -> bool:
        """매 정책 tick(50Hz) 호출.
        반환 True = 복구 시퀀스 진행 중 → 호출자가 일반 정책 obs/action 스킵.
        반환 False = 정상 보행 모드."""
        # up_z: -grav[2] 이 직립=1.0, 누움≈0. EMA smoothing 으로 잡음 억제.
        up_z = float(-grav[2])
        self._fall_up_z = 0.85 * self._fall_up_z + 0.15 * up_z
        smoothed = self._fall_up_z

        now = time.time()

        # 1) 복구 중이면 시퀀스 진행
        if self._recovering:
            self._run_recover_stage(now, smoothed)
            return True

        # 2) 직립 상태 — fall 진입 판정
        if smoothed >= self._FALL_EXIT_UPZ:
            if self._fallen:
                # 자체적으로 회복(외부 도움) — 알람만 해제
                self._fallen = False
                self._fall_since = None
                self._write_fall_ipc("UPRIGHT", smoothed)
            return False

        # 3) 임계값 이하 — 1초 지속 판정
        if smoothed < self._FALL_ENTER_UPZ:
            if self._fall_since is None:
                self._fall_since = now
            elif (now - self._fall_since) >= self._FALL_ENTER_DUR \
                    and not self._fallen:
                self._fallen = True
                _log(f"FALL 감지 (up_z={smoothed:.2f}) → 자동 기립 시퀀스 시작")
                self._write_fall_ipc("FALLEN", smoothed)
                self._begin_recovery(now)
                return True
        else:
            # 회색지대(0.4~0.85) — 카운터 초기화
            self._fall_since = None
        return False

    def _begin_recovery(self, now: float) -> None:
        """복구 시퀀스 시작: gains 를 PD position-drive 용으로 강화 + flags."""
        self._recovering = True
        self._recover_t0 = now
        # actuator_net 우회 + Isaac 내부 PD 활성. kps 강함 / kds 적당.
        try:
            ctrl = self._art.get_articulation_controller()
            ctrl.set_gains(
                kps=np.full(self._n_dofs, 80.0, dtype=np.float32),
                kds=np.full(self._n_dofs, 2.0, dtype=np.float32))
            self._recover_kps_active = True
        except Exception as exc:
            _log(f"recover set_gains err: {exc!r}")
        # 0 속도로 시작
        try:
            self._art.set_joint_velocities(np.zeros(self._n_dofs))
        except Exception:
            pass
        self._write_fall_ipc("RECOVERING", self._fall_up_z, stage=0)

    def _end_recovery(self, success: bool, up_z: float) -> None:
        """복구 종료: gains 원복(actuator_net 토크 모드) + flags + IPC."""
        self._recovering = False
        self._recover_t0 = None
        try:
            ctrl = self._art.get_articulation_controller()
            ctrl.set_gains(
                kps=np.zeros(self._n_dofs, dtype=np.float32),
                kds=np.zeros(self._n_dofs, dtype=np.float32))
            self._recover_kps_active = False
        except Exception as exc:
            _log(f"recover restore gains err: {exc!r}")
        # 정책 history 재설정 — 누운 채로 쌓인 obs 가 보행 정책을 교란하므로
        # zero 로 reset 후 default_policy 자세에서 재시작.
        try:
            torch = self._torch
            self._obs_hist = torch.zeros(1, OBS_HIST, dtype=torch.float32)
            self._actions = torch.zeros(1, 12, dtype=torch.float32)
            self._last_actions = torch.zeros(1, 12, dtype=torch.float32)
            self._pe_l[:] = 0
            self._pe_ll[:] = 0
            self._v_l[:] = 0
            self._v_ll[:] = 0
            self._jpt = None
        except Exception:
            pass
        if success:
            self._fallen = False
            self._fall_since = None
            _log(f"FALL 복구 성공 (up_z={up_z:.2f})")
            self._write_fall_ipc("RECOVERED", up_z)
        else:
            # 시퀀스 실패 → sim teleport fallback (시연용 — 실로봇 배포 시 제거)
            _log(f"FALL 복구 실패 (up_z={up_z:.2f}) → teleport reset fallback")
            self._reset_stand_upright()
            self._fallen = False
            self._fall_since = None
            self._write_fall_ipc("RECOVERED", 1.0)

    def _run_recover_stage(self, now: float, up_z: float) -> None:
        """시퀀스 stage 진행. 각 stage 동일 패턴을 4 다리에 적용."""
        elapsed = now - (self._recover_t0 or now)
        # 시퀀스 누적 종료 시점 계산
        acc = 0.0
        stage_idx = None
        stage_target = None
        for i, (dur, tgt) in enumerate(self._RECOVER_STAGES):
            if elapsed < acc + dur:
                stage_idx = i
                stage_target = tgt
                break
            acc += dur
        # 시퀀스 끝 — 직립 검사
        if stage_idx is None:
            if up_z >= self._FALL_EXIT_UPZ:
                self._end_recovery(success=True, up_z=up_z)
                return
            # 5초 timeout 초과 시 teleport fallback
            if elapsed >= self._RECOVER_TIMEOUT:
                self._end_recovery(success=False, up_z=up_z)
                return
            # 마지막 stand 자세 유지하며 대기
            stage_idx = len(self._RECOVER_STAGES) - 1
            stage_target = self._RECOVER_STAGES[-1][1]

        # 4 다리에 동일 (hip, thigh, calf) 패턴 — policy 순서에 맞춰 12-vec 구성
        hip_t, thigh_t, calf_t = stage_target
        tgt_policy = np.empty(12, dtype=np.float32)
        for leg in range(4):
            tgt_policy[leg * 3 + 0] = hip_t
            tgt_policy[leg * 3 + 1] = thigh_t
            tgt_policy[leg * 3 + 2] = calf_t
        # policy→sim 매핑 + hip 부호 반전(_SGN)
        tgt_policy_signed = tgt_policy * _SGN
        tgt_sim = self._default_sim.copy()
        for pi, si in enumerate(self._p2s):
            tgt_sim[si] = tgt_policy_signed[pi]

        try:
            from isaacsim.core.utils.types import ArticulationAction
            self._art.apply_action(
                ArticulationAction(joint_positions=tgt_sim))
        except Exception as exc:
            if int(elapsed * 50) % 50 == 0:
                _log(f"recover apply err: {exc!r}")

        # stage 변화 시 IPC 발행 (dedup)
        self._write_fall_ipc("RECOVERING", up_z, stage=stage_idx)

    def _reset_stand_upright(self) -> None:
        """실패 fallback — yaw 보존, roll/pitch=0 + base z=0.42 + default joints.
        sim-only 비물리 teleport. 실로봇은 RL recovery 정책 또는 사람 개입."""
        try:
            self._art.set_joint_positions(self._default_sim.copy())
            self._art.set_joint_velocities(np.zeros(self._n_dofs))
            pos, ori = self._art.get_world_pose()
            # ori 에서 yaw 만 추출 → roll/pitch 0 인 quat 재구성
            w, x, y, z = (float(ori[0]), float(ori[1]),
                          float(ori[2]), float(ori[3]))
            yaw = math.atan2(2.0 * (w * z + x * y),
                             1.0 - 2.0 * (y * y + z * z))
            qw = math.cos(yaw / 2.0)
            qz = math.sin(yaw / 2.0)
            self._art.set_world_pose(
                position=np.array([float(pos[0]), float(pos[1]), 0.42]),
                orientation=np.array([qw, 0.0, 0.0, qz]))
        except Exception as exc:
            _log(f"reset_stand_upright err: {exc!r}")

    def _advance_gait(self, cmd: np.ndarray) -> None:
        freq = float(cmd[4])
        phase = float(cmd[5])
        offset = float(cmd[6])
        bound = float(cmd[7])
        self._gait_idx = (self._gait_idx + CONTROL_DT * freq) % 1.0
        fi = [
            self._gait_idx + phase + offset + bound,
            self._gait_idx + offset,
            self._gait_idx + bound,
            self._gait_idx + phase,
        ]
        self._clock = np.array(
            [math.sin(2.0 * math.pi * v) for v in fi], dtype=np.float32)

    def _apply_actuator(self) -> None:
        """매 physics substep: actuator net 으로 토크 계산·적용 + 히스토리 갱신.
        legged_robot._compute_torques(actuator_net) 와 동일:
          pos_err = dof_pos - joint_pos_target
          xs=[pe,pe_l,pe_ll, v,v_l,v_ll] (12,6) → actnet → torque
          (계산 후) pe_ll←pe_l; pe_l←pe; v_ll←v_l; v_l←v
          clip(±torque_limit), motor_strengths=1."""
        if self._jpt is None:
            return
        try:
            torch = self._torch
            ps = np.asarray(self._art.get_joint_positions(), dtype=float)
            vs = np.asarray(self._art.get_joint_velocities(), dtype=float)
            p2s = self._p2s
            # sim→policy 컨벤션: hip 부호 반전(_SGN)
            q = np.array([ps[p2s[i]] for i in range(12)],
                         dtype=np.float32) * _SGN
            qd = np.array([vs[p2s[i]] for i in range(12)],
                          dtype=np.float32) * _SGN

            pe = (q - self._jpt).astype(np.float32)
            xs = np.stack(
                [pe, self._pe_l, self._pe_ll, qd, self._v_l, self._v_ll],
                axis=-1).astype(np.float32)                    # (12,6)
            with torch.no_grad():
                tau = self._actnet(torch.from_numpy(xs)).numpy().ravel()

            # 히스토리 갱신 (토크 계산 후 — legged_robot 와 동일 순서)
            self._pe_ll = self._pe_l.copy()
            self._pe_l = pe.copy()
            self._v_ll = self._v_l.copy()
            self._v_l = qd.copy()

            tau = np.clip(tau, -TORQUE_LIMIT, TORQUE_LIMIT)
            # policy→sim 컨벤션: hip 토크도 부호 반전(_SGN) 후 적용
            tau = tau * _SGN
            tau_sim = np.zeros(self._n_dofs, dtype=np.float32)
            for pi, si in enumerate(p2s):
                tau_sim[si] = tau[pi]

            from isaacsim.core.utils.types import ArticulationAction
            self._art.apply_action(
                ArticulationAction(joint_efforts=tau_sim))
        except Exception:
            pass
