"""standalone RealSense 카메라 퍼블리셔 (MCP/GUI 비의존, 결정적).

씬 USD 를 열고(없으면 최소 구성), Spot 팔 끝(arm0_link_wr1) 의 RealSense
Camera 를 보장한 뒤, OG sensor_bridge(OnTick→ROS2Context(domain 130)→
CreateRenderProduct→ROS2CameraHelper rgb)를 만들고 시뮬을 계속 step 하여
`/cam/realsense/rgb` 를 발행한다. 같은 그래프에서 ROS2 정공 텔레메트리
(Spot 단일 아티큘레이션 JointState + base Odometry)도 OG 노드로 발행
(GP_ROS2_TELEM=1). 다운링크(/robot/cmd_vel) 는 OG ROS2SubscribeTwist 로 수신 →
SpotController.set_cmd_vel 로 전달 → RL 보행 정책에 반영.
HTTP /ingest 경로 제거 — ROS2 정공 단일 경로.

실행: main_side/run_camera_pub.sh
"""
import os
import time

from isaacsim import SimulationApp

# GP_HEADLESS=0 → GUI 창 표시, 1 → headless(웹 전송 전용).
_HEADLESS = os.environ.get("GP_HEADLESS", "0") == "1"
simulation_app = SimulationApp(
    {"headless": _HEADLESS, "renderer": "RayTracedLighting"}
)

import omni.usd
import omni.timeline
import omni.graph.core as og
from pxr import UsdGeom, Usd, Gf, Sdf
from isaacsim.core.api import World
from isaacsim.core.utils.extensions import enable_extension

# ROS2 bridge 확장 명시 enable (standalone 앱에 자동 로드 안 됨)
enable_extension("isaacsim.ros2.bridge")
for _ in range(60):              # 노드 타입 등록될 때까지 app 펌프
    simulation_app.update()

SCENE = os.environ.get(
    "GP_SCENE",
    # 이식성: 스크립트 상대(하드코딩 제거). main_side/scene/ 는 자체완결.
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "scene", "gp_scene.usd"),
)
CAM_PATH = "/World/Robot/arm0_link_wr1/realsense"
SPOT_PRIM = "/World/Robot"
BASE_PRIM = "/World/Robot/base"
WRIST_PRIM = "/World/Robot/arm0_link_wr1"
GRAPH = "/World/Graphs/sensor_bridge"
TOPIC = "/cam/realsense/rgb"
DOMAIN = int(os.environ.get("ROS_DOMAIN_ID", "130"))
_SPOT_CTRL = os.environ.get("GP_SPOT_CONTROL", "1") == "1"


def log(m):
    print(f"[camera_pub] {m}", flush=True)


# ── 통신 설정 자가점검 ────────────────────────────────────────────────────
log("==== ENV / ROS 설정 점검 ====")
for k in ("ROS_DOMAIN_ID", "RMW_IMPLEMENTATION", "ROS_LOCALHOST_ONLY",
          "ROS_DISTRO", "AMENT_PREFIX_PATH"):
    v = os.environ.get(k, "<UNSET>")
    log(f"  {k}={v if k != 'AMENT_PREFIX_PATH' else v.split(':')[0]+' ...'}")
if os.environ.get("ROS_DOMAIN_ID") != "130":
    log("  ⚠ ROS_DOMAIN_ID != 130 — C2/degrade 와 불일치 가능!")
if os.environ.get("RMW_IMPLEMENTATION") != "rmw_fastrtps_cpp":
    log("  ⚠ RMW != rmw_fastrtps_cpp — Isaac↔C2 디스커버리 실패 위험!")
log(f"  GP_SCENE={SCENE}")
log("=============================")


# 1) 씬 열기 ----------------------------------------------------------------
ctx = omni.usd.get_context()
if os.path.isfile(SCENE):
    ctx.open_stage(SCENE)
    log(f"opened scene: {SCENE}")
else:
    ctx.new_stage()
    log(f"scene not found, empty stage: {SCENE}")
stage = ctx.get_stage()

# 2) RealSense 카메라 보장 ---------------------------------------------------
# 구조: arm0_link_wr1/realsense (Xform + rsd455.usd 참조 = 시각 메시)
#       arm0_link_wr1/realsense/Camera (UsdGeom.Camera = OG 렌더 타깃)
_RS_USD = ("https://omniverse-content-production.s3-us-west-2.amazonaws.com"
           "/Assets/Isaac/5.1/Isaac/Sensors/Intel/RealSense/rsd455.usd")
_rs_base = (WRIST_PRIM + "/realsense"
            if stage.GetPrimAtPath(WRIST_PRIM).IsValid() else CAM_PATH)
