"""standalone RealSense 카메라 퍼블리셔 (MCP/GUI 비의존, 결정적).

isaac-sim-mcp 스킬 원칙: MCP 가 불능일 때 python.sh standalone 사용.
씬 USD 를 열고(없으면 최소 구성), Spot 팔 끝(arm0_link_wr1) 의 RealSense
Camera 를 보장한 뒤, OG sensor_bridge(OnTick→ROS2Context(domain 130)→
CreateRenderProduct→ROS2CameraHelper rgb)를 만들고 시뮬을 계속 step 하여
`/cam/realsense/rgb` 를 발행한다. 같은 그래프에서 ROS2 정공 텔레메트리
(Spot 단일 아티큘레이션 JointState + base Odometry)도 OG 노드로 발행
(GP_ROS2_TELEM=1, gps/state 는 시스템측 telemetry_bridge_node 가 odom 에서
파생). 로봇은 spot_with_arm(4족+팔 단일 아티큘레이션) — 과거 m0609+ANYmal
2-아티큘레이션이 아니라, arm/leg 분리는 _gather 에서 조인트명 prefix 로
수행한다. D-확장 HTTP /ingest 경로는 그대로 병행. RMW 는 환경 설정.

실행: main_side/run_camera_pub.sh
"""
import os

from isaacsim import SimulationApp

# GP_HEADLESS=0 → GUI 창 표시(사용자가 직접 봄), 1 → headless(웹 전송 전용).
# 둘 다 렌더링 동작(카메라 render product 생성·발행).
_HEADLESS = os.environ.get("GP_HEADLESS", "0") == "1"
simulation_app = SimulationApp(
    {"headless": _HEADLESS, "renderer": "RayTracedLighting"}
)

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
    # 이식성: 스크립트 상대(하드코딩 제거). main_side/scene/ 는 자체완결
    # 로컬화 씬(terrain/fence/textures 동봉, Spot 만 공개 S3 URL 레퍼런스).
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "scene", "gp_scene.usd"),
)
# Spot 팔 끝(손목) 의 RealSense — gp_scene.usd 에 이미 저장돼 있음.
CAM_PATH = "/World/Robot/arm0_link_wr1/realsense"
SPOT_PRIM = "/World/Robot"                 # spot_with_arm 단일 아티큘레이션 루트
BASE_PRIM = "/World/Robot/base"            # Spot 몸체(odom·sim-GPS 기준)
WRIST_PRIM = "/World/Robot/arm0_link_wr1"  # 카메라 부모(없을 때 생성 위치)
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
if os.environ.get("RMW_IMPLEMENTATION") != "rmw_fastrtps_cpp":
    log("  ⚠ RMW != rmw_fastrtps_cpp — Isaac↔C2 디스커버리 실패 위험!")
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

# 2) RealSense 카메라 보장 -------------------------------------------------
# gp_scene.usd 에 Spot 손목(arm0_link_wr1/realsense) 으로 이미 저장됨. 없을
# 때만(구 씬 등) 손목 자식으로 재생성 — Spot 팔 끝에 전방 hand-eye 로.
cam_prim = stage.GetPrimAtPath(CAM_PATH)
if not cam_prim.IsValid():
    # 'realsense' 프림 탐색(경로 변형 대비), 없으면 손목 하위 생성
    found = None
    rp = stage.GetPrimAtPath("/World/Robot")
    if rp.IsValid():
        for p in Usd.PrimRange(rp):
            if p.GetName() == "realsense":
                found = str(p.GetPath())
                break
    target = found or (WRIST_PRIM + "/realsense"
                       if stage.GetPrimAtPath(WRIST_PRIM).IsValid()
                       else CAM_PATH)
    cam = UsdGeom.Camera.Define(stage, target)
    W, H, F, HA, VA = 1280, 720, 24.0, 20.955, 11.787
    cam.GetFocalLengthAttr().Set(F)
    cam.GetHorizontalApertureAttr().Set(HA)
    cam.GetVerticalApertureAttr().Set(VA)
    cam.GetClippingRangeAttr().Set(Gf.Vec2f(0.05, 100.0))
    xf = UsdGeom.Xformable(cam.GetPrim())
    xf.ClearXformOpOrder()
    # Spot 손목 로컬: 전방(+X) 으로 0.06 이동 후 -Z→+X 로 회전(전방 주시)
    xf.AddTranslateOp().Set(Gf.Vec3f(0.06, 0, 0))
    xf.AddRotateXYZOp().Set(Gf.Vec3f(0, 90, 0))
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

