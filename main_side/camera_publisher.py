"""standalone RealSense 카메라 퍼블리셔 (MCP/GUI 비의존, 결정적).

isaac-sim-mcp 스킬 원칙: MCP 가 불능일 때 python.sh standalone 사용.
씬 USD 를 열고(없으면 최소 구성), m0609 link_6 플랜지에 RealSense Camera 를
보장한 뒤, OG sensor_bridge(OnTick→ROS2Context(domain 130)→CreateRenderProduct
→ROS2CameraHelper rgb)를 만들고 시뮬을 계속 step 하여 `/cam/realsense/rgb`
를 발행한다. RMW 는 환경(run 스크립트가 FastDDS UDP-only 설정).

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
    # 로컬화 씬(terrain/fence/m0609/textures 동봉, ANYmal 만 공개 S3 URL).
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "scene", "gp_scene.usd"),
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

# ── D-확장 직결 uplink (ROS2 우회: in-process 캡처 → web_server POST) ──────
import json as _json
import queue as _queue
import threading as _threading
import urllib.request as _ul
import numpy as _np

C2 = os.environ.get("C2_INGEST_URL", "http://localhost:8000")
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

# 아티큘레이션 핸들(방어적 — API 명칭 버전차 대응)
_arts = {}
try:
    from isaacsim.core.prims import Articulation as _Art
    for _nm, _p in (("m0609", "/World/Robot/m0609"),
                    ("anymal", "/World/Robot/anymal")):
        try:
            a = _Art(_p)
            a.initialize()
            _arts[_nm] = a
            log(f"uplink: articulation {_nm} ({_p}) init OK")
        except Exception as e:
            log(f"uplink: articulation {_nm} init 실패 {e!r}")
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


_uth = _threading.Thread(target=_uplink_worker, daemon=True)
_uth.start()
log(f"uplink: worker 시작 → {C2} (ingest/frame, ingest/telemetry)")


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
    try:
        a = _arts.get("m0609")
        if a is not None:
            jp = a.get_joint_positions()
            tele["arm_q"] = [float(v) for v in _np.ravel(jp)][:6]
    except Exception:
        pass
    try:
        a = _arts.get("anymal")
        if a is not None:
            jp = a.get_joint_positions()
            tele["leg_q"] = [float(v) for v in _np.ravel(jp)][:12]
    except Exception:
        pass
    try:
        _xc.SetTime(Usd.TimeCode.Default())
        bp = omni.usd.get_context().get_stage().GetPrimAtPath(
            "/World/Robot/anymal")
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
        if _ann["rp"] is None and n % 30 == 0:
            _attach_annotators()
        if n % 12 == 0:                       # ≈ uplink 5Hz
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
