"""standalone RealSense 카메라 퍼블리셔 (MCP/GUI 비의존, 결정적).

isaac-sim-mcp 스킬 원칙: MCP 가 불능일 때 python.sh standalone 사용.
씬 USD 를 열고(없으면 최소 구성), m0609 link_6 플랜지에 RealSense Camera 를
보장한 뒤, OG sensor_bridge(OnTick→ROS2Context(domain 130)→CreateRenderProduct
→ROS2CameraHelper rgb)를 만들고 시뮬을 계속 step 하여 `/cam/realsense/rgb`
를 발행한다. RMW 는 환경(run 스크립트가 cyclonedds 설정).

실행: main_side/run_camera_pub.sh
"""
import os

from isaacsim import SimulationApp

# 카메라가 프레임을 내려면 렌더가 필요 → headless 라도 renderer 활성
simulation_app = SimulationApp({"headless": True, "renderer": "RayTracedLighting"})

import omni.usd
import omni.timeline
import omni.graph.core as og
from pxr import UsdGeom, Usd, Gf
from isaacsim.core.api import World
from isaacsim.core.utils.extensions import enable_extension

# ROS2 bridge 확장은 standalone 앱에 자동 로드되지 않음 → 명시 enable
enable_extension("isaacsim.ros2.bridge")
for _ in range(60):              # 노드 타입 등록될 때까지 app 펌프
    simulation_app.update()

SCENE = os.environ.get(
    "GP_SCENE",
    "/home/rokey/dev_ws/isaac_sim/src/doosan-robot2/urdf/m0609_isaac_sim/cobot3_1.usd",
)
CAM_PATH = "/World/Robot/m0609/link_6/realsense"
GRAPH = "/World/Graphs/sensor_bridge"
TOPIC = "/cam/realsense/rgb"
DOMAIN = int(os.environ.get("ROS_DOMAIN_ID", "130"))


def log(m):
    print(f"[camera_pub] {m}", flush=True)


# ── 통신 설정 자가점검 (요청: ROS_DOMAIN_ID 등 맞는지) ──────────────────
log("==== ENV / ROS 설정 점검 ====")
for k in ("ROS_DOMAIN_ID", "RMW_IMPLEMENTATION", "ROS_LOCALHOST_ONLY",
          "ROS_DISTRO", "AMENT_PREFIX_PATH"):
    v = os.environ.get(k, "<UNSET>")
    log(f"  {k}={v if k != 'AMENT_PREFIX_PATH' else v.split(':')[0]+' ...'}")
if os.environ.get("ROS_DOMAIN_ID") != "130":
    log("  ⚠ ROS_DOMAIN_ID != 130 — C2/degrade 와 불일치 가능!")
if os.environ.get("RMW_IMPLEMENTATION") != "rmw_cyclonedds_cpp":
    log("  ⚠ RMW != rmw_cyclonedds_cpp — Isaac↔C2 디스커버리 실패 위험!")
log(f"  GP_SCENE={SCENE}")
log("=============================")


# 1) 씬 열기 ---------------------------------------------------------------
ctx = omni.usd.get_context()
if os.path.isfile(SCENE):
    ctx.open_stage(SCENE)
    log(f"opened scene: {SCENE}")
else:
    ctx.new_stage()
    log(f"scene not found, empty stage: {SCENE}")
stage = ctx.get_stage()

# 2) RealSense 카메라 보장 (없으면 link_6 자식으로 생성) -------------------
cam_prim = stage.GetPrimAtPath(CAM_PATH)
if not cam_prim.IsValid():
    # link_6 탐색
    link6 = None
    rp = stage.GetPrimAtPath("/World/Robot/m0609")
    if rp.IsValid():
        for p in Usd.PrimRange(rp):
            if p.GetName() == "link_6":
                link6 = str(p.GetPath())
                break
    target = (link6 + "/realsense") if link6 else CAM_PATH
    cam = UsdGeom.Camera.Define(stage, target)
    W, H, F, HA, VA = 1280, 720, 24.0, 20.955, 11.787
    cam.GetFocalLengthAttr().Set(F)
    cam.GetHorizontalApertureAttr().Set(HA)
    cam.GetVerticalApertureAttr().Set(VA)
    cam.GetClippingRangeAttr().Set(Gf.Vec2f(0.05, 100.0))
    xf = UsdGeom.Xformable(cam.GetPrim())
    xf.ClearXformOpOrder()
    xf.AddTranslateOp().Set(Gf.Vec3f(0, 0, 0.05))
    xf.AddRotateXYZOp().Set(Gf.Vec3f(0, 180, 0))
    CAM_PATH = target
    log(f"created RealSense camera at {CAM_PATH}")