# ── ROS2 정공 텔레메트리 발행 (OG, py3.11↔3.10 경계 안전) ─────────────────
# rclpy 를 Isaac(py3.11) 에서 import 하면 시스템 ROS2(py3.10) 와 ABI 충돌 →
# run_camera_pub.sh 가 의도적으로 시스템 ROS scrub. 따라서 텔레메트리도
# video(/cam/realsense/rgb) 와 동일하게 **OG 내부 ROS2 브리지**로만 발행한다.
# Spot 은 단일 아티큘레이션(arm0_*+다리 한 몸) — ROS2PublishJointState 는
# 아티큘레이션 단위라 arm/leg 를 OG 에서 못 가른다. 두 토픽 모두 Spot 전체
# JointState 를 싣고(C2 는 토픽명 불변·유효 데이터 수신), arm/leg 의미 분리는
# 라이브 경로인 HTTP _gather 가 조인트명 prefix 로 수행(아래 §_gather).
# base=Odometry. gps(NavSatFix)/state(String) 는 OG 정규노드가 없어 시스템측
# telemetry_bridge_node.py 가 /robot/odom 에서 파생. C2 ros_bridge 는
# RELIABLE 구독 → 발행도 RELIABLE 명시. HTTP /ingest 경로는 그대로 병행(무손상).
_TELEM = os.environ.get("GP_ROS2_TELEM", "1") == "1"
_REL_QOS = ('{"history":"keepLast","depth":10,'
            '"reliability":"reliable","durability":"volatile"}')
