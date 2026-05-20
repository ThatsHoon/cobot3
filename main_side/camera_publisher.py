"""standalone 2-카메라 퍼블리셔 — Go2 몸통 앞뒤 RealSense (MCP/GUI 비의존, 결정적).

씬 USD 를 열고 robot prim 참조를 go2.usd 로 교체한 뒤, 몸통 앞뒤(base)에
Camera 프림을 생성해 OG sensor_bridge 로 `/cam/front/rgb` `/cam/rear/rgb` 를
발행한다. 같은 그래프에서 ROS2 정공 텔레메트리(Go2 12-DOF 다리 JointState +
base Odometry + TF)도 발행(GP_ROS2_TELEM=1). 다운링크(/robot/cmd_vel) 는
OG ROS2SubscribeTwist 로 수신 → Go2WtwController.set_cmd_vel 로 전달 →
walk-these-ways RL 보행 정책. HTTP /ingest 경로 제거 — ROS2 정공 단일 경로.

prim 경로(/World/Robot)·토픽명(/robot/*·/cam/*) 은 Spot 때와 동일하게 유지 →
OG Odom/JointState/TF 와이어링·sub1_side(C2) 전부 무수정. go2.usd 가
/World/Robot 에 컴포즈되어 /World/Robot/base 가 chassis 로 그대로 동작.

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
# Go2: gp_scene.usd 의 /World/Robot 에는 spot_with_arm 구조가 베이크되어
# 있어 go2.usd 를 그 위에 ref 하면 ArticulationRoot 컴포지션이 깨진다.
# → 깨끗한 /World/Go2 프림을 따로 만들고 /World/Robot 은 비활성화한다.
# 토픽명(/robot/*·/cam/*) 은 동일 유지 → sub1_side(C2) 무수정.
ROBOT_PRIM     = "/World/Go2"          # go2.usd ref Xform (TF 루트)
# go2.usd 의 ArticulationRoot 는 base 링크(/World/Go2/base) — 라이브 실측.
# SingleArticulation·OG JointState·Odom chassis 는 이 경로를 써야 함.
ART_PRIM       = "/World/Go2/base"
SPOT_PRIM      = ART_PRIM              # OG 와이어링 하위호환 별칭(=articulation)
BASE_PRIM      = "/World/Go2/base"
CAM_FRONT_PATH = "/World/Go2/base/camera_front"
CAM_REAR_PATH  = "/World/Go2/base/camera_rear"
_STALE_ROBOT   = "/World/Robot"
GRAPH  = "/World/Graphs/sensor_bridge"
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

# 2) 로봇 참조 교체(spot_with_arm → go2) + 앞뒤 카메라 생성 -------------------
# NVIDIA go2.usd 는 walk-these-ways 학습 컨벤션과 달라 보행 전이 실패(검증):
# 기립 OK 이나 전진 보행 불가. → 정책이 실제 학습한 Unitree go2.urdf 를
# import_go2_unitree.py 로 USD 변환한 로컬 자산을 사용(학습 컨벤션 일치).
# defaultPrim=/go2_description, artroot=/go2_description/base → ref 시
# /World/Go2/base 로 컴포즈(ART_PRIM 와 일치).
_GO2_USD = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "go2_unitree", "go2_unitree.usd")
if not os.path.isfile(_GO2_USD):  # 폴백: 임포트 USD 없으면 S3 NVIDIA go2
    try:
        from isaacsim.core.utils.nucleus import get_assets_root_path as _gar
        _assets_root = _gar()
    except Exception:
        _assets_root = ("https://omniverse-content-production.s3-us-west-2"
                        ".amazonaws.com/Assets/Isaac/5.1")
    _GO2_USD = _assets_root + "/Isaac/Robots/Unitree/Go2/go2.usd"

# 스테일 spot 프림 비활성화 (gp_scene.usd 베이크 구조가 go2 컴포지션 오염)
_stale = stage.GetPrimAtPath(_STALE_ROBOT)
if _stale.IsValid():
    _stale.SetActive(False)
    log(f"스테일 {_STALE_ROBOT}(spot) 비활성화")

# 깨끗한 /World/Go2: 베이크된(GUI 저장) 스테일 /World/Go2 가 있으면
# 통째로 제거 후 fresh Xform + go2_unitree.usd ref (구조 오염 차단).
if stage.GetPrimAtPath(ROBOT_PRIM).IsValid():
    stage.RemovePrim(ROBOT_PRIM)
    for _ in range(5):
        simulation_app.update()
    log(f"베이크된 스테일 {ROBOT_PRIM} 제거 (fresh 재생성)")
_go2 = stage.DefinePrim(ROBOT_PRIM, "Xform")
_go2.GetReferences().ClearReferences()
_go2.GetReferences().AddReference(_GO2_USD)
# 시나리오: /World/Cube 의 XY '근처' 실제 터레인 표면에서 출발 →
# /World/Cone 까지 자율 주행. Cube 는 터레인보다 ~7m 떠 있는 박스라
# Cube z 무의미 → 터레인 collider 메시에서 Cube XY 최근접 정점을 찾아
# 그 위(+_CLEAR)에 스폰(고체 지면 보장; 정확 Cube XY 는 메시 빈틈/경사로
# −5042m 추락 검증됨). nav_goal = Cone 중심 XY.
from pxr import Usd as _U
import numpy as _np
_bc = UsdGeom.BBoxCache(_U.TimeCode.Default(), ["default", "render"])
CUBE_PRIM = "/World/Cube"
CONE_PRIM = "/World/Cone"
TERR_PRIM = ("/World/Terrain/Meshes/Sketchfab_model/root/"
             "GLTF_SceneRootNode/TerrainNode_0/Object_4/Object_0")
_CLEAR = float(os.environ.get("GP_GO2_SPAWN_CLEAR", "0.45"))

# DMZ_Zone 런타임 빌드 — gp_scene.usd 가 binary 라 직접 편집 불가. world (0,0)
# 부근에 80m×80m 평지 + guard_tower/chainlink_fence USDZ instance + patrol
# marker Xform 을 매번 fresh 생성(idempotent). OG sensor_bridge 와 prim 경로
# 분리 — 단일 OG edit 원칙 무영향.
_DMZ_ZONE_PRIM = "/World/DMZ_Zone"
_DMZ_HOME      = (0.0, 0.0)
_DMZ_PATROL_W  = (-24.0, -12.0)
_DMZ_PATROL_E  = (24.0, -12.0)
_DMZ_FENCE_N_Y = 16.0
# _HERE: camera_publisher.py 가 위치한 main_side 디렉토리 절대경로
_HERE = os.path.dirname(os.path.abspath(__file__))
_DMZ_GTOWER    = os.path.join(
    _HERE, "scene", "assets", "props", "guard_tower",
    "Guard_Tower_Free_Asset.usdz")
_DMZ_FENCE_USD = os.path.join(
    _HERE, "scene", "assets", "props", "chainlink_fence",
    "chainlink_fence_tileable.usdz")


def _build_dmz_zone(_stage):
    """world (0,0) 부근에 DMZ patrol zone 빌드 (Cube/Cone 영역과 분리).
    USDZ 자산 없으면 placeholder Cube 로 fallback."""
    if _stage.GetPrimAtPath(_DMZ_ZONE_PRIM).IsValid():
        _stage.RemovePrim(_DMZ_ZONE_PRIM)
    _root = _stage.DefinePrim(_DMZ_ZONE_PRIM, "Xform")
    _ground = _stage.DefinePrim(f"{_DMZ_ZONE_PRIM}/Ground", "Cube")
    _gxf = UsdGeom.Xformable(_ground)
    _gxf.AddScaleOp().Set(Gf.Vec3f(40.0, 40.0, 0.05))
    _gxf.AddTranslateOp().Set(Gf.Vec3f(0.0, 0.0, -0.05))
    if os.path.exists(_DMZ_GTOWER):
        for _i, (_x, _y) in enumerate(
                [(-24, 10), (24, 10), (-24, 14), (24, 14)]):
            _t = _stage.DefinePrim(f"{_DMZ_ZONE_PRIM}/GTower_{_i}", "Xform")
            _t.GetReferences().AddReference(_DMZ_GTOWER)
            UsdGeom.Xformable(_t).AddTranslateOp().Set(
                Gf.Vec3f(float(_x), float(_y), 0.0))
    if os.path.exists(_DMZ_FENCE_USD):
        for _i, (_x, _y, _yaw) in enumerate(
                [(0.0, _DMZ_FENCE_N_Y, 0.0), (0.0, -12.0, 0.0),
                 (-24.0, 2.0, 90.0), (24.0, 2.0, 90.0)]):
            _f = _stage.DefinePrim(f"{_DMZ_ZONE_PRIM}/Fence_{_i}", "Xform")
            _f.GetReferences().AddReference(_DMZ_FENCE_USD)
            _fxf = UsdGeom.Xformable(_f)
            _fxf.AddTranslateOp().Set(Gf.Vec3f(float(_x), float(_y), 0.0))
            _fxf.AddRotateZOp().Set(float(_yaw))
    # patrol markers (시각자산 없는 순수 Xform)
    for _name, (_x, _y) in (("Home_Marker", _DMZ_HOME),
                            ("Patrol_W_Marker", _DMZ_PATROL_W),
                            ("Patrol_E_Marker", _DMZ_PATROL_E),
                            ("Fence_N_Marker", (0.0, _DMZ_FENCE_N_Y))):
        _m = _stage.DefinePrim(f"{_DMZ_ZONE_PRIM}/{_name}", "Xform")
        UsdGeom.Xformable(_m).AddTranslateOp().Set(
            Gf.Vec3f(float(_x), float(_y), 0.0))
    log(f"DMZ_Zone 빌드 — home(0,0), patrol(-24~24,-12), fence_n(y=16) "
        f"@ {_DMZ_ZONE_PRIM} (gtower={os.path.exists(_DMZ_GTOWER)} "
        f"fence={os.path.exists(_DMZ_FENCE_USD)})")


_build_dmz_zone(stage)

# Go2 spawn zone 선택: cube=기존 Cube 위 (-714,952), dmz=DMZ_Zone Home (0,0)
_ZONE = os.environ.get("GP_GO2_SPAWN_ZONE", "cube").lower()
log(f"GP_GO2_SPAWN_ZONE={_ZONE}")

_spawn = Gf.Vec3d(0.0, 0.0, 0.42)
_cone_xy = None
_cb = stage.GetPrimAtPath(CUBE_PRIM)
_tm = stage.GetPrimAtPath(TERR_PRIM)


def _terrain_nearest_vertex(tm_prim, tx, ty):
    """터레인 메시에서 (tx, ty) 에 가장 가까운 world vertex 반환 (gx, gy, gz)."""
    _tmx = UsdGeom.Xformable(tm_prim).ComputeLocalToWorldTransform(
        _U.TimeCode.Default())
    _pts = UsdGeom.Mesh(tm_prim).GetPointsAttr().Get()
    _P = _np.array([[p[0], p[1], p[2]] for p in _pts], dtype=float)
    _M = _np.array([[_tmx[i][j] for j in range(4)] for i in range(4)],
                   dtype=float)
    _W = (_np.c_[_P, _np.ones(len(_P))] @ _M)[:, :3]
    _i = int(_np.argmin((_W[:, 0] - tx) ** 2 + (_W[:, 1] - ty) ** 2))
    return float(_W[_i, 0]), float(_W[_i, 1]), float(_W[_i, 2])


# spawn / cone 결정 — zone 분기
if _ZONE == "dmz":
    # DMZ_Zone Home_Marker(0,0) 위 spawn. terrain 가 있으면 nearest vertex z,
    # 없으면 DMZ Ground plane 위(z=0.05+_CLEAR).
    if _tm and _tm.IsValid():
        try:
            _gx, _gy, _gz = _terrain_nearest_vertex(_tm, *_DMZ_HOME)
            _spawn = Gf.Vec3d(_gx, _gy, _gz + _CLEAR)
            log(f"[DMZ] home(0,0) → terrain 최근접 ({_gx:.1f},{_gy:.1f},"
                f"z={_gz:.2f}) → spawn {tuple(round(float(v),2) for v in _spawn)}")
        except Exception as _e:
            _spawn = Gf.Vec3d(0.0, 0.0, 0.05 + _CLEAR)
            log(f"[DMZ] terrain nearest 실패 ({_e!r}) → Ground 위 spawn {tuple(_spawn)}")
    else:
        _spawn = Gf.Vec3d(0.0, 0.0, 0.05 + _CLEAR)
        log(f"[DMZ] terrain 없음 → Ground 위 spawn {tuple(_spawn)}")
    _cone_xy = _DMZ_PATROL_E
    log(f"[DMZ] nav_goal = Patrol_E_Marker {_cone_xy}")
elif _cb and _cb.IsValid() and _tm and _tm.IsValid():
    _cm = UsdGeom.Xformable(_cb).ComputeLocalToWorldTransform(
        _U.TimeCode.Default())
    _ct = _cm.ExtractTranslation()
    _cx, _cy = float(_ct[0]), float(_ct[1])
    _gx, _gy, _gz = _terrain_nearest_vertex(_tm, _cx, _cy)
    _d = ((_gx - _cx) ** 2 + (_gy - _cy) ** 2) ** 0.5
    _spawn = Gf.Vec3d(_gx, _gy, _gz + _CLEAR)
    log(f"Cube XY({_cx:.1f},{_cy:.1f}) → 최근접 터레인 정점"
        f"({_gx:.1f},{_gy:.1f},z={_gz:.2f}) {_d:.1f}m → spawn "
        f"{tuple(round(float(v),2) for v in _spawn)} (터레인+{_CLEAR})")
    _cn = stage.GetPrimAtPath(CONE_PRIM)
    if _cn and _cn.IsValid():
        _r2 = _bc.ComputeWorldBound(_cn).ComputeAlignedRange()
        _m2, _x2 = _r2.GetMin(), _r2.GetMax()
        _cone_xy = ((float(_m2[0]) + float(_x2[0])) / 2.0,
                    (float(_m2[1]) + float(_x2[1])) / 2.0)
        log(f"Cone@({_cone_xy[0]:.2f},{_cone_xy[1]:.2f}) → nav_goal "
            f"(Cube→Cone ≈ "
            f"{((_cone_xy[0]-_spawn[0])**2 + (_cone_xy[1]-_spawn[1])**2)**0.5:.0f}m)")
    else:
        log(f"⚠ {CONE_PRIM} 없음 — nav 비활성")
else:
    log(f"⚠ {CUBE_PRIM}/{TERR_PRIM} 미발견 — 기본 스폰 (0,0,0.42)")

# 씬 랜드마크 dump → landmarks_pub.py 가 읽어 /scene/landmarks (latched) 발행.
# patrol controller(C2) 가 sortie 시 waypoint 구성에 사용.
import json as _json
try:
    _lm = {
        "zone": _ZONE,
        "cube": {"x": float(_spawn[0]), "y": float(_spawn[1]),
                 "z": float(_spawn[2])},
    }
    if _cone_xy is not None:
        _lm["cone"] = {"x": float(_cone_xy[0]), "y": float(_cone_xy[1]),
                       "z": 0.0}
    # 울타리 세그먼트 — gp_scene 의 /World/Fence/* 또는
    # /World/barbed_wire_fence/* 가 있으면 중심 XY 수집.
    _fence_paths = []
    for _p in stage.Traverse():
        _pp = str(_p.GetPath())
        if (_pp.startswith("/World/Fence/")
                or _pp.startswith("/World/barbed_wire_fence")):
            if UsdGeom.Xformable(_p):
                _fence_paths.append(_pp)
    _lm["fence"] = []
    for _fp in _fence_paths[:8]:
        _fprim = stage.GetPrimAtPath(_fp)
        _frange = _bc.ComputeWorldBound(_fprim).ComputeAlignedRange()
        if _frange.IsEmpty():
            continue
        _fmn, _fmx = _frange.GetMin(), _frange.GetMax()
        _lm["fence"].append({
            "x": 0.5 * (float(_fmn[0]) + float(_fmx[0])),
            "y": 0.5 * (float(_fmn[1]) + float(_fmx[1])),
            "z": 0.5 * (float(_fmn[2]) + float(_fmx[2])),
        })
    # DMZ_Zone 의 home/cone/fence 도 항상 dump (zone 무관, web 가시화용)
    _lm["dmz_home"] = {"x": float(_DMZ_HOME[0]), "y": float(_DMZ_HOME[1]), "z": 0.0}
    _lm["dmz_cone"] = {"x": float(_DMZ_PATROL_E[0]), "y": float(_DMZ_PATROL_E[1]), "z": 0.0}
    _lm["dmz_patrol_w"] = {"x": float(_DMZ_PATROL_W[0]), "y": float(_DMZ_PATROL_W[1]), "z": 0.0}
    _lm["dmz_fence"] = [
        {"x": -40.0, "y": float(_DMZ_FENCE_N_Y), "z": 0.0},
        {"x":  40.0, "y": float(_DMZ_FENCE_N_Y), "z": 0.0},
    ]
    with open("/tmp/cobot3_landmarks.json", "w") as _f:
        _json.dump(_lm, _f)
    log(f"landmarks dump → /tmp/cobot3_landmarks.json "
        f"(zone={_ZONE}, cube,cone,fence×{len(_lm['fence'])}, dmz_*)")
except Exception as _e:
    log(f"⚠ landmarks dump 실패: {_e!r}")
_xf_g = UsdGeom.Xformable(_go2)
_xf_g.ClearXformOpOrder()
_xf_g.AddTranslateOp().Set(_spawn)
log(f"{ROBOT_PRIM} 생성 → go2.usd ref @ {tuple(round(float(v),2) for v in _spawn)}")

# go2.usd S3 최초 다운로드/컴포지션 대기 (spot 보다 김). 부족하면
# go2_controller._setup 가 매 physics step 재시도하므로 복원됨.
for _ in range(120):
    simulation_app.update()

# ── 접지 마찰 안전망 (씬에 이미 있으면 스킵) ──────────────────────────
# 원칙: 마찰은 gp_scene.usd 에 GUI 로 저작·저장된 것이 단일 소스.
# 단, 씬에 마찰 바인딩이 없을 때(미저장/구버전 씬)만 무마찰→전복을
# 막기 위한 안전망으로 런타임 0.8 바인딩(학습 분포 0.05~4.5 내)을 적용.
try:
    from pxr import UsdShade as _UsdShade, UsdPhysics as _UP
    # 지형 collider 중 이미 physics material 바인딩된 게 있나?
    _scene_has_fric = False
    for _p in stage.Traverse():
        if not _p.HasAPI(_UP.CollisionAPI):
            continue
        _pp = str(_p.GetPath())
        if _pp.startswith("/World/Terrain") or "GP_NoiseTerrain" in _pp:
            _r = _p.GetRelationship("material:binding:physics")
            if _r and _r.GetTargets():
                _scene_has_fric = True
                break
    if _scene_has_fric:
        log("접지 마찰: 씬에 이미 바인딩됨 → 런타임 패치 스킵(씬이 단일 소스)")
    else:
        _PM = "/World/Physics_Materials/physics_material"
        _pmp = stage.GetPrimAtPath(_PM)
        if not (_pmp and _pmp.IsValid()):
            _UsdShade.Material.Define(stage, _PM)
            _pmp = stage.GetPrimAtPath(_PM)
        if not _pmp.HasAPI(_UP.MaterialAPI):
            _UP.MaterialAPI.Apply(_pmp)
        _mapi = _UP.MaterialAPI(_pmp)
        for _attr, _v in (("CreateStaticFrictionAttr", 0.8),
                          ("CreateDynamicFrictionAttr", 0.8),
                          ("CreateRestitutionAttr", 0.0)):
            getattr(_mapi, _attr)(_v)
        _pm_mat = _UsdShade.Material(_pmp)

        def _bind_phys(prim):
            _UsdShade.MaterialBindingAPI.Apply(prim)
            _UsdShade.MaterialBindingAPI(prim).Bind(
                _pm_mat,
                bindingStrength=_UsdShade.Tokens.weakerThanDescendants,
                materialPurpose="physics")

        _nb = 0
        for _p in stage.Traverse():
            if not _p.HasAPI(_UP.CollisionAPI):
                continue
            _pp = str(_p.GetPath())
            if (_pp.startswith("/World/Terrain")
                    or "GP_NoiseTerrain" in _pp
                    or _pp.startswith(ROBOT_PRIM)):
                _bind_phys(_p); _nb += 1
        log(f"접지 마찰 안전망 적용(씬 미저장) — collider {_nb}개 0.8 바인딩")
except Exception as _e:
    log(f"⚠ 마찰 안전망 처리 실패: {_e!r}")

# 진단: go2.usd 컴포지션 후 실제 ArticulationRoot 경로 1회 덤프
try:
    from pxr import Usd as _Usd, UsdPhysics as _UsdPhysics
    _g = stage.GetPrimAtPath(ROBOT_PRIM)
    _lines, _root = [], None
    if _g and _g.IsValid():
        for _p in _Usd.PrimRange(_g):
            _pp = str(_p.GetPath())
            _is_art = _p.HasAPI(_UsdPhysics.ArticulationRootAPI)
            if _is_art and _root is None:
                _root = _pp
            if len(_lines) < 80:
                _lines.append(f"{_pp} [{_p.GetTypeName()}]"
                              f"{' <ARTROOT>' if _is_art else ''}")
    with open('/tmp/go2_tree.txt', 'w') as _f:
        _f.write(f"ROBOT_PRIM={ROBOT_PRIM} artroot={_root}\n"
                 + "\n".join(_lines) + "\n")
    log(f"go2 tree dump → /tmp/go2_tree.txt (artroot={_root})")
except Exception as _e:
    log(f"go2 tree dump 실패: {_e!r}")

# 카메라 방향: USD 카메라는 기본 -Z 를 보고 +Y 가 up. 그냥 rotateXYZ
# (0,∓90,0) 만 주면 시선은 ±X(전후방) 맞지만 up 이 world +Y 로 누워
# 영상이 90° 회전(세로 띠)됨. → orient 쿼터니언으로 "시선 ±X / up
# world +Z" 를 정확히 지정. 종횡비: 렌더 640x360(16:9)에 맞춰
# verticalAperture = horizontalAperture * 360/640 (수평 찌그러짐 제거).
_HAP = 20.955
_VAP = _HAP * 360.0 / 640.0          # 16:9 정합 ≈ 11.79
# 전방: 시선 +X, up +Z  → quat(w,x,y,z)=(0.5, 0.5,-0.5,-0.5)
_Q_FRONT = Gf.Quatf(0.5, Gf.Vec3f(0.5, -0.5, -0.5))
# 후방: 시선 -X, up +Z  → quat=(0.5, 0.5, 0.5, 0.5)
_Q_REAR = Gf.Quatf(0.5, Gf.Vec3f(0.5, 0.5, 0.5))


def _mk_cam(path, translate, quat, label):
    if stage.GetPrimAtPath(path).IsValid():
        stage.RemovePrim(path)
    cam = UsdGeom.Camera.Define(stage, path)
    xf = UsdGeom.Xformable(cam.GetPrim())
    xf.ClearXformOpOrder()
    xf.AddTranslateOp().Set(translate)
    xf.AddOrientOp().Set(quat)
    cam.GetFocalLengthAttr().Set(10.5)
    cam.GetHorizontalApertureAttr().Set(_HAP)
    cam.GetVerticalApertureAttr().Set(_VAP)
    log(f"{label} 생성: {path} (시선 정방향, up=+Z, 16:9)")


_mk_cam(CAM_FRONT_PATH, Gf.Vec3f(0.22, 0.0, 0.06), _Q_FRONT, "전방 카메라")
_mk_cam(CAM_REAR_PATH, Gf.Vec3f(-0.22, 0.0, 0.06), _Q_REAR, "후방 카메라")

# DMZ Sentry M6: 검사 카메라(가상 짐벌) — Go2 base 위 mount. pan/tilt/zoom 은
# /robot/inspect/command 수신 시 _apply_inspect_cmd 가 Xform·focalLength 갱신.
CAM_INSPECT_PATH = "/World/Go2/base/camera_inspect"
_mk_cam(CAM_INSPECT_PATH, Gf.Vec3f(0.0, 0.0, 0.30), _Q_FRONT, "검사 카메라(짐벌)")

# 3) OG sensor_bridge — 기존(비기능 가능) 제거 후 항상 fresh 재생성 ----------
try:
    import omni.graph.tools.ogn as _ogn  # noqa
    for nt in ("isaacsim.ros2.bridge.ROS2CameraHelper",
               "isaacsim.ros2.bridge.ROS2Context"):
        ok = nt in og.GraphRegistry().get_node_types()
        log(f"nodetype {nt}: registered={ok}")
except Exception as e:
    log(f"nodetype 등록확인 스킵({e!r})")

# 폴루션 자가치유: GUI 저장 등으로 gp_scene.usd 에 베이크된 스테일
# sensor_bridge 그래프(죽은 /World/Robot 참조 → OG/physics view 붕괴)를
# 알려진 모든 경로에서 제거 후 fresh 재생성. 마찰 바인딩은 보존됨.
_STALE_GRAPHS = [GRAPH, "/World/Xform_01/Graphs/sensor_bridge",
                 "/World/Graphs/sensor_bridge"]
_removed = []
for _gp in _STALE_GRAPHS:
    if stage.GetPrimAtPath(_gp).IsValid():
        stage.RemovePrim(_gp)
        _removed.append(_gp)
if _removed:
    for _ in range(10):
        simulation_app.update()
    log(f"스테일 OG 그래프 제거: {_removed} (fresh 재생성)")

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
CMD_TOPIC  = os.environ.get("GP_CMD_TOPIC", "/robot/cmd_vel")
LEG_PRIM   = SPOT_PRIM
LEG_TOPIC  = "/robot/leg_joint_states"
ODOM_TOPIC = "/robot/odom"

K = og.Controller.Keys
_CN = [
    ("OnTick",   "omni.graph.action.OnPlaybackTick"),
    ("Ctx",      "isaacsim.ros2.bridge.ROS2Context"),
    ("RPFront",  "isaacsim.core.nodes.IsaacCreateRenderProduct"),
    ("CamFront", "isaacsim.ros2.bridge.ROS2CameraHelper"),
    # CamDepth/CamInfo/CamPCL 제거: Isaac 5.1 ROS2CameraHelper 가 type
    # "depth"/"camera_info"/"depth_pcl" 미지원 → 매 프레임 "type is not
    # supported" 폭주(수천 에러)·렌더 파이프라인 손상. rgb 2종만 유지.
    ("RPRear",   "isaacsim.core.nodes.IsaacCreateRenderProduct"),
    ("CamRear",  "isaacsim.ros2.bridge.ROS2CameraHelper"),
    # DMZ Sentry M6: 검사 카메라 RGB
    ("RPInspect",  "isaacsim.core.nodes.IsaacCreateRenderProduct"),
    ("CamInspect", "isaacsim.ros2.bridge.ROS2CameraHelper"),
    # 검사 카메라 명령 — Isaac 5.1 OG 에 ROS2SubscribeString 미등록(2026-05-20
    # 라이브 검증) → 사이드카 inspect_relay.py(rclpy) 가 /robot/inspect/command
    # 구독해 /tmp/cobot3_inspect_cmd.json 에 dump, 본 process 가 mtime 폴.
]
_SV = [
    ("Ctx.inputs:domain_id",        DOMAIN),
    ("RPFront.inputs:cameraPrim",   CAM_FRONT_PATH),
    ("RPFront.inputs:width",        640),
    ("RPFront.inputs:height",       360),
    ("CamFront.inputs:topicName",   "/cam/front/rgb"),
    ("CamFront.inputs:frameId",     "camera_front"),
    ("CamFront.inputs:type",        "rgb"),
    ("CamFront.inputs:qosProfile",  _SENSOR_QOS),
    ("RPRear.inputs:cameraPrim",    CAM_REAR_PATH),
    ("RPRear.inputs:width",         640),
    ("RPRear.inputs:height",        360),
    ("CamRear.inputs:topicName",    "/cam/rear/rgb"),
    ("CamRear.inputs:frameId",      "camera_rear"),
    ("CamRear.inputs:type",         "rgb"),
    ("CamRear.inputs:qosProfile",   _SENSOR_QOS),
    # DMZ Sentry M6: 검사 카메라 RGB + 명령 구독
    ("RPInspect.inputs:cameraPrim",  CAM_INSPECT_PATH),
    ("RPInspect.inputs:width",       640),
    ("RPInspect.inputs:height",      360),
    ("CamInspect.inputs:topicName",  "/cam/inspect/rgb"),
    ("CamInspect.inputs:frameId",    "camera_inspect"),
    ("CamInspect.inputs:type",       "rgb"),
    ("CamInspect.inputs:qosProfile", _SENSOR_QOS),
]
_CC = [
    ("OnTick.outputs:tick",              "RPFront.inputs:execIn"),
    ("RPFront.outputs:execOut",          "CamFront.inputs:execIn"),
    ("RPFront.outputs:renderProductPath","CamFront.inputs:renderProductPath"),
    ("Ctx.outputs:context",              "CamFront.inputs:context"),
    ("OnTick.outputs:tick",              "RPRear.inputs:execIn"),
    ("RPRear.outputs:execOut",           "CamRear.inputs:execIn"),
    ("RPRear.outputs:renderProductPath", "CamRear.inputs:renderProductPath"),
    ("Ctx.outputs:context",              "CamRear.inputs:context"),
    # DMZ Sentry M6
    ("OnTick.outputs:tick",                "RPInspect.inputs:execIn"),
    ("RPInspect.outputs:execOut",          "CamInspect.inputs:execIn"),
    ("RPInspect.outputs:renderProductPath", "CamInspect.inputs:renderProductPath"),
    ("Ctx.outputs:context",                "CamInspect.inputs:context"),
]
if _TELEM:
    _CN += [
        ("SimTime", "isaacsim.core.nodes.IsaacReadSimulationTime"),
        ("LegJS",   "isaacsim.ros2.bridge.ROS2PublishJointState"),
        ("Odo",     "isaacsim.core.nodes.IsaacComputeOdometry"),
        ("OdoPub",  "isaacsim.ros2.bridge.ROS2PublishOdometry"),
        ("TF",      "isaacsim.ros2.bridge.ROS2PublishTransformTree"),
    ]
    _SV += [
        ("LegJS.inputs:targetPrim",        LEG_PRIM),
        ("LegJS.inputs:topicName",         LEG_TOPIC),
        ("LegJS.inputs:qosProfile",        _REL_QOS),
        ("Odo.inputs:chassisPrim",         BASE_PRIM),
        ("OdoPub.inputs:topicName",        ODOM_TOPIC),
        ("OdoPub.inputs:odomFrameId",      "odom"),
        # OG ROS2PublishTransformTree 가 발행하는 base link frame_id 는 USD
        # prim 이름인 "Go2" — OdoPub 도 동일 이름 써야 TF tree 가 끊기지 않음.
        # (이전 "base_link" 는 OG TF 와 다른 frame 으로 분리되어 Nav2 가
        # robot base 위치 못 찾는 원인이었음 — 2026-05-20 라이브 검증).
        ("OdoPub.inputs:chassisFrameId",   "Go2"),
        ("OdoPub.inputs:qosProfile",       _REL_QOS),
        ("TF.inputs:targetPrims",          [ROBOT_PRIM]),
        # Nav2 TransformListener 는 RELIABLE 기대 — BEST_EFFORT 발행 시
        # "incompatible QoS" 로 메시지 폐기 → odom→base_link 미수신 → 모든 goal 실패.
        ("TF.inputs:qosProfile",           _REL_QOS),
    ]
    _CC += [
        ("OnTick.outputs:tick",                "LegJS.inputs:execIn"),
        ("OnTick.outputs:tick",                "Odo.inputs:execIn"),
        ("Odo.outputs:execOut",                "OdoPub.inputs:execIn"),
        ("Ctx.outputs:context",                "LegJS.inputs:context"),
        ("Ctx.outputs:context",                "OdoPub.inputs:context"),
        ("SimTime.outputs:simulationTime",     "LegJS.inputs:timeStamp"),
        ("SimTime.outputs:simulationTime",     "OdoPub.inputs:timeStamp"),
        ("Odo.outputs:position",               "OdoPub.inputs:position"),
        ("Odo.outputs:orientation",            "OdoPub.inputs:orientation"),
        ("Odo.outputs:linearVelocity",         "OdoPub.inputs:linearVelocity"),
        ("Odo.outputs:angularVelocity",        "OdoPub.inputs:angularVelocity"),
        ("OnTick.outputs:tick",                "TF.inputs:execIn"),
        ("Ctx.outputs:context",                "TF.inputs:context"),
        ("SimTime.outputs:simulationTime",     "TF.inputs:timeStamp"),
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
log(f"OG {GRAPH} fresh 생성 완료 → /cam/front/rgb, /cam/rear/rgb (domain {DOMAIN})")
if _TELEM:
    log(f"OG 텔레메트리 발행: {LEG_TOPIC}, {ODOM_TOPIC}, /tf "
        f"(RELIABLE) — gps/state 는 telemetry_bridge_node 가 odom 에서 파생")
if _CMD:
    log(f"다운링크 ON: ROS2SubscribeTwist ← {CMD_TOPIC} (RELIABLE)")

# 4) 시뮬 구동 ---------------------------------------------------------------
# physics_dt=1/200 → walk-these-ways-go2 학습 sim dt=0.005 와 일치.
# (구 Spot 은 1/500 요구였으나 Go2 RL 은 0.005 학습본 → decimation=4 로
#  control 50Hz. actuator_net 도 이 substep(200Hz)에서 평가되어야 충실.)
# rendering_dt=1/50 → 카메라 50Hz (OG CameraHelper 기준).
import numpy as _np

world = World(stage_units_in_meters=1.0, physics_dt=1/200, rendering_dt=1/50)
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

# ── DMZ Sentry M6: 검사 카메라 명령 — /tmp 파일 mailbox 폴링 ────────────
# Isaac 5.1 OG 에 ROS2SubscribeString 미등록 → 사이드카 inspect_relay.py
# (rclpy) 가 /robot/inspect/command 구독해 /tmp/cobot3_inspect_cmd.json 에
# 덮어쓰기. 본 process 는 mtime 변화 감지로 명령 수신.
_INSPECT_CMD_FILE = "/tmp/cobot3_inspect_cmd.json"
_inspect_state = {
    "rx": 0, "last_log": 0.0, "last_mtime": 0.0,
    "pan": 0.0, "tilt": 0.0, "focal": 18.0,
}

# ── Go2WtwController (walk-these-ways RL 보행 정책, in-process) ───────────
# GP_SPOT_CONTROL 환경변수명은 run 스크립트·dev-docs 호환 위해 유지(보행
# 컨트롤러 on/off 토글 의미).
_ctrl = None
if _SPOT_CTRL:
    try:
        from go2_controller import Go2WtwController
        _ctrl = Go2WtwController(SPOT_PRIM)
        world.add_physics_callback("go2_ctrl", _ctrl.on_physics_step)
        log("Go2WtwController 등록 — physics_callback 활성")
        # play 시 자동으로 Cone 으로 자율 주행 (nav P-제어 → walk-these-ways).
        # teleop(/robot/cmd_vel) 수신 시 _command() 가 우선(teleop>nav>idle).
        if _cone_xy is not None and os.environ.get("GP_GO2_NAV", "1") == "1":
            _ctrl.set_nav_goal(_cone_xy[0], _cone_xy[1])
            log(f"nav_goal=Cone {tuple(round(v,2) for v in _cone_xy)} "
                f"설정 — play 시 자율 보행 시작")
    except Exception as e:
        log(f"Go2WtwController 초기화 실패 {e!r} — 보행 제어 비활성")
else:
    log("GP_SPOT_CONTROL=0 → Go2WtwController 비활성(관측 전용)")


def _apply_cmd():
    """OG SubCmd 출력을 읽어 Go2WtwController 에 전달(비차단).
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
            f"{GRAPH}/RPFront.outputs:renderProductPath").get()
        cp = og.Controller.attribute(
            f"{GRAPH}/RPFront.inputs:cameraPrim").get()
        log(f"DIAG front cameraPrim={cp} renderProduct={rp!r}")
        if not rp:
            log("  ⚠ front renderProductPath 비어있음 → 카메라 프레임 생성 안 됨")
    except Exception as e:
        log(f"DIAG 실패: {e!r}")