_cam_path = _rs_base + "/Camera"

xp = stage.GetPrimAtPath(_rs_base)
if xp.IsValid() and xp.GetTypeName() == "Camera":
    # 구버전 Camera prim → 제거 후 Xform+rsd455 로 재구성 (비주얼 메시 연결)
    stage.RemovePrim(_rs_base)
    xp = stage.GetPrimAtPath(_rs_base)  # RemovePrim 후 재확인
    log(f"RealSense 구버전 Camera prim 제거: {_rs_base}")

if not xp.IsValid():
    xp = UsdGeom.Xform.Define(stage, _rs_base).GetPrim()
    xp.GetReferences().AddReference(_RS_USD)
    log(f"RealSense Xform+rsd455 생성: {_rs_base}")
else:
    log(f"RealSense Xform 있음: {_rs_base}")

# 항상 transform 갱신 — 자동저장 씬에 이전 회전값 잔존 방지
# rotateXYZ(0,-90,0): 카메라 기본 look(-Z)이 wrist +X(전방)으로 향하도록
xf = UsdGeom.Xformable(xp)
xf.ClearXformOpOrder()
xf.AddTranslateOp().Set(Gf.Vec3f(0.06, 0, 0))
xf.AddRotateXYZOp().Set(Gf.Vec3f(0, -90, 0))

# PhysicsAPI 제거는 항상 실행 — 씬 자동저장 후 재로드 시에도 rsd455 physics 잔존 방지
# (rigidBodyEnabled=False 로는 schema 경고가 남으므로 API 자체를 제거)
try:
    for desc in Usd.PrimRange(xp):
        removed = []
        for api in ("PhysicsRigidBodyAPI", "PhysicsCollisionAPI",
                    "PhysicsMassAPI", "PhysicsArticulationRootAPI"):
            if api in desc.GetAppliedSchemas():
                desc.RemoveAppliedSchema(api)
                removed.append(api)
        if removed:
            log(f"  RealSense physics 제거: {desc.GetPath()} {removed}")
except Exception as e:
    log(f"  RealSense physics 제거 스킵: {e!r}")

cam_prim = stage.GetPrimAtPath(_cam_path)
if not cam_prim.IsValid():
    cam = UsdGeom.Camera.Define(stage, _cam_path)
    cam.GetFocalLengthAttr().Set(24.0)
    cam.GetHorizontalApertureAttr().Set(20.955)
    cam.GetVerticalApertureAttr().Set(11.787)
    cam.GetClippingRangeAttr().Set(Gf.Vec2f(0.05, 100.0))
    log(f"RealSense Camera prim 생성: {_cam_path}")
else:
    log(f"RealSense Camera prim 있음: {_cam_path}")
CAM_PATH = _cam_path
log(f"CAM_PATH → {CAM_PATH}")

# 3) OG sensor_bridge — 기존(비기능 가능) 제거 후 항상 fresh 재생성 ----------
try:
    import omni.graph.tools.ogn as _ogn  # noqa
    for nt in ("isaacsim.ros2.bridge.ROS2CameraHelper",
               "isaacsim.ros2.bridge.ROS2Context"):
        ok = nt in og.GraphRegistry().get_node_types()
        log(f"nodetype {nt}: registered={ok}")
except Exception as e:
    log(f"nodetype 등록확인 스킵({e!r})")

if stage.GetPrimAtPath(GRAPH).IsValid():
    stage.RemovePrim(GRAPH)
    for _ in range(10):
        simulation_app.update()
    log(f"기존 {GRAPH} 제거 (fresh 재생성 위해)")

# ── ROS2 정공 설정 ────────────────────────────────────────────────────────
# Isaac ROS2 bridge qosProfile JSON 파서는 8키 전부 요구 (FASTDDS.md §3).
_TELEM = os.environ.get("GP_ROS2_TELEM", "1") == "1"
_REL_QOS = ('{"history":"keepLast","depth":10,"reliability":"reliable",'
            '"durability":"volatile","deadline":0.0,"lifespan":0.0,'
            '"liveliness":"systemDefault","leaseDuration":0.0}')
_SENSOR_QOS = ('{"history":"keepLast","depth":5,"reliability":"bestEffort",'
               '"durability":"volatile","deadline":0.0,"lifespan":0.0,'
               '"liveliness":"systemDefault","leaseDuration":0.0}')
_CMD = os.environ.get("GP_ROS2_CMD", "1") == "1"
CMD_TOPIC = os.environ.get("GP_CMD_TOPIC", "/robot/cmd_vel")
ARM_PRIM, LEG_PRIM = SPOT_PRIM, SPOT_PRIM
ARM_TOPIC = "/dsr01/joint_states"
LEG_TOPIC = "/robot/leg_joint_states"
ODOM_TOPIC = "/robot/odom"

