"""walk-these-ways-go2 정책 MCP 실행 스크립트."""

import omni.usd
import omni.timeline
import omni.kit.app
from pxr import Gf, UsdGeom
import numpy as np
import torch

GO2_USD  = ("https://omniverse-content-production.s3-us-west-2.amazonaws.com"
            "/Assets/Isaac/5.1/Isaac/Robots/Unitree/Go2/go2.usd")
GO2_PRIM = "/World/Go2"
CKPT     = ("/home/rokey/dev_ws/isaac_sim/cobot3/main_side/go2_policy"
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

# 1. Go2 씬 추가
stage = omni.usd.get_context().get_stage()
if stage.GetPrimAtPath(GO2_PRIM).IsValid():
    stage.RemovePrim(GO2_PRIM)

go2_prim = stage.DefinePrim(GO2_PRIM, "Xform")
go2_prim.GetReferences().AddReference(GO2_USD)
xf = UsdGeom.Xformable(go2_prim)
xf.ClearXformOpOrder()
xf.AddTranslateOp().Set(Gf.Vec3d(5.0, 0.0, 0.4))
print("[go2_wtw] Go2 추가 ->", GO2_PRIM)

for _ in range(40):
    omni.kit.app.get_app().update()

# 2. Articulation 초기화
from isaacsim.core.prims import SingleArticulation
from isaacsim.core.api import World

world = World.instance()
if world is None:
    world = World()
go2_art = SingleArticulation(prim_path=GO2_PRIM)
go2_art.initialize()

joint_names = list(go2_art.dof_names)
print("[go2_wtw] joints:", joint_names)

# 3. 인덱스 매핑
def _match(a, b):
    a, b = a.lower(), b.lower()
    return a == b or a.endswith(b) or b.endswith(a)

train_to_sim = [None] * 12
for si, sn in enumerate(joint_names):
    for ti, tn in enumerate(TRAIN_ORDER):
        if _match(sn, tn):
            train_to_sim[ti] = si
            break

assert None not in train_to_sim, "joint mapping failed: " + str(list(zip(TRAIN_ORDER, train_to_sim)))
print("[go2_wtw] train->sim:", train_to_sim)

default_train = torch.tensor([DEFAULT_ANGLES[j] for j in TRAIN_ORDER], dtype=torch.float32)
default_sim   = np.array([DEFAULT_ANGLES.get(j, 0.) for j in joint_names])

# 4. PD 게인 + 초기 자세
go2_art.set_gains(kps=np.full(len(joint_names), 25.0), kds=np.full(len(joint_names), 0.6))
go2_art.set_joint_positions(default_sim)

# 5. JIT 모델 로드
adapt_mod = torch.jit.load(CKPT + "/adaptation_module_latest.jit").eval()
body_net   = torch.jit.load(CKPT + "/body_latest.jit").eval()

with torch.no_grad():
    _lat = adapt_mod(torch.zeros(1, HIST_LEN * NUM_OBS))
    _act = body_net(torch.cat([torch.zeros(1, NUM_OBS), _lat], dim=-1))
LATENT_DIM = _lat.shape[-1]
print("[go2_wtw] latent=%d action=%d" % (LATENT_DIM, _act.shape[-1]))

# 6. 정책 상태 (리스트로 클로저 갱신 허용)
cmd_t   = torch.tensor([CMD_VEL], dtype=torch.float32)
obs_buf = [torch.zeros(1, HIST_LEN * NUM_OBS)]
prev_a  = [torch.zeros(1, 12)]
steps   = [0]

def proj_gravity(q_wxyz):
    w = float(q_wxyz[0]); x = float(q_wxyz[1])
    y = float(q_wxyz[2]); z = float(q_wxyz[3])
    g = np.array([0., 0., -1.])
    t = 2. * np.array([y*g[2]-z*g[1], z*g[0]-x*g[2], x*g[1]-y*g[0]])
    return torch.tensor(g + w*t + np.cross([x, y, z], t), dtype=torch.float32)

def policy_step(dt):
    steps[0] += 1

    pos_sim = go2_art.get_joint_positions()
    vel_sim = go2_art.get_joint_velocities()
    pos_t   = torch.tensor([float(pos_sim[train_to_sim[i]]) for i in range(12)])
    vel_t   = torch.tensor([float(vel_sim[train_to_sim[i]]) for i in range(12)])

    _, quats = go2_art.get_world_poses()
    pg = proj_gravity(quats[0])

    obs = torch.cat([
        pg.unsqueeze(0),
        cmd_t,
        ((pos_t - default_train)).unsqueeze(0),
        (vel_t * 0.05).unsqueeze(0),
        prev_a[0],
    ], dim=-1)

    obs_buf[0] = torch.cat([obs_buf[0][:, NUM_OBS:], obs], dim=-1)

    with torch.no_grad():
        latent  = adapt_mod(obs_buf[0])
        actions = body_net(torch.cat([obs, latent], dim=-1))

    scaled = actions * ACTION_SCALE
    scaled[:, :4] *= HIP_SCALE
    prev_a[0] = actions.detach()

    target_t = (default_train + scaled[0]).numpy()
    target_sim = default_sim.copy()
    for ti, si in enumerate(train_to_sim):
        target_sim[si] = float(target_t[ti])

    go2_art.set_joint_position_targets(target_sim)
    if steps[0] % 200 == 1:
        print("[go2_wtw] step=%d" % steps[0], np.round(target_t, 2))

# 7. 콜백 등록
try:
    world.remove_physics_callback("go2_wtw_policy")
except Exception:
    pass
world.add_physics_callback("go2_wtw_policy", policy_step)

timeline = omni.timeline.get_timeline_interface()
if not timeline.is_playing():
    timeline.play()

"go2_wtw done — latent_dim=%d" % LATENT_DIM