# Spot 단일 아티큘레이션 → arm/leg JointState·Odom 모두 같은 루트 대상.
ARM_PRIM, LEG_PRIM = SPOT_PRIM, SPOT_PRIM
ARM_TOPIC = "/dsr01/joint_states"          # C2 config.TOPICS["arm_joint"]
LEG_TOPIC = "/robot/leg_joint_states"      # C2 config.TOPICS["leg_joint"]
ODOM_TOPIC = "/robot/odom"                 # C2 config.TOPICS["odom"]

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
    ("CamRGB.inputs:qosProfile", "sensor_data"),
]
_CC = [
    ("OnTick.outputs:tick", "CreateRP.inputs:execIn"),
    ("CreateRP.outputs:execOut", "CamRGB.inputs:execIn"),
    ("CreateRP.outputs:renderProductPath",
     "CamRGB.inputs:renderProductPath"),
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
        ("Odo.inputs:chassisPrim", BASE_PRIM),   # Spot 몸체 rigid body
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

og.Controller.edit(
    {"graph_path": GRAPH, "evaluator_name": "execution"},
    {K.CREATE_NODES: _CN, K.SET_VALUES: _SV, K.CONNECT: _CC},
)
log(f"OG {GRAPH} fresh 생성 완료 → {TOPIC} (domain {DOMAIN})")
if _TELEM:
    log(f"OG 텔레메트리 발행: {ARM_TOPIC}, {LEG_TOPIC}, {ODOM_TOPIC} "
        f"(RELIABLE) — gps/state 는 telemetry_bridge_node 가 odom 에서 파생")
else:
    log("GP_ROS2_TELEM=0 → ROS2 텔레메트리 발행 비활성(HTTP /ingest 만)")

# 4) 시뮬 구동 — OnPlaybackTick 이 틱하도록 계속 step -----------------------
world = World(stage_units_in_meters=1.0)
world.reset()
omni.timeline.get_timeline_interface().play()
log("simulation playing — Ctrl+C to stop")

# ── D-확장 직결 uplink (ROS2 우회: in-process 캡처 → web_server POST) ──────
import json as _json
import queue as _queue
import threading as _threading
import urllib.request as _ul
import numpy as _np

C2 = os.environ.get("C2_INGEST_URL", "http://localhost:8000")
# D-확장 HTTP /ingest 업링크 토글 (GP_ROS2_TELEM 과 대칭, 기본 ON).
# 2-PC 정공(B/M2)에선 C2 가 ROS2 로 수신하므로 HTTP 까지 보내면 C2 가
# 동일 데이터를 ROS2·HTTP 두 경로로 받아 DB 이중 적재·WS 이중 emit.
# → 정공 운용 시 GP_HTTP_UPLINK=0 으로 HTTP 경로를 꺼 단일 소스화.
# 같은-PC(M1)는 ROS2 디스커버리 불가라 HTTP 가 유일 경로 → 1(기본) 유지.
_HTTP_UPLINK = os.environ.get("GP_HTTP_UPLINK", "1") == "1"
LAT0, LON0, ALT0 = 38.30, 127.50, 200.0     # sim 원점 기준점(설계 §S5 sim-GPS)
_OW, _OH = 640, 360

# rgb/depth 어노테이터 (render product 에 attach — 첫 rp 확보 후 지연 attach)
_rep = None
try:
    import omni.replicator.core as _rep
    log("uplink: omni.replicator.core 로드 OK")
except Exception as e:
    log(f"uplink: replicator 로드 실패 {e!r} — 영상 캡처 제한")
_ann = {"rgb": None, "depth": None, "rp": None}

# Spot 단일 아티큘레이션 핸들 + 조인트명(arm/leg 분리에 사용)
_arts = {}
_SPOT_DOF = []          # dof 이름 순서 (get_joint_positions 와 동일 순서)
try:
    from isaacsim.core.prims import Articulation as _Art
    try:
        a = _Art(SPOT_PRIM)
        a.initialize()
        _arts["spot"] = a
        try:
            _SPOT_DOF = [str(n) for n in (a.dof_names or [])]
        except Exception:
            _SPOT_DOF = []
        log(f"uplink: articulation spot ({SPOT_PRIM}) init OK "
            f"(dof={len(_SPOT_DOF)})")
    except Exception as e:
        log(f"uplink: articulation spot init 실패 {e!r}")
except Exception as e:
    log(f"uplink: Articulation API 로드 실패 {e!r} — joint 미수집")

_xc = UsdGeom.XformCache(Usd.TimeCode.Default())
_q: "_queue.Queue" = _queue.Queue(maxsize=2)
_ustat = {"frame_ok": 0, "frame_err": 0, "tele_ok": 0, "tele_err": 0}


def _resize_rgb(a):
    """cv2 없이 HxWx(3|4) → 360x640x3 RGB (스트라이드 다운샘플)."""
    if a is None or a.ndim < 3:
        return None
    h, w = a.shape[0], a.shape[1]
    ri = _np.linspace(0, h - 1, _OH).astype(_np.int32)
    ci = _np.linspace(0, w - 1, _OW).astype(_np.int32)
    return _np.ascontiguousarray(a[ri][:, ci, :3]).astype(_np.uint8)


def _sim_gps(x, y, z):
    import math
    dlat = (y / 6378137.0) * (180.0 / math.pi)
    dlon = (x / (6378137.0 * math.cos(math.radians(LAT0)))) * (180.0 / math.pi)
    return {"lat": LAT0 + dlat, "lon": LON0 + dlon, "alt": ALT0 + float(z)}


def _uplink_worker():
    while True:
        item = _q.get()
        if item is None:
            return
        frame, tele = item
        if tele is not None:
            try:
                r = _ul.Request(f"{C2}/ingest/telemetry",
                                data=_json.dumps(tele).encode(),
                                headers={"Content-Type": "application/json"},
                                method="POST")
                _ul.urlopen(r, timeout=2).read()
                _ustat["tele_ok"] += 1
            except Exception:
                _ustat["tele_err"] += 1
        if frame is not None:
            try:
                r = _ul.Request(
                    f"{C2}/ingest/frame?w={_OW}&h={_OH}&enc=rgb",
                    data=frame.tobytes(),
                    headers={"Content-Type": "application/octet-stream"},
                    method="POST")
                _ul.urlopen(r, timeout=2).read()
                _ustat["frame_ok"] += 1
            except Exception:
                _ustat["frame_err"] += 1


if _HTTP_UPLINK:
    _uth = _threading.Thread(target=_uplink_worker, daemon=True)
    _uth.start()
    log(f"uplink: worker 시작 → {C2} (ingest/frame, ingest/telemetry)")
else:
    log("GP_HTTP_UPLINK=0 → HTTP /ingest 업링크 비활성 "
        "(2-PC 정공: C2 는 ROS2 단일 경로로 수신, 이중수신 차단)")


def _attach_annotators():
    """첫 render product 확보 시 1회 rgb/depth 어노테이터 attach."""
    if _ann["rp"] or _rep is None:
        return
    try:
        rp = og.Controller.attribute(
            f"{GRAPH}/CreateRP.outputs:renderProductPath").get()
    except Exception:
        rp = None
    if not rp:
        return
    try:
        ra = _rep.AnnotatorRegistry.get_annotator("rgb")
        da = _rep.AnnotatorRegistry.get_annotator("distance_to_image_plane")
        ra.attach([rp])
        da.attach([rp])
        _ann.update(rgb=ra, depth=da, rp=rp)
        log(f"uplink: annotator attach OK (rp={rp})")
    except Exception as e:
        log(f"uplink: annotator attach 실패 {e!r}")


def _gather():
    """현재 sim 상태 in-process 수집 → 큐 적재(비차단)."""
    tele = {"ts": None}
    # Spot 단일 아티큘레이션 → 조인트명 prefix 로 arm/leg 분리
    # (arm0_* = 팔, fl_/fr_/hl_/hr_ = 4족 다리). dof명 없으면 전체를 arm_q.
    try:
        a = _arts.get("spot")
        if a is not None:
            jp = [float(v) for v in _np.ravel(a.get_joint_positions())]
            if _SPOT_DOF and len(_SPOT_DOF) == len(jp):
                arm = [v for n, v in zip(_SPOT_DOF, jp)
                       if n.startswith("arm0_")]
                leg = [v for n, v in zip(_SPOT_DOF, jp)
                       if n[:3] in ("fl_", "fr_", "hl_", "hr_")]
                tele["arm_q"], tele["leg_q"] = arm[:8], leg[:12]
            else:
                tele["arm_q"] = jp[:8]
    except Exception:
        pass
    try:
        _xc.SetTime(Usd.TimeCode.Default())
        _st = omni.usd.get_context().get_stage()
        bp = _st.GetPrimAtPath(BASE_PRIM)
        if not (bp and bp.IsValid()):
            bp = _st.GetPrimAtPath(SPOT_PRIM)
        m = _xc.GetLocalToWorldTransform(bp)
        tr = m.ExtractTranslation()
        x, y, z = float(tr[0]), float(tr[1]), float(tr[2])
        tele["odom"] = {"x": x, "y": y, "z": z}
        tele["gps"] = _sim_gps(x, y, z)
    except Exception:
        pass
    frame = None
    if _ann["rgb"] is not None:
        try:
            d = _ann["rgb"].get_data()
            frame = _resize_rgb(_np.asarray(d))
        except Exception:
            pass
    try:
        _q.put_nowait((frame, tele))
    except _queue.Full:
        pass

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
        if _HTTP_UPLINK:                       # HTTP /ingest 전용 수집 경로
            if _ann["rp"] is None and n % 30 == 0:
                _attach_annotators()
            if n % 12 == 0:                   # ≈ uplink 5Hz
                _gather()
        if n in (60, 150):
            _diag()
        if n % 300 == 0:
            t = omni.timeline.get_timeline_interface().get_current_time()
            log(f"stepped {n} | simTime={t:.2f} | uplink "
                f"frame ok/err={_ustat['frame_ok']}/{_ustat['frame_err']} "
                f"tele ok/err={_ustat['tele_ok']}/{_ustat['tele_err']} "
                f"ann={'Y' if _ann['rp'] else 'N'} arts={list(_arts)}")
            _diag()
except KeyboardInterrupt:
    log("중지(Ctrl+C)")
finally:
    try:
        _q.put_nowait(None)
    except Exception:
        pass
    simulation_app.close()