def _apply_inspect_cmd():
    """/tmp/cobot3_inspect_cmd.json 의 명령을 읽어 검사 카메라 Xform/focal 갱신.

    inspect_relay.py (rclpy 사이드카) 가 /robot/inspect/command 를 받아
    이 파일에 dump 한다. mtime 변화 시에만 처리.

    payload JSON 키:
    - pan, tilt: delta(rad) 또는 절대(rad) — "absolute":true 면 절대.
    - zoom: focalLength 곱 (1.0=중립, <1=zoom out, >1=zoom in).
    - focal_length: focalLength 직접(mm).
    - look_at: [x,y,z] world 좌표 — yaw/pitch 자동 계산.
    - reset: true → pan/tilt/focal 초기화.
    """
    try:
        m = os.path.getmtime(_INSPECT_CMD_FILE)
    except OSError:
        return
    if m <= _inspect_state["last_mtime"]:
        return
    _inspect_state["last_mtime"] = m
    _inspect_state["rx"] += 1
    import json as _json
    try:
        with open(_INSPECT_CMD_FILE) as _f:
            cmd = _json.load(_f)
    except Exception as _e:
        log(f"[inspect] JSON 파싱 실패: {_e!r}")
        return

    if cmd.get("reset"):
        _inspect_state["pan"] = 0.0
        _inspect_state["tilt"] = 0.0
        _inspect_state["focal"] = 18.0
    else:
        absolute = bool(cmd.get("absolute", True))
        if "pan" in cmd:
            v = float(cmd["pan"])
            _inspect_state["pan"] = v if absolute else _inspect_state["pan"] + v
        if "tilt" in cmd:
            v = float(cmd["tilt"])
            _inspect_state["tilt"] = (
                v if absolute else _inspect_state["tilt"] + v)
        if "focal_length" in cmd:
            _inspect_state["focal"] = float(cmd["focal_length"])
        elif "zoom" in cmd:
            _inspect_state["focal"] = float(
                max(8.0, min(90.0, _inspect_state["focal"] * float(cmd["zoom"]))))
        # look_at: base 좌표계 기준이 아닌 world 좌표 — robot pose 결합 없이는
        # 정확하지 않음. 1차 구현: world XY 만 사용해 robot 현재 pose 기준 yaw.
        if "look_at" in cmd and isinstance(cmd["look_at"], (list, tuple)):
            try:
                tx, ty = float(cmd["look_at"][0]), float(cmd["look_at"][1])
                _g = stage.GetPrimAtPath(BASE_PRIM)
                if _g and _g.IsValid():
                    _gt = UsdGeom.Xformable(_g).ComputeLocalToWorldTransform(
                        Usd.TimeCode.Default()).ExtractTranslation()
                    import math as _math
                    _inspect_state["pan"] = _math.atan2(
                        ty - float(_gt[1]), tx - float(_gt[0]))
                    _inspect_state["tilt"] = 0.0
            except Exception:
                pass

    # Xform / focalLength 갱신
    try:
        _cam_prim = stage.GetPrimAtPath(CAM_INSPECT_PATH)
        if _cam_prim and _cam_prim.IsValid():
            import math as _math
            # base 정면(+X, up +Z) 쿼터니언 _Q_FRONT 에 pan(Z축) · tilt(Y축) 합성
            cy = _math.cos(_inspect_state["pan"] * 0.5)
            sy = _math.sin(_inspect_state["pan"] * 0.5)
            cp = _math.cos(_inspect_state["tilt"] * 0.5)
            sp = _math.sin(_inspect_state["tilt"] * 0.5)
            # base 좌표 기준: pan = yaw about world Z (≈ camera 그대로 회전),
            # tilt = pitch about camera's right axis. 1차 구현: 단순 yaw·pitch
            # 의 Z·Y 합성 쿼터니언으로 (정밀 짐벌 짐벌락 분석은 추후).
            q_yaw = Gf.Quatf(float(cy), Gf.Vec3f(0.0, 0.0, float(sy)))
            q_pitch = Gf.Quatf(float(cp), Gf.Vec3f(0.0, float(sp), 0.0))
            q_total = _Q_FRONT * q_yaw * q_pitch
            _xf = UsdGeom.Xformable(_cam_prim)
            _ops = _xf.GetOrderedXformOps()
            for _op in _ops:
                if _op.GetOpType() == UsdGeom.XformOp.TypeOrient:
                    _op.Set(q_total)
                    break
            UsdGeom.Camera(_cam_prim).GetFocalLengthAttr().Set(
                float(_inspect_state["focal"]))
    except Exception as _e:
        log(f"[inspect] Xform 갱신 실패: {_e!r}")

    now = time.time()
    if now - _inspect_state["last_log"] > 1.0:
        _inspect_state["last_log"] = now
        log(f"[inspect] pan={_inspect_state['pan']:.2f} "
            f"tilt={_inspect_state['tilt']:.2f} "
            f"focal={_inspect_state['focal']:.1f} (rx={_inspect_state['rx']})")


n = 0
try:
    while simulation_app.is_running():
        world.step(render=True)
        n += 1
        _apply_cmd()
        _apply_inspect_cmd()
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
