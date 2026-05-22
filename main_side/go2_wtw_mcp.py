"""walk-these-ways-go2 정책 실행 스크립트.

Isaac Sim MCP (exec() 컨텍스트)에서 직접 실행.

핵심 원칙:
- app.update() 절대 사용 금지 — exec() 내부에서 이벤트 루프 재진입 → 크래시
- initialize(), set_gains() 등 블로킹 ops는 physx 콜백 첫 호출에서 실행
- 모든 쓰기 ops는 physx 콜백 컨텍스트에서만 (exec() 컨텍스트에서는 읽기만)
"""

import omni.usd
import omni.timeline
from pxr import Gf, UsdGeom
import numpy as np
import torch
import builtins
from omni.physx import get_physx_interface

GO2_USD  = ("https://omniverse-content-production.s3-us-west-2.amazonaws.com"
            "/Assets/Isaac/5.1/Isaac/Robots/Unitree/Go2/go2.usd")
GO2_PRIM = "/World/Go2"
CKPT     = ("/home/rokey/dev_ws/isaac_sim/cobot3/main_side/scene/go2_policy"
            "/gait-conditioned-agility/pretrain-go2/train/142238.667503/checkpoints")

TRAIN_ORDER = [
    "FL_hip_joint","RL_hip_joint","FR_hip_joint","RR_hip_joint",
    "FL_thigh_joint","RL_thigh_joint","FR_thigh_joint","RR_thigh_joint",
    "FL_calf_joint","RL_calf_joint","FR_calf_joint","RR_calf_joint",
]
DEFAULT_ANGLES = {
    "FL_hip_joint":  0.1, "RL_hip_joint":  0.1,
    "FR_hip_joint": -0.1, "RR_hip_joint": -0.1,
    "FL_thigh_joint": 0.8, "RL_thigh_joint": 1.0,
    "FR_thigh_joint": 0.8, "RR_thigh_joint": 1.0,
    "FL_calf_joint": -1.5, "RL_calf_joint": -1.5,
    "FR_calf_joint": -1.5, "RR_calf_joint": -1.5,
}
ACTION_SCALE = 0.25
HIP_SCALE    = 0.5
CMD_VEL      = [0.5, 0.0, 0.0]
NUM_OBS      = 42
HIST_LEN     = 15

# ── 1. Go2 씬 추가 (없으면) — USD 조작만, app.update() 없음 ─────────
stage = omni.usd.get_context().get_stage()
if not stage.GetPrimAtPath(GO2_PRIM).IsValid():
    go2_prim = stage.DefinePrim(GO2_PRIM, "Xform")
    go2_prim.GetReferences().AddReference(GO2_USD)
    xf = UsdGeom.Xformable(go2_prim)
    xf.ClearXformOpOrder()
    xf.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 0.5))
    # app.update() 금지 — USD 컴포지션은 physx 콜백이 시작되기 전에 완료됨
    print("[go2_wtw] Go2 새로 추가 (initialize는 physx 콜백에서)")
else:
    print("[go2_wtw] Go2 기존 프림 사용")

# ── 2. JIT 모델 로드 (pure Python, 블로킹 없음) ────────────────────
adapt_mod = torch.jit.load(CKPT + "/adaptation_module_latest.jit").eval()
body_net   = torch.jit.load(CKPT + "/body_latest.jit").eval()

with torch.no_grad():
    _lat = adapt_mod(torch.zeros(1, HIST_LEN * NUM_OBS))
    _act = body_net(torch.cat([torch.zeros(1, NUM_OBS), _lat], dim=-1))
LATENT_DIM = _lat.shape[-1]
print("[go2_wtw] latent=%d action=%d" % (LATENT_DIM, _act.shape[-1]))

# ── 3. 정책 상태 (builtins 참조하여 콜백에서 접근) ───────────────────
cmd_t   = torch.tensor([CMD_VEL], dtype=torch.float32)
obs_buf = [torch.zeros(1, HIST_LEN * NUM_OBS)]
prev_a  = [torch.zeros(1, 12)]
steps   = [0]
builtins._go2_wtw_cmd_t   = cmd_t
builtins._go2_wtw_obs_buf = obs_buf
builtins._go2_wtw_prev_a  = prev_a
builtins._go2_wtw_steps   = steps
builtins._go2_wtw_adapt   = adapt_mod
builtins._go2_wtw_body    = body_net

def _match(a, b):
    a, b = a.lower(), b.lower()
    return a == b or a.endswith(b) or b.endswith(a)

def proj_gravity(q_wxyz):
    w = float(q_wxyz[0]); x = float(q_wxyz[1])
    y = float(q_wxyz[2]); z = float(q_wxyz[3])
    g = np.array([0., 0., -1.])
    t = 2. * np.array([y*g[2]-z*g[1], z*g[0]-x*g[2], x*g[1]-y*g[0]])
    return torch.tensor(g + w*t + np.cross([x, y, z], t), dtype=torch.float32)