else:
    log(f"RealSense camera present: {CAM_PATH}")

# 3) OG sensor_bridge — 기존(비기능 가능) 제거 후 항상 fresh 재생성 --------
# 노드 타입 등록 확인 (ros2.bridge enable 가 실제 반영됐는지) — 방어적
try:
    import omni.graph.tools.ogn as _ogn  # noqa
    for nt in ("isaacsim.ros2.bridge.ROS2CameraHelper",
               "isaacsim.ros2.bridge.ROS2Context"):
        ok = nt in og.GraphRegistry().get_node_types()
        log(f"nodetype {nt}: registered={ok}")
except Exception as e:
    log(f"nodetype 등록확인 스킵({e!r}) — enable_extension 후 진행")

if stage.GetPrimAtPath(GRAPH).IsValid():
    stage.RemovePrim(GRAPH)
    for _ in range(10):
        simulation_app.update()
    log(f"기존 {GRAPH} 제거 (fresh 재생성 위해)")

K = og.Controller.Keys
og.Controller.edit(
    {"graph_path": GRAPH, "evaluator_name": "execution"},
    {
        K.CREATE_NODES: [
            ("OnTick", "omni.graph.action.OnPlaybackTick"),
            ("Ctx", "isaacsim.ros2.bridge.ROS2Context"),
            ("CreateRP", "isaacsim.core.nodes.IsaacCreateRenderProduct"),
            ("CamRGB", "isaacsim.ros2.bridge.ROS2CameraHelper"),
        ],
        K.SET_VALUES: [
            ("Ctx.inputs:domain_id", DOMAIN),
            ("CreateRP.inputs:cameraPrim", CAM_PATH),
            ("CreateRP.inputs:width", 1280),
            ("CreateRP.inputs:height", 720),
            ("CamRGB.inputs:topicName", TOPIC),
            ("CamRGB.inputs:frameId", "realsense"),
            ("CamRGB.inputs:type", "rgb"),
            ("CamRGB.inputs:qosProfile", "sensor_data"),
        ],
        K.CONNECT: [
            ("OnTick.outputs:tick", "CreateRP.inputs:execIn"),
            ("CreateRP.outputs:execOut", "CamRGB.inputs:execIn"),
            ("CreateRP.outputs:renderProductPath",
             "CamRGB.inputs:renderProductPath"),
            ("Ctx.outputs:context", "CamRGB.inputs:context"),
        ],
    },
)
log(f"OG {GRAPH} fresh 생성 완료 → {TOPIC} (domain {DOMAIN})")

# 4) 시뮬 구동 — OnPlaybackTick 이 틱하도록 계속 step -----------------------
world = World(stage_units_in_meters=1.0)
world.reset()
omni.timeline.get_timeline_interface().play()
log("simulation playing — Ctrl+C to stop")

# 자가검증: 몇 스텝 후 OG 가 render product 를 실제로 만들었는지 확인
def _diag():
    try:
        rp = og.Controller.attribute(
            f"{GRAPH}/CreateRP.outputs:renderProductPath").get()
        cp = og.Controller.attribute(
            f"{GRAPH}/CreateRP.inputs:cameraPrim").get()
        log(f"DIAG cameraPrim={cp} renderProduct={rp!r}")
        if not rp:
            log("  ⚠ renderProductPath 비어있음 → 카메라 프레임 생성 안 됨 "
                "(publisher 0 의 직접 원인). cameraPrim 경로/렌더 확인 필요")
    except Exception as e:
        log(f"DIAG 실패: {e!r}")

n = 0
try:
    while simulation_app.is_running():
        world.step(render=True)
        n += 1
        if n in (60, 150):
            _diag()
        if n % 300 == 0:
            t = omni.timeline.get_timeline_interface().get_current_time()
            log(f"stepped {n} frames | simTime={t:.2f} | publishing {TOPIC} "
                f"(domain {os.environ.get('ROS_DOMAIN_ID')})")
            _diag()
except KeyboardInterrupt:
    log("중지(Ctrl+C)")
finally:
    simulation_app.close()