K = og.Controller.Keys
_CN = [
    ("OnTick", "omni.graph.action.OnPlaybackTick"),
    ("Ctx", "isaacsim.ros2.bridge.ROS2Context"),
    ("CreateRP", "isaacsim.core.nodes.IsaacCreateRenderProduct"),
    ("CamRGB", "isaacsim.ros2.bridge.ROS2CameraHelper"),
]
_SV = [
    ("Ctx.inputs:domain_id", DOMAIN),
    ("CreateRP.inputs:cameraPrim", CAM_PATH),
    ("CreateRP.inputs:width", 1280),
    ("CreateRP.inputs:height", 720),
    ("CamRGB.inputs:topicName", TOPIC),
    ("CamRGB.inputs:frameId", "realsense"),
    ("CamRGB.inputs:type", "rgb"),
    ("CamRGB.inputs:qosProfile", _SENSOR_QOS),
]
_CC = [
    ("OnTick.outputs:tick", "CreateRP.inputs:execIn"),
    ("CreateRP.outputs:execOut", "CamRGB.inputs:execIn"),
    ("CreateRP.outputs:renderProductPath", "CamRGB.inputs:renderProductPath"),
    ("Ctx.outputs:context", "CamRGB.inputs:context"),
]
if _TELEM:
    _CN += [
        ("SimTime", "isaacsim.core.nodes.IsaacReadSimulationTime"),
        ("ArmJS", "isaacsim.ros2.bridge.ROS2PublishJointState"),
        ("LegJS", "isaacsim.ros2.bridge.ROS2PublishJointState"),
        ("Odo", "isaacsim.core.nodes.IsaacComputeOdometry"),
        ("OdoPub", "isaacsim.ros2.bridge.ROS2PublishOdometry"),
    ]
    _SV += [
        ("ArmJS.inputs:targetPrim", ARM_PRIM),
        ("ArmJS.inputs:topicName", ARM_TOPIC),
        ("ArmJS.inputs:qosProfile", _REL_QOS),
        ("LegJS.inputs:targetPrim", LEG_PRIM),
        ("LegJS.inputs:topicName", LEG_TOPIC),
        ("LegJS.inputs:qosProfile", _REL_QOS),
        ("Odo.inputs:chassisPrim", BASE_PRIM),
        ("OdoPub.inputs:topicName", ODOM_TOPIC),
        ("OdoPub.inputs:odomFrameId", "odom"),
        ("OdoPub.inputs:chassisFrameId", "base_link"),
        ("OdoPub.inputs:qosProfile", _REL_QOS),
    ]
    _CC += [
        ("OnTick.outputs:tick", "ArmJS.inputs:execIn"),
        ("OnTick.outputs:tick", "LegJS.inputs:execIn"),
        ("OnTick.outputs:tick", "Odo.inputs:execIn"),
        ("Odo.outputs:execOut", "OdoPub.inputs:execIn"),
        ("Ctx.outputs:context", "ArmJS.inputs:context"),
        ("Ctx.outputs:context", "LegJS.inputs:context"),
        ("Ctx.outputs:context", "OdoPub.inputs:context"),
        ("SimTime.outputs:simulationTime", "ArmJS.inputs:timeStamp"),
        ("SimTime.outputs:simulationTime", "LegJS.inputs:timeStamp"),
        ("SimTime.outputs:simulationTime", "OdoPub.inputs:timeStamp"),
        ("Odo.outputs:position", "OdoPub.inputs:position"),
        ("Odo.outputs:orientation", "OdoPub.inputs:orientation"),
        ("Odo.outputs:linearVelocity", "OdoPub.inputs:linearVelocity"),
        ("Odo.outputs:angularVelocity", "OdoPub.inputs:angularVelocity"),
    ]
if _CMD:
    # SubCmd 는 메인 OG 단일 빌드에 통합(증분 edit = OmniGraphError)
    _CN += [("SubCmd", "isaacsim.ros2.bridge.ROS2SubscribeTwist")]
    _SV += [("SubCmd.inputs:topicName", CMD_TOPIC),
            ("SubCmd.inputs:qosProfile", _REL_QOS)]
    _CC += [("OnTick.outputs:tick", "SubCmd.inputs:execIn"),
            ("Ctx.outputs:context", "SubCmd.inputs:context")]

og.Controller.edit(
    {"graph_path": GRAPH, "evaluator_name": "execution"},
    {K.CREATE_NODES: _CN, K.SET_VALUES: _SV, K.CONNECT: _CC},
)
log(f"OG {GRAPH} fresh 생성 완료 → {TOPIC} (domain {DOMAIN})")
if _TELEM:
    log(f"OG 텔레메트리 발행: {ARM_TOPIC}, {LEG_TOPIC}, {ODOM_TOPIC} "
        f"(RELIABLE) — gps/state 는 telemetry_bridge_node 가 odom 에서 파생")