def policy_step(dt):
    _steps = builtins._go2_wtw_steps
    _steps[0] += 1
    _art     = builtins._go2_wtw_art
    _d       = builtins._go2_wtw_default
    _t2s     = builtins._go2_wtw_t2s
    _dtrain  = builtins._go2_wtw_dtrain
    _cmd_t   = builtins._go2_wtw_cmd_t
    _obs_buf = builtins._go2_wtw_obs_buf
    _prev_a  = builtins._go2_wtw_prev_a
    _adapt   = builtins._go2_wtw_adapt
    _body    = builtins._go2_wtw_body

    try:
        from isaacsim.core.utils.types import ArticulationAction

        pos_sim = _art.get_joint_positions()
        vel_sim = _art.get_joint_velocities()
        pos_t   = torch.tensor([float(pos_sim[_t2s[i]]) for i in range(12)])
        vel_t   = torch.tensor([float(vel_sim[_t2s[i]]) for i in range(12)])

        _, quat = _art.get_world_pose()
        pg = proj_gravity(quat)

        obs = torch.cat([
            pg.unsqueeze(0),
            _cmd_t,
            (pos_t - _dtrain).unsqueeze(0),
            (vel_t * 0.05).unsqueeze(0),
            _prev_a[0],
        ], dim=-1)

        _obs_buf[0] = torch.cat([_obs_buf[0][:, NUM_OBS:], obs], dim=-1)

        with torch.no_grad():
            latent  = _adapt(_obs_buf[0])
            actions = _body(torch.cat([obs, latent], dim=-1))

        scaled = actions * ACTION_SCALE
        scaled[:, :4] *= HIP_SCALE
        _prev_a[0] = actions.detach()

        target_t = (_dtrain + scaled[0]).numpy()
        target_sim = _d.copy()
        for ti, si in enumerate(_t2s):
            target_sim[si] = float(target_t[ti])

        _art.apply_action(ArticulationAction(joint_positions=target_sim))

        if _steps[0] % 100 == 1:
            with open('/tmp/go2_step.txt', 'a') as f:
                f.write(f"step={_steps[0]} pg={pg.numpy().round(2).tolist()} "
                        f"t4={target_t[:4].round(2).tolist()}\n")
    except Exception as e:
        if _steps[0] % 500 == 1:
            with open('/tmp/go2_step.txt', 'a') as f:
                f.write(f"[policy_err step={_steps[0]}] {e}\n")

# ── 4. 초기화 콜백 — physx 콜백 내부에서 initialize() 실행 ─────────
# exec() 컨텍스트에서 initialize()를 호출하면 다음 physx 스텝을 기다리며 블로킹됨.
# 대신 physx 콜백 내부에서 호출하면 현재 스텝 컨텍스트 안에서 안전하게 실행됨.
_init_state = [0]   # 0=대기, 1=완료, -1=오류

def _init_and_start(dt):
    if _init_state[0] != 0:
        return
    _init_state[0] = -1   # 중간에 예외 나도 무한루프 방지

    try:
        from isaacsim.core.prims import SingleArticulation
        from isaacsim.core.utils.types import ArticulationAction

        art = SingleArticulation(prim_path=GO2_PRIM)
        art.initialize()

        joint_names = list(art.dof_names)

        t2s = [None] * 12
        for si, sn in enumerate(joint_names):
            for ti, tn in enumerate(TRAIN_ORDER):
                if _match(sn, tn):
                    t2s[ti] = si
                    break
        assert None not in t2s, "joint mapping failed: " + str(list(zip(TRAIN_ORDER, t2s)))

        default_sim   = np.array([DEFAULT_ANGLES.get(j, 0.) for j in joint_names])
        default_train = torch.tensor([DEFAULT_ANGLES[j] for j in TRAIN_ORDER],
                                     dtype=torch.float32)

        # PD 게인 설정 (physx 콜백 내부 → 블로킹 없음)
        ctrl = art.get_articulation_controller()
        ctrl.set_gains(
            kps=np.full(len(joint_names), 25.0),
            kds=np.full(len(joint_names), 0.6)
        )

        # builtins에 공유 상태 저장
        builtins._go2_wtw_art     = art
        builtins._go2_wtw_default = default_sim
        builtins._go2_wtw_dtrain  = default_train
        builtins._go2_wtw_t2s     = t2s

        # 정책 콜백 등록
        sub = get_physx_interface().subscribe_physics_step_events(policy_step)
        builtins._go2_wtw_sub = sub

        _init_state[0] = 1   # 성공
        with open('/tmp/go2_step.txt', 'a') as f:
            f.write(f"[init_ok] joints={joint_names}\nt2s={t2s}\n")
        print(f"[go2_wtw] 초기화 완료: {joint_names}")

    except Exception as e:
        import traceback
        with open('/tmp/go2_step.txt', 'a') as f:
            f.write(f"[init_err] {e}\n{traceback.format_exc()}\n")
        print(f"[go2_wtw] 초기화 오류: {e}")

# ── 5. 기존 콜백 정리 ─────────────────────────────────────────────
for _attr in ['_go2_wtw_sub', '_go2_init_sub',
              '_go2_apply_sub', '_go2_ctl_sub', '_go2_full_sub',
              '_go2_physx_sub', '_simple_sub']:
    _sub = getattr(builtins, _attr, None)
    if _sub:
        try: _sub.unsubscribe()
        except Exception: pass
        try: delattr(builtins, _attr)
        except Exception: pass

# ── 6. 초기화 콜백 등록 + 타임라인 시작 ─────────────────────────────
_init_sub = get_physx_interface().subscribe_physics_step_events(_init_and_start)
builtins._go2_init_sub = _init_sub

timeline = omni.timeline.get_timeline_interface()
if not timeline.is_playing():
    timeline.play()

result = {"status": "registered", "latent_dim": LATENT_DIM,
          "msg": "physx 콜백에서 initialize 예정"}
print("[go2_wtw] 초기화 콜백 등록 완료 — 첫 physx 스텝에서 articulation 초기화 예정")