if _CMD:
    log(f"다운링크 ON: ROS2SubscribeTwist ← {CMD_TOPIC} (RELIABLE)")

# 4) 시뮬 구동 ---------------------------------------------------------------
# physics_dt=1/500 → SpotFlatTerrainPolicy 요구 주기(spot_env.yaml dt=0.002).
# rendering_dt=1/50 → 카메라 50Hz (OG CameraHelper 기준).
import numpy as _np

world = World(stage_units_in_meters=1.0, physics_dt=1/500, rendering_dt=1/50)
world.reset()
omni.timeline.get_timeline_interface().play()
log("simulation playing — Ctrl+C to stop")

# ── 다운링크: SubCmd OG 출력 attr 핸들 ──────────────────────────────────
_cmd_state = {"lin": (0.0, 0.0, 0.0), "ang": (0.0, 0.0, 0.0),
              "rx": 0, "last_log": 0.0}
_cmd_lin_attr = _cmd_ang_attr = None
if _CMD:
    try:
        _cmd_lin_attr = og.Controller.attribute(
            f"{GRAPH}/SubCmd.outputs:linearVelocity")
        _cmd_ang_attr = og.Controller.attribute(
            f"{GRAPH}/SubCmd.outputs:angularVelocity")
        log("다운링크 SubCmd attr 핸들 OK")
    except Exception as e:
        log(f"다운링크 SubCmd 핸들 실패 {e!r} — 명령 수신 비활성")
        _CMD = False
else:
    log("GP_ROS2_CMD=0 → 다운링크(명령 수신) 비활성")

# ── SpotController (RL 보행 정책, in-process) ────────────────────────────
_ctrl = None
if _SPOT_CTRL:
    try:
        from spot_controller import SpotController
        _ctrl = SpotController(SPOT_PRIM)
        world.add_physics_callback("spot_ctrl", _ctrl.on_physics_step)
        log("SpotController 등록 — physics_callback 활성")
    except Exception as e:
        log(f"SpotController 초기화 실패 {e!r} — 보행 제어 비활성")
else:
    log("GP_SPOT_CONTROL=0 → SpotController 비활성(관측 전용)")


def _apply_cmd():
    """OG SubCmd 출력을 읽어 SpotController 에 전달(비차단).
    nonzero 명령일 때만 set_cmd_vel 호출 → 0.5s 타임아웃이 정상 작동."""
    if not _CMD or _cmd_lin_attr is None:
        return
    try:
        lin = _np.asarray(_cmd_lin_attr.get()).astype(float).ravel().tolist()
        ang = _np.asarray(_cmd_ang_attr.get()).astype(float).ravel().tolist()
    except Exception:
        return
    if len(lin) < 3 or len(ang) < 3:
        return
    _cmd_state["lin"], _cmd_state["ang"] = tuple(lin), tuple(ang)
    nonzero = any(abs(v) > 1e-6 for v in (*lin, *ang))
    if nonzero:
        _cmd_state["rx"] += 1
        if _ctrl is not None:
            _ctrl.set_cmd_vel(lin[0], lin[1], ang[2])
    now = time.time()
    if nonzero and now - _cmd_state["last_log"] > 1.0:
        _cmd_state["last_log"] = now
        log(f"[cmd] RX lin={[round(v,3) for v in lin]} "
            f"ang={[round(v,3) for v in ang]} (총 {_cmd_state['rx']}회)")


def _diag():
    try:
        rp = og.Controller.attribute(
            f"{GRAPH}/CreateRP.outputs:renderProductPath").get()
        cp = og.Controller.attribute(
            f"{GRAPH}/CreateRP.inputs:cameraPrim").get()
        log(f"DIAG cameraPrim={cp} renderProduct={rp!r}")
        if not rp:
            log("  ⚠ renderProductPath 비어있음 → 카메라 프레임 생성 안 됨")
    except Exception as e:
        log(f"DIAG 실패: {e!r}")


n = 0
try:
    while simulation_app.is_running():
        world.step(render=True)
        n += 1
        _apply_cmd()
        if n in (60, 150):
            _diag()
        if n % 300 == 0:
            t = omni.timeline.get_timeline_interface().get_current_time()
            log(f"stepped {n} | simTime={t:.2f} | cmd_rx={_cmd_state['rx']}")
            _diag()
except KeyboardInterrupt:
    log("중지(Ctrl+C)")
finally:
    simulation_app.close()
