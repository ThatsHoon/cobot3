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
# 2026-05-21: 9개 신규 prim (Watchtowers/Fence/Doro/spike_ball/banana_obstacle/
# Landmine/Go2_starting_point/militarybase/radar_tower) 의 collider/material
# binding/dynamic 설정을 별도 USDA sublayer 로 분리. gp_scene.usd 무수정 원칙
# 유지. 자세한 항목은 dev-docs/scene-overrides.md 참고. GP_USE_OVERRIDES=0
# 으로 끄면 sublayer 미로드, 기존 safety-net 만 동작 (fallback).
_OVERRIDES_USD = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "scene", "overrides", "gp_scene_overrides.usda")
_USE_OVERRIDES = os.environ.get("GP_USE_OVERRIDES", "1") == "1"
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

# 1b) sublayer 보강 — gp_scene.usd 무수정 원칙 유지 (단일 소스).
# WHY: collider/material binding/mass 등 보강만 별도 USDA 에 모음. 강한 opinion
# 으로 prepend → 기존 gp_scene.usd 의 누락된 attribute 가 sublayer 값으로 채워짐.
# 미존재 시 fallback safety-net 이 같은 일을 runtime 에 수행 (단, silent fail
# 위험이 있어 sublayer 권장).
if _USE_OVERRIDES and os.path.isfile(_OVERRIDES_USD):
    _rl = stage.GetRootLayer()
    _rl_dir = os.path.dirname(_rl.realPath) if _rl.realPath else os.path.dirname(SCENE)
    _rel = os.path.relpath(_OVERRIDES_USD, _rl_dir)
    if _rel not in list(_rl.subLayerPaths):
        _rl.subLayerPaths.insert(0, _rel)
        log(f"sublayer prepended: {_rel}")
    else:
        log(f"sublayer already present: {_rel}")
else:
    log(f"sublayer skipped (USE={_USE_OVERRIDES}, "
        f"exists={os.path.isfile(_OVERRIDES_USD)}) — fallback safety-net 동작")

# 2) 로봇 참조 교체(spot_with_arm → go2) + 앞뒤 카메라 생성 -------------------
# NVIDIA go2.usd 는 walk-these-ways 학습 컨벤션과 달라 보행 전이 실패(검증):
# 기립 OK 이나 전진 보행 불가. → 정책이 실제 학습한 Unitree go2.urdf 를
# import_go2_unitree.py 로 USD 변환한 로컬 자산을 사용(학습 컨벤션 일치).
# defaultPrim=/go2_description, artroot=/go2_description/base → ref 시
# /World/Go2/base 로 컴포즈(ART_PRIM 와 일치).
_GO2_USD = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "scene", "go2_unitree", "go2_unitree.usd")
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

# Go2 정찰 사양 (2026-05-20): 명시 spawn (212.8, 890.53, 5.0), 수색지(620.36,
# 499.72, 52.138). 환경변수 GP_GO2_SPAWN_USE_TERRAIN=1 면 terrain nearest
# vertex 보정(낙하 방지), 기본 0=명시 좌표 그대로 (씬 terrain 없거나 명시
# z 가 신뢰 가능할 때).
# 2026-05-21: GP_GO2_SPAWN_X/Y/Z env 추가 — world_odom_tf_pub.py 의 동일
# env 와 일치시켜 spawn 좌표 단일 진실의 원천 (SSOT) 보장.
_GO2_HOME_XYZ = (
    float(os.environ.get("GP_GO2_SPAWN_X", "212.8")),
    float(os.environ.get("GP_GO2_SPAWN_Y", "890.53")),
    float(os.environ.get("GP_GO2_SPAWN_Z", "5.0")),
)
_GO2_GOAL_XYZ = (287.59, 1129.728, 29.53)
_USE_TERRAIN = os.environ.get("GP_GO2_SPAWN_USE_TERRAIN", "0") == "1"

_spawn = Gf.Vec3d(*_GO2_HOME_XYZ)
_cone_xy = (_GO2_GOAL_XYZ[0], _GO2_GOAL_XYZ[1])
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


if _USE_TERRAIN and _tm and _tm.IsValid():
    try:
        _gx, _gy, _gz = _terrain_nearest_vertex(_tm, _GO2_HOME_XYZ[0],
                                                _GO2_HOME_XYZ[1])
        _spawn = Gf.Vec3d(_gx, _gy, _gz + _CLEAR)
        log(f"spawn terrain nearest: ({_gx:.1f},{_gy:.1f},z={_gz:.2f}) → "
            f"{tuple(round(float(v),2) for v in _spawn)}")
    except Exception as _e:
        log(f"⚠ terrain nearest 실패 ({_e!r}) → 명시 좌표 사용 {_GO2_HOME_XYZ}")
else:
    log(f"spawn 명시 좌표: {tuple(round(float(v),2) for v in _spawn)} "
        f"(GP_GO2_SPAWN_USE_TERRAIN={int(_USE_TERRAIN)})")
log(f"nav_goal=수색지 {_cone_xy} (z={_GO2_GOAL_XYZ[2]:.2f})")

# 씬 랜드마크 dump → landmarks_pub.py 가 읽어 /scene/landmarks (latched) 발행.
# patrol controller(C2) 가 sortie 시 waypoint 구성에 사용.
import json as _json
try:
    _lm = {
        "home": {"x": float(_spawn[0]), "y": float(_spawn[1]),
                 "z": float(_spawn[2])},
        "goal": {"x": float(_cone_xy[0]), "y": float(_cone_xy[1]),
                 "z": float(_GO2_GOAL_XYZ[2])},
        "arrive_box": 10.0,
    }
    with open("/tmp/cobot3_landmarks.json", "w") as _f:
        _json.dump(_lm, _f)
    log(f"landmarks dump → /tmp/cobot3_landmarks.json "
        f"home={_lm['home']} goal={_lm['goal']} arrive=±{_lm['arrive_box']}m")
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

# ── 접지 collider+마찰 안전망 (씬에 이미 있으면 스킵) ─────────────────
# 원칙: 마찰은 gp_scene.usd 에 GUI 로 저작·저장된 것이 단일 소스.
# 단, 씬 GUI 저장 과정에서 Terrain 메시의 CollisionAPI 가 누락되거나
# (실측 2026-05-21: Go2 가 지형을 통과해 z<0 으로 추락), physics material
# 바인딩만 빠진 경우 무마찰→전복을 막기 위한 안전망 발동.
# - PRE-FIX: Terrain 하위 Mesh 중 CollisionAPI 가 없으면
#   CollisionAPI + MeshCollisionAPI(approximation="none" trimesh) 적용
# - POST-FIX: physics material(0.8) 정의 + Terrain·Go2 collider 에 바인딩
try:
    from pxr import UsdShade as _UsdShade, UsdPhysics as _UP

    # 0) Terrain 하위 Mesh 진단 + CollisionAPI 누락 시 추가 적용
    _terr_root = stage.GetPrimAtPath("/World/Terrain")
    _mesh_total = _mesh_with_col = _added_col = 0
    if _terr_root and _terr_root.IsValid():
        from pxr import Usd as _UsdT
        for _m in _UsdT.PrimRange(_terr_root):
            if _m.GetTypeName() != "Mesh":
                continue
            _mesh_total += 1
            if _m.HasAPI(_UP.CollisionAPI):
                _mesh_with_col += 1
                continue
            try:
                _UP.CollisionAPI.Apply(_m)
                _UP.MeshCollisionAPI.Apply(_m)
                _mca = _UP.MeshCollisionAPI(_m)
                # static 지형이므로 trimesh("none") 안전 (Go2 는 dynamic
                # 이지만 base/legs collider 는 robot prim 쪽에서 처리).
                _mca.CreateApproximationAttr("none")
                _added_col += 1
            except Exception as _ce:
                log(f"⚠ Terrain CollisionAPI apply fail {_m.GetPath()}: {_ce!r}")
        log(f"Terrain mesh diag: total={_mesh_total} "
            f"pre_collider={_mesh_with_col} added_collider={_added_col}")

    # 1) 이미 binding 있나? (collider 가 모두 새로 추가됐다면 binding 0 → fix 진행)
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
    if _scene_has_fric and _added_col == 0:
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
        log(f"접지 마찰 안전망 적용 — collider {_nb}개 0.8 바인딩 "
            f"(터레인 신규 collider={_added_col})")

    # 2026-05-21: 사용자 수동 추가 prim 들의 leaf Mesh CollisionAPI + Terrain
    # material binding 보강. 정적/동적 분기 — 동적 rigidBody (spike_ball/banana/
    # Landmine) 는 PhysX 요구사항으로 approximation='convexHull' (trimesh-none
    # 은 dynamic 비허용). 정적 props (Watchtowers/Fence/Doro) 는 'none' (trimesh).
    # 시각 마커 (Go2_starting_point/militarybase/radar_tower) 는 sublayer 에서
    # collisionEnabled=false → safety-net 도 collider 생성 안 함.
    #
    # sublayer (gp_scene_overrides.usda) 가 있으면 root 레벨 rigidBody/mass/
    # collisionEnabled 는 그쪽이 처리. 여기서는 leaf Mesh CollisionAPI 와
    # binding 만 담당 (sublayer 는 leaf 경로 미리 열거 불가).
    _DYN_PRIMS = ["/World/spike_ball", "/World/banana_obstacle", "/World/Landmine"]
    _STATIC_PRIMS = ["/World/Watchtowers", "/World/Doro", "/World/Fence"]
    _MARKER_PRIMS = ["/World/Go2_starting_point", "/World/militarybase",
                     "/World/radar_tower"]  # collider 생성 안 함
    _EXTRA_PRIMS = _DYN_PRIMS + _STATIC_PRIMS  # marker 제외
    # Terrain 의 physics_material path 자동 발견 (저장된 단일 소스)
    _TERR_PM = None
    for _t in stage.Traverse():
        if _t.HasAPI(_UP.MaterialAPI) and "/World/Terrain" in str(_t.GetPath()):
            _TERR_PM = _t
            break
    if _TERR_PM is None:
        log("⚠ 추가 prim 마찰: Terrain physics_material 미발견 → 스킵")
    else:
        from pxr import Usd as _Us2
        _pm_mat_ext = _UsdShade.Material(_TERR_PM)
        _ex_col = _ex_bind = 0
        for _root_path in _EXTRA_PRIMS:
            _root = stage.GetPrimAtPath(_root_path)
            if not (_root and _root.IsValid()):
                continue
            _is_dyn = _root_path in _DYN_PRIMS
            _approx = "convexHull" if _is_dyn else "none"
            for _p in _Us2.PrimRange(_root):
                if _p.GetTypeName() != "Mesh":
                    continue
                # CollisionAPI 없으면 추가 (동적=convexHull, 정적=trimesh-none)
                if not _p.HasAPI(_UP.CollisionAPI):
                    _UP.CollisionAPI.Apply(_p)
                    _UP.MeshCollisionAPI.Apply(_p)
                    _UP.MeshCollisionAPI(_p).CreateApproximationAttr(_approx)
                    _ex_col += 1
                # binding 비어있으면 Terrain material 로
                _br = _p.GetRelationship("material:binding:physics")
                if _br and _br.GetTargets():
                    continue
                _UsdShade.MaterialBindingAPI.Apply(_p)
                _UsdShade.MaterialBindingAPI(_p).Bind(
                    _pm_mat_ext,
                    bindingStrength=_UsdShade.Tokens.weakerThanDescendants,
                    materialPurpose="physics")
                _ex_bind += 1
        log(f"추가 prim {len(_EXTRA_PRIMS)}개 마찰 적용 — "
            f"신규 collider={_ex_col}, 신규 binding={_ex_bind} "
            f"(target material={_TERR_PM.GetPath()})")
except Exception as _e:
    log(f"⚠ 마찰 안전망 처리 실패: {_e!r}")

# ── Go2 physics material + 질량 안전망 (2026-05-21) ──────────────────
# 발견(MCP 진단): import_go2_unitree.py 가 ref 한 go2.usd 는 collider 가
# instanceable prim(/Go2/<link>/collisions → /__Prototype_N) 안에
# Cube/Cylinder/Sphere(Gprim) 형태로 모두 정의돼 있다. CollisionAPI 도
# prototype 쪽에 적용됨 → 우리가 직접 mesh 순회로 적용할 필요 없음.
# 단 physics material 바인딩이 모두 누락 → PhysX default(~0.5) 사용 →
# Terrain 0.8 과 combine 시 effective ≈ 0.65 → 학습 분포(0.8 가정)보다
# 낮음 → "정지 시 미끄러짐" 의 직접 원인. ROBOT_PRIM 루트에 단일 binding
# 을 weakerThanDescendants 로 두면 USD inheritance 가 모든 collider
# (instance prototype 포함) 까지 적용됨 — 1줄로 끝.
#
# 추가 mass: import 직후 base mass 가 6.92 kg 으로 들어오는 케이스 관측
# (Go2 실측 ~12 kg → 58% → OOD). 차이 0.5 kg 이상이면 12.0 으로 보정.
try:
    from pxr import UsdShade as _US2, UsdPhysics as _UP2
    _g2 = stage.GetPrimAtPath(ROBOT_PRIM)
    if _g2 and _g2.IsValid():
        # 1) PhysicsMaterial 정의 (없으면 신규)
        _GO2_PM = "/World/Physics_Materials/go2_material"
        _gpmp = stage.GetPrimAtPath(_GO2_PM)
        if not (_gpmp and _gpmp.IsValid()):
            _US2.Material.Define(stage, _GO2_PM)
            _gpmp = stage.GetPrimAtPath(_GO2_PM)
        if not _gpmp.HasAPI(_UP2.MaterialAPI):
            _UP2.MaterialAPI.Apply(_gpmp)
        _gmapi = _UP2.MaterialAPI(_gpmp)
        for _attr, _v in (("CreateStaticFrictionAttr", 0.8),
                          ("CreateDynamicFrictionAttr", 0.8),
                          ("CreateRestitutionAttr", 0.0)):
            getattr(_gmapi, _attr)(_v)
        _go2_mat = _US2.Material(_gpmp)

        # 2) ROBOT_PRIM 루트 1회 binding — inheritance 로 자식 collider 전체 적용
        _US2.MaterialBindingAPI.Apply(_g2)
        _US2.MaterialBindingAPI(_g2).Bind(
            _go2_mat,
            bindingStrength=_US2.Tokens.weakerThanDescendants,
            materialPurpose="physics")
        log(f"Go2 physics material 루트 binding (mu=0.8, inheritance)")

        # 3) Base link mass 보정 — Unitree Go2 실측 ~12 kg
        _base = stage.GetPrimAtPath(f"{ROBOT_PRIM}/base")
        if _base and _base.IsValid():
            if not _base.HasAPI(_UP2.MassAPI):
                _UP2.MassAPI.Apply(_base)
            _mass_api = _UP2.MassAPI(_base)
            _mass_attr = _mass_api.GetMassAttr() or _mass_api.CreateMassAttr()
            _old_mass = _mass_attr.Get()
            _GO2_MASS_TARGET = float(os.environ.get("GP_GO2_MASS", "12.0"))
            if _old_mass is None or abs(float(_old_mass) - _GO2_MASS_TARGET) > 0.5:
                _mass_attr.Set(_GO2_MASS_TARGET)
                log(f"Go2 base mass {float(_old_mass or 0):.2f} → "
                    f"{_GO2_MASS_TARGET:.2f} kg")
            else:
                log(f"Go2 base mass 이미 적정({float(_old_mass):.2f} kg) → 스킵")
except Exception as _e:
    log(f"⚠ Go2 material/mass 안전망 실패: {_e!r}")

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


# 사용자 요청 (2026-05-20): front 카메라 삭제, inspect 는 base 전방 끝, rear 는
# 후방 끝 으로 이동. Go2 base half-length ≈ 0.235m.
_mk_cam(CAM_REAR_PATH, Gf.Vec3f(-0.235, 0.0, 0.10), _Q_REAR, "후방(real) 카메라")

# 검사 카메라(가상 짐벌) — base 전방 끝 mount. pan/tilt/zoom 은
# /robot/inspect/command 수신 시 _apply_inspect_cmd 가 Xform·focalLength 갱신.
CAM_INSPECT_PATH = "/World/Go2/base/camera_inspect"
_mk_cam(CAM_INSPECT_PATH, Gf.Vec3f(0.235, 0.0, 0.10), _Q_FRONT, "검사 카메라(짐벌, 전방 끄트머리)")

# 오버헤드(TACTICAL MAP 배경용) 카메라 — /World 직접 자식, 매 step Go2 base
# xy 동기화 + z 고정 + orient identity (시선 −Z, up +Y) = North-up 고정.
# WHY: base 자식이면 보행 oscillation (roll/pitch + z bob) 가 영상에 누설.
# /World 자식 + 매 step xy 추적이면 robot 따라가지만 화면 위는 항상 world +Y.
CAM_OVERHEAD_PATH = "/World/Overhead_Camera"
_Q_DOWN = Gf.Quatf(1.0, Gf.Vec3f(0.0, 0.0, 0.0))   # identity
if stage.GetPrimAtPath(CAM_OVERHEAD_PATH).IsValid():
    stage.RemovePrim(CAM_OVERHEAD_PATH)
_cam_ov = UsdGeom.Camera.Define(stage, CAM_OVERHEAD_PATH)
_xf_ov = UsdGeom.Xformable(_cam_ov.GetPrim())
_xf_ov.ClearXformOpOrder()
# 초기 spawn 위치 위에 두기 (Go2 spawn x=212.8, y=890.53, z=5.0 + 100)
_xf_ov.AddTranslateOp().Set(Gf.Vec3f(212.8, 890.53, 105.0))
_xf_ov.AddOrientOp().Set(_Q_DOWN)
_cam_ov.GetFocalLengthAttr().Set(8.0)
_cam_ov.GetHorizontalApertureAttr().Set(_HAP)
_cam_ov.GetVerticalApertureAttr().Set(_VAP)
_cam_ov.GetClippingRangeAttr().Set(Gf.Vec2f(1.0, 1000.0))
log(f"오버헤드 카메라(고도 100m, North-up 고정) 생성: {CAM_OVERHEAD_PATH}")

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
# 사용자 요청 (2026-05-20): RPFront/CamFront 제거 — front 카메라 미사용.
# 신규: RPOverhead/CamOverhead — TACTICAL MAP 배경용 (고도 100m, 지면).
_CN = [
    ("OnTick",   "omni.graph.action.OnPlaybackTick"),
    ("Ctx",      "isaacsim.ros2.bridge.ROS2Context"),
    ("RPRear",   "isaacsim.core.nodes.IsaacCreateRenderProduct"),
    ("CamRear",  "isaacsim.ros2.bridge.ROS2CameraHelper"),
    ("RPInspect",  "isaacsim.core.nodes.IsaacCreateRenderProduct"),
    ("CamInspect", "isaacsim.ros2.bridge.ROS2CameraHelper"),
    ("RPOverhead",  "isaacsim.core.nodes.IsaacCreateRenderProduct"),
    ("CamOverhead", "isaacsim.ros2.bridge.ROS2CameraHelper"),
]
_SV = [
    ("Ctx.inputs:domain_id",        DOMAIN),
    ("RPRear.inputs:cameraPrim",    CAM_REAR_PATH),
    ("RPRear.inputs:width",         640),
    ("RPRear.inputs:height",        360),
    ("CamRear.inputs:topicName",    "/cam/rear/rgb"),
    ("CamRear.inputs:frameId",      "camera_rear"),
    ("CamRear.inputs:type",         "rgb"),
    ("CamRear.inputs:qosProfile",   _SENSOR_QOS),
    ("RPInspect.inputs:cameraPrim",  CAM_INSPECT_PATH),
    ("RPInspect.inputs:width",       640),
    ("RPInspect.inputs:height",      360),
    ("CamInspect.inputs:topicName",  "/cam/inspect/rgb"),
    ("CamInspect.inputs:frameId",    "camera_inspect"),
    ("CamInspect.inputs:type",       "rgb"),
    ("CamInspect.inputs:qosProfile", _SENSOR_QOS),
    ("RPOverhead.inputs:cameraPrim",  CAM_OVERHEAD_PATH),
    ("RPOverhead.inputs:width",       640),
    ("RPOverhead.inputs:height",      640),       # 정방형 (지도용)
    ("CamOverhead.inputs:topicName",  "/cam/overhead/rgb"),
    ("CamOverhead.inputs:frameId",    "camera_overhead"),
    ("CamOverhead.inputs:type",       "rgb"),
    ("CamOverhead.inputs:qosProfile", _SENSOR_QOS),
]
_CC = [
    ("OnTick.outputs:tick",              "RPRear.inputs:execIn"),
    ("RPRear.outputs:execOut",           "CamRear.inputs:execIn"),
    ("RPRear.outputs:renderProductPath", "CamRear.inputs:renderProductPath"),
    ("Ctx.outputs:context",              "CamRear.inputs:context"),
    ("OnTick.outputs:tick",                  "RPOverhead.inputs:execIn"),
    ("RPOverhead.outputs:execOut",           "CamOverhead.inputs:execIn"),
    ("RPOverhead.outputs:renderProductPath", "CamOverhead.inputs:renderProductPath"),
    ("Ctx.outputs:context",                  "CamOverhead.inputs:context"),
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
        # 2026-05-21: /clock publisher 추가 — Nav2 의 use_sim_time=true 가
        # 정상 동작하려면 Isaac sim time 이 ROS clock 으로 발행돼야 함.
        # 미발행 시 nav2 TF buffer 가 stamp 매칭 실패 → "Could not find a
        # connection between world and Go2" 무한 에러 + sortie 무동작.
        ("Clock",   "isaacsim.ros2.bridge.ROS2PublishClock"),
    ]
    _SV += [
        ("LegJS.inputs:targetPrim",        LEG_PRIM),
        ("LegJS.inputs:topicName",         LEG_TOPIC),
        ("LegJS.inputs:qosProfile",        _REL_QOS),
        ("Odo.inputs:chassisPrim",         BASE_PRIM),
        ("OdoPub.inputs:topicName",        ODOM_TOPIC),
        ("OdoPub.inputs:odomFrameId",      "odom"),
        ("Clock.inputs:topicName",         "/clock"),
        ("Clock.inputs:qosProfile",        _REL_QOS),
        # 발행 주기는 OnPlaybackTick 펄스 = render_dt 1/50 → 50Hz. ROS2PublishClock
        # 은 자체 publishRate input 미보유 (2026-05-21 라이브 검증: 추가 시
        # "Attribute named 'inputs:publishRate' does not refer to a legal og.Attribute"
        # OmniGraphError → kit 종료). Nav2 controller_frequency 10Hz 의 5×.
        # OG ROS2PublishTransformTree 가 발행하는 base link frame_id 는 USD
        # prim 이름인 "Go2" — OdoPub 도 동일 이름 써야 TF tree 가 끊기지 않음.
        # (이전 "base_link" 는 OG TF 와 다른 frame 으로 분리되어 Nav2 가
        # robot base 위치 못 찾는 원인이었음 — 2026-05-20 라이브 검증).
        ("OdoPub.inputs:chassisFrameId",   "Go2"),
        ("OdoPub.inputs:qosProfile",       _REL_QOS),
        # 2026-05-21 fix: ROBOT_PRIM(/World/Go2) USD Xform 은 spawn 정적 위치.
        # 보행 중 동적 변위는 articulation 의 base link 가 가짐. TF 가 spawn
        # 위치만 발행 → Nav2 가 robot 안 움직인다고 판단 → yaw 정렬 무한 회전
        # (사용자 보고). BASE_PRIM(/World/Go2/base) = articulation root → 동적
        # world pose 반영.
        ("TF.inputs:targetPrims",          [BASE_PRIM]),
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
        # /clock publisher 연결 (2026-05-21)
        ("OnTick.outputs:tick",                "Clock.inputs:execIn"),
        ("Ctx.outputs:context",                "Clock.inputs:context"),
        ("SimTime.outputs:simulationTime",     "Clock.inputs:timeStamp"),
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
log(f"OG {GRAPH} fresh 생성 완료 → /cam/rear/rgb, /cam/inspect/rgb, /cam/overhead/rgb (domain {DOMAIN})")
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
        from isaacsim.core.prims import SingleArticulation as _SA
        # GPU PhysX 모드에서 physics callback 내 initialize()는 GPU
        # PhysicsSimulationView를 생성하지 못해 ~1000 step 후
        # get_joint_positions() → 0-dim array → IndexError 폭주.
        # world.reset() 직후 메인 스레드에서 미리 초기화해 주입
        # (go2_nav_inject.py 와 동일 패턴 — dof 수로 성공 여부 검증).
        _pre_art = _SA(prim_path=ART_PRIM)
        _pre_art.initialize()
        _pre_dof = list(_pre_art.dof_names) if _pre_art.dof_names else []
        _ctrl = Go2WtwController(SPOT_PRIM)
        if len(_pre_dof) >= 12:
            _ctrl._art = _pre_art
            log(f"SingleArticulation 메인스레드 사전 초기화 OK "
                f"(dof={len(_pre_dof)}): {ART_PRIM}")
        else:
            log(f"SingleArticulation 사전 초기화 dof={len(_pre_dof)} (<12) "
                f"— 콜백 폴백 (GPU physics 지연 시 경고 가능)")
        world.add_physics_callback("go2_ctrl", _ctrl.on_physics_step)
        log("Go2WtwController 등록 — physics_callback 활성")
        # 외부 Nav2 사용 시 내부 P-제어 비활성 (GP_GO2_NAV=0). 충돌 방지
        # — 외부 Nav2 가 mode 변경마다 새 goal 전송, 내부 P-제어가 고정 goal
        # 추적하면 명령 무시 증상 (2026-05-20 fix).
        if _cone_xy is not None and os.environ.get("GP_GO2_NAV", "1") != "0":
            _ctrl.set_nav_goal(_cone_xy[0], _cone_xy[1])
            log(f"nav_goal=수색지 {tuple(round(v,2) for v in _cone_xy)} "
                f"설정 — play 시 자율 보행 시작 (내부 P-제어)")
        else:
            log("GP_GO2_NAV=0 → 내부 P-제어 set_nav_goal 호출 스킵 "
                "(외부 Nav2 cmd_vel 만 사용)")
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
        for cam in ("RPRear", "RPInspect", "RPOverhead"):
            rp = og.Controller.attribute(
                f"{GRAPH}/{cam}.outputs:renderProductPath").get()
            cp = og.Controller.attribute(
                f"{GRAPH}/{cam}.inputs:cameraPrim").get()
            log(f"DIAG {cam} cameraPrim={cp} renderProduct={rp!r}")
            if not rp:
                log(f"  ⚠ {cam} renderProductPath 비어있음")
    except Exception as e:
        log(f"DIAG 실패: {e!r}")


_INSPECT_LIM = 70.0   # 사용자 사양 (2026-05-20): pan/tilt ±70°


def _update_overhead_xform():
    """매 step 호출 — overhead 카메라 (/World 자식) 의 translate 를 Go2 base
    xy 로 동기화. z 는 base.z + 100m. orient identity 유지 (North-up).
    """
    try:
        _base = stage.GetPrimAtPath(BASE_PRIM)
        if not (_base and _base.IsValid()):
            return
        _bt = UsdGeom.Xformable(_base).ComputeLocalToWorldTransform(
            _U.TimeCode.Default()).ExtractTranslation()
        _cam = stage.GetPrimAtPath(CAM_OVERHEAD_PATH)
        if not (_cam and _cam.IsValid()):
            return
        _xf = UsdGeom.Xformable(_cam)
        for _op in _xf.GetOrderedXformOps():
            if _op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                _op.Set(Gf.Vec3f(float(_bt[0]), float(_bt[1]),
                                 float(_bt[2]) + 100.0))
                break
    except Exception as _e:
        log(f"[overhead] xform 갱신 실패: {_e!r}")


def _update_inspect_xform():
    """매 step 호출 — base body roll/pitch 격리 (짐벌 stabilization) +
    사용자 pan/tilt 적용 + focalLength 갱신.

    WHY: base 자식이라 robot 보행 중 base roll/pitch 가 카메라에 누설되어
    영상이 기울어짐. base.world.inverse 로 cancel.
    """
    try:
        _cam_prim = stage.GetPrimAtPath(CAM_INSPECT_PATH)
        if not (_cam_prim and _cam_prim.IsValid()):
            return
        import math as _math
        _LIM = _math.radians(_INSPECT_LIM)
        _inspect_state["pan"] = max(-_LIM, min(_LIM, _inspect_state["pan"]))
        _inspect_state["tilt"] = max(-_LIM, min(_LIM, _inspect_state["tilt"]))
        # base world rotation → roll(X)/pitch(Y) 추출 (ZYX intrinsic)
        _base = stage.GetPrimAtPath(BASE_PRIM)
        _roll_w = _pitch_w = 0.0
        if _base and _base.IsValid():
            _bt = UsdGeom.Xformable(_base).ComputeLocalToWorldTransform(
                _U.TimeCode.Default())
            _r20 = float(_bt[2][0]); _r21 = float(_bt[2][1]); _r22 = float(_bt[2][2])
            _pitch_w = _math.atan2(-_r20, _math.sqrt(_r21*_r21 + _r22*_r22))
            _roll_w = _math.atan2(_r21, _r22)

        def _qx(a):
            return Gf.Quatf(float(_math.cos(a*0.5)),
                            Gf.Vec3f(float(_math.sin(a*0.5)), 0.0, 0.0))
        def _qy(a):
            return Gf.Quatf(float(_math.cos(a*0.5)),
                            Gf.Vec3f(0.0, float(_math.sin(a*0.5)), 0.0))
        def _qz(a):
            return Gf.Quatf(float(_math.cos(a*0.5)),
                            Gf.Vec3f(0.0, 0.0, float(_math.sin(a*0.5))))
        # base frame 에서 pan = yaw(Z) · tilt = pitch(Y). carmera local axes 가
        # 아니라 base axes 기준으로 회전해야 "고개 좌우/상하" 가 됨 (사용자
        # 요청 2026-05-20: 좌우 이동이 시선축 roll 이 아닌 yaw 회전).
        # _Q_FRONT 가 base→camera-local 매핑이므로, q_user 를 _Q_FRONT 의 왼쪽에
        # 곱해 base frame 에 적용.
        q_user_base = _qz(_inspect_state["pan"]) * _qy(_inspect_state["tilt"])
        # base 자식 → local = inverse(base roll/pitch) * (q_user_base * Q_FRONT)
        q_stab = _qy(-_pitch_w) * _qx(-_roll_w)
        q_total = q_stab * q_user_base * _Q_FRONT
        _xf = UsdGeom.Xformable(_cam_prim)
        for _op in _xf.GetOrderedXformOps():
            if _op.GetOpType() == UsdGeom.XformOp.TypeOrient:
                _op.Set(q_total)
                break
        UsdGeom.Camera(_cam_prim).GetFocalLengthAttr().Set(
            float(_inspect_state["focal"]))
    except Exception as _e:
        log(f"[inspect] xform 갱신 실패: {_e!r}")


def _apply_inspect_cmd():
    """/tmp/cobot3_inspect_cmd.json 의 명령을 읽어 검사 카메라 Xform/focal 갱신.

    inspect_relay.py (rclpy 사이드카) 가 /robot/inspect/command 를 받아
    이 파일에 dump 한다. mtime 변화 시에만 처리 → 그러나 stabilization 부분
    (_update_inspect_xform) 은 매 step 호출돼 base body 회전 격리 유지.

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
        # 파일 없어도 stabilization 은 매 step 갱신
        _update_inspect_xform()
        return
    if m <= _inspect_state["last_mtime"]:
        _update_inspect_xform()
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
        # look_at_pixel: bbox 중심 이미지 픽셀 → inspect intrinsics 로
        # pan/tilt delta 계산 (HITL 사격 보조, 2026-05-21).
        # camera_info: fx = (W/aperture_mm) * focal_mm, cx = W/2, cy = H/2
        # 픽셀 (px, py) → 각도: dx = (px-cx)/fx, dy = (py-cy)/fy (radian 근사)
        if ("look_at_pixel" in cmd
                and isinstance(cmd["look_at_pixel"], (list, tuple))
                and len(cmd["look_at_pixel"]) >= 2):
            try:
                import math as _math
                px, py = float(cmd["look_at_pixel"][0]), \
                         float(cmd["look_at_pixel"][1])
                # 카메라 intrinsics — camera_info_publisher 와 동일 공식
                _W, _H = 1280, 720    # CamInspect 해상도 (기본값 가정)
                _focal = _inspect_state.get("focal", 18.0)
                _aperture = 20.955    # _HAP
                _fx = (_W / _aperture) * _focal
                _fy = (_H / (_aperture * _H / _W)) * _focal
                _cx, _cy = _W / 2.0, _H / 2.0
                _dx = (px - _cx) / _fx     # yaw delta (right=+)
                _dy = (py - _cy) / _fy     # pitch delta (down=+)
                # 현재 pan/tilt 에 누적 (-tilt 부호 변환: pixel y down=pitch down)
                _inspect_state["pan"] += _dx
                _inspect_state["tilt"] -= _dy
            except Exception:
                pass

    _update_inspect_xform()

    now = time.time()
    if now - _inspect_state["last_log"] > 1.0:
        _inspect_state["last_log"] = now
        log(f"[inspect] pan={_inspect_state['pan']:.2f} "
            f"tilt={_inspect_state['tilt']:.2f} "
            f"focal={_inspect_state['focal']:.1f} (rx={_inspect_state['rx']})")


# ── NPC 소환 (지통실 버튼 → npc_relay → /tmp mailbox → 본 함수) ──────────
# WHY: 사용자 요청 — 사람 형체 NPC 를 Go2 전방 20m 앞 z+5 에서 떨어뜨려
# YOLO person 검출 검증. 사람 USD 자산이 로컬에 없어 procedural primitive
# 합성 (capsule 몸통/사지 + 구체 머리, ~1.75m 인체 비율). RigidBody+Gravity
# 활성 → 자유낙하 → 지면 충돌.
_NPC_CMD_FILE = "/tmp/cobot3_npc_cmd.json"
_NPC_ROOT_PRIM = "/World/NPCs"
_npc_state = {"rx": 0, "spawned": 0, "last_mtime": 0.0}
_SKIN_COLOR = Gf.Vec3f(0.96, 0.80, 0.69)
_CLOTH_COLOR = Gf.Vec3f(0.20, 0.30, 0.55)


def _yaw_from_xformable(prim) -> float:
    """Xformable world rotation 에서 Z 축 yaw(rad) 추출."""
    import math as _math
    m = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(
        _U.TimeCode.Default())
    # 회전 행렬 [m00, m01, m02; m10, m11, m12; ...] → yaw = atan2(m10, m00)
    return _math.atan2(float(m[1][0]), float(m[0][0]))


def _build_npc(stage_, path, x, y, z):
    """Procedural 사람 형체 NPC (capsule 몸통/사지 + 구체 머리). RigidBody
    + CollisionAPI + 중력 자동 적용. 키 ≈ 1.75m, 어깨폭 ≈ 0.4m."""
    from pxr import UsdPhysics as _UP, UsdShade as _US
    if stage_.GetPrimAtPath(path).IsValid():
        stage_.RemovePrim(path)
    root = stage_.DefinePrim(path, "Xform")
    rxf = UsdGeom.Xformable(root)
    rxf.AddTranslateOp().Set(Gf.Vec3d(float(x), float(y), float(z)))
    _UP.RigidBodyAPI.Apply(root)
    _UP.MassAPI.Apply(root)
    _UP.MassAPI(root).CreateMassAttr(75.0)
    # 자식 prim 들은 root 의 RigidBody 에 자동 가담 (USD physics 규약).
    parts = [
        ("body",  "Capsule", (0.0, 0.0,  0.95), 0.18, 0.55, _CLOTH_COLOR),
        ("head",  "Sphere",  (0.0, 0.0,  1.62), 0.14, 0.0,  _SKIN_COLOR),
        ("arm_l", "Capsule", (-0.28, 0.0, 1.10), 0.07, 0.50, _SKIN_COLOR),
        ("arm_r", "Capsule", ( 0.28, 0.0, 1.10), 0.07, 0.50, _SKIN_COLOR),
        ("leg_l", "Capsule", (-0.10, 0.0, 0.40), 0.09, 0.60, _CLOTH_COLOR),
        ("leg_r", "Capsule", ( 0.10, 0.0, 0.40), 0.09, 0.60, _CLOTH_COLOR),
    ]
    for name, prim_type, (px, py, pz), radius, height, color in parts:
        p = stage_.DefinePrim(f"{path}/{name}", prim_type)
        pxf = UsdGeom.Xformable(p)
        pxf.AddTranslateOp().Set(Gf.Vec3d(px, py, pz))
        if prim_type == "Capsule":
            UsdGeom.Capsule(p).GetRadiusAttr().Set(float(radius))
            UsdGeom.Capsule(p).GetHeightAttr().Set(float(height))
        else:
            UsdGeom.Sphere(p).GetRadiusAttr().Set(float(radius))
        # 시각 색상 (displayColor primvar — material 없이 즉시 색칭)
        UsdGeom.Gprim(p).CreateDisplayColorAttr([color])
        _UP.CollisionAPI.Apply(p)


def _apply_npc_cmd():
    """NPC mailbox 폴링 — /tmp/cobot3_npc_cmd.json 의 mtime 변화 시 소환.

    payload (npc_relay.py 가 작성):
      {"forward_m": 20.0, "z_offset": 5.0, "count": 1} — Go2 base pose 기준
      forward(전방) 방향 N미터, base.z + z_offset 위치에서 떨어뜨림.
      forward_m 음수면 후방. count > 1 면 좌우 0.6m 간격으로 다중 소환.
    """
    try:
        m = os.path.getmtime(_NPC_CMD_FILE)
    except OSError:
        return
    if m <= _npc_state["last_mtime"]:
        return
    _npc_state["last_mtime"] = m
    _npc_state["rx"] += 1
    import json as _json
    try:
        with open(_NPC_CMD_FILE) as _f:
            cmd = _json.load(_f)
    except Exception as _e:
        log(f"[npc] JSON 파싱 실패: {_e!r}")
        return

    fwd = float(cmd.get("forward_m", 20.0))
    dz = float(cmd.get("z_offset", 5.0))
    count = max(1, int(cmd.get("count", 1)))

    base = stage.GetPrimAtPath(BASE_PRIM)
    if not (base and base.IsValid()):
        log(f"[npc] {BASE_PRIM} 없음 — 소환 무효")
        return
    bt = UsdGeom.Xformable(base).ComputeLocalToWorldTransform(
        _U.TimeCode.Default()).ExtractTranslation()
    yaw = _yaw_from_xformable(base)
    import math as _math
    fx = _math.cos(yaw); fy = _math.sin(yaw)
    sx = -fy; sy = fx  # 좌우 (yaw + 90° 방향 단위벡터)

    if not stage.GetPrimAtPath(_NPC_ROOT_PRIM).IsValid():
        stage.DefinePrim(_NPC_ROOT_PRIM, "Xform")

    for i in range(count):
        offset = (i - (count - 1) * 0.5) * 0.6   # 중심 정렬, 0.6m 간격
        nx = float(bt[0]) + fwd * fx + offset * sx
        ny = float(bt[1]) + fwd * fy + offset * sy
        nz = float(bt[2]) + dz
        _npc_state["spawned"] += 1
        idx = _npc_state["spawned"]
        path = f"{_NPC_ROOT_PRIM}/npc_{idx:03d}"
        try:
            _build_npc(stage, path, nx, ny, nz)
            log(f"[npc] 소환 #{idx} @ ({nx:.1f},{ny:.1f},{nz:.1f}) "
                f"base=({float(bt[0]):.1f},{float(bt[1]):.1f},{float(bt[2]):.1f}) "
                f"yaw={_math.degrees(yaw):.0f}° fwd={fwd}m dz={dz}m")
        except Exception as _e:
            log(f"[npc] 소환 실패: {_e!r}")


# ── Weather visuals + Wind force + Weapon (2026-05-21) ─────────────────
# WeatherVisuals: hi 브랜치 포팅 모듈. /World/Sun + DomeLight 갱신 + 비/눈/안개
# procedural geometry visibility 토글 + 매 step update.
# Wind: /tmp/cobot3_wind_state.json (wind_publisher 사이드카가 발행) 폴 →
# dc.apply_body_force 로 매 step Go2 base 에 풍력 인가. F = ½ρCdA|v_rel|·v_rel.
# Weapon: /tmp/cobot3_fire_cmd.json (weapon_relay) 폴 → _fire_sequence_step
# state machine 진행 (ramp_down → fire → ramp_up).
try:
    from weather_visuals import WeatherVisuals
    def _go2_xy():
        try:
            _bp = stage.GetPrimAtPath(BASE_PRIM)
            if _bp and _bp.IsValid():
                _bt = UsdGeom.Xformable(_bp).ComputeLocalToWorldTransform(
                    Usd.TimeCode.Default()).ExtractTranslation()
                return float(_bt[0]), float(_bt[1])
        except Exception:
            pass
        return 0.0, 0.0
    _weather = WeatherVisuals(stage, robot_xy_provider=_go2_xy, area=80.0)
    log(f"WeatherVisuals 등록 (time={_weather.time_of_day} "
        f"weather={_weather.weather})")
except Exception as _e:
    _weather = None
    log(f"⚠ WeatherVisuals 초기화 실패: {_e!r}")

# Weather command IPC poll (inspect_relay 패턴 — sub1 ros_bridge 가 /weather/
# command 받고 IPC 파일로 forward, 이쪽은 in-process subscribe 회피)
_WEATHER_CMD_FILE = "/tmp/cobot3_weather_cmd.json"
_weather_state = {"last_mtime": 0.0, "wind_mode": "calm",
                  "wind_random_dir": True, "wind_dir_deg": None,
                  "wind_speed": None}

def _apply_weather_cmd():
    """/tmp/cobot3_weather_cmd.json mtime 변화 시 WeatherVisuals.set_mode +
    wind 설정 echo. wind_mode 등은 별도 wind_publisher 가 직접 subscribe."""
    if _weather is None:
        return
    try:
        m = os.path.getmtime(_WEATHER_CMD_FILE)
    except OSError:
        return
    if m <= _weather_state["last_mtime"]:
        return
    _weather_state["last_mtime"] = m
    import json as _json
    try:
        with open(_WEATHER_CMD_FILE) as _f:
            d = _json.load(_f)
    except Exception as _e:
        log(f"[weather] JSON 파싱 실패: {_e!r}")
        return
    _weather.set_mode(time_of_day=d.get("time_of_day"),
                      weather=d.get("weather"))
    _weather_state["wind_mode"] = d.get("wind_mode", _weather_state["wind_mode"])
    log(f"[weather] mode → time={_weather.time_of_day} "
        f"weather={_weather.weather} wind={_weather_state['wind_mode']}")

# Wind force callback (매 step Go2 base 에 force 인가)
_WIND_STATE_FILE = "/tmp/cobot3_wind_state.json"
_wind_state = {"vx": 0.0, "vy": 0.0, "vz": 0.0, "last_mtime": 0.0}
# 공력 계수: Go2 측면 ½ρCdA = 0.5 * 1.225 * 1.0 * 0.15 ≈ 0.092
_WIND_K = 0.5 * 1.225 * 1.0 * 0.15

_wind_diag = {"last_log": 0.0, "applied": 0, "skipped_dc": 0,
              "skipped_zero": 0}

def _apply_wind_force():
    """매 step — /tmp/cobot3_wind_state.json 읽고 dc.apply_body_force 로
    Go2 base 에 wind force 인가. F = ½ρCdA|v_rel|·v_rel."""
    try:
        m = os.path.getmtime(_WIND_STATE_FILE)
        if m > _wind_state["last_mtime"]:
            import json as _json
            with open(_WIND_STATE_FILE) as _f:
                d = _json.load(_f)
            _wind_state["vx"] = float(d.get("vx", 0))
            _wind_state["vy"] = float(d.get("vy", 0))
            _wind_state["vz"] = float(d.get("vz", 0))
            _wind_state["last_mtime"] = m
    except (OSError, ValueError):
        pass
    if abs(_wind_state["vx"]) + abs(_wind_state["vy"]) < 0.05:
        _wind_diag["skipped_zero"] += 1
        return
    try:
        from omni.isaac.dynamic_control import _dynamic_control
        _dc = _dynamic_control.acquire_dynamic_control_interface()
        _base = _dc.get_rigid_body(BASE_PRIM)
        if not _base:
            _wind_diag["skipped_dc"] += 1
            return
        _bv = _dc.get_rigid_body_linear_velocity(_base)
        _vrx = _wind_state["vx"] - float(_bv.x)
        _vry = _wind_state["vy"] - float(_bv.y)
        _vrz = _wind_state["vz"] - float(_bv.z)
        _s = (_vrx * _vrx + _vry * _vry + _vrz * _vrz) ** 0.5
        _F = (_WIND_K * _s * _vrx, _WIND_K * _s * _vry, _WIND_K * _s * _vrz)
        # Isaac 5.1 시그니처: (body, force, position, isGlobal)
        # 2026-05-21 fix: 이전엔 position(0,0,0.05) 을 force 자리에 넣어
        # 0.05N 의 거의 0 force 만 인가됨 → wind 효과 안 보이던 진짜 원인.
        _dc.apply_body_force(_base, _F, (0.0, 0.0, 0.05), False)
        _wind_diag["applied"] += 1
        # 2초마다 진단 출력 (force 인가 실증)
        _now = time.time()
        if _now - _wind_diag["last_log"] > 2.0:
            _wind_diag["last_log"] = _now
            log(f"[wind] applied={_wind_diag['applied']} "
                f"skipped(dc={_wind_diag['skipped_dc']},"
                f"zero={_wind_diag['skipped_zero']}) "
                f"v_w=({_wind_state['vx']:.2f},{_wind_state['vy']:.2f}) "
                f"|v_rel|={_s:.2f} F=({_F[0]:.2f},{_F[1]:.2f}) N")
    except Exception as _e:
        _wind_diag["skipped_dc"] += 1
        _now = time.time()
        if _now - _wind_diag["last_log"] > 5.0:
            _wind_diag["last_log"] = _now
            log(f"[wind] apply 실패: {_e!r}")

# ── Weapon 부착 (실 라이플 모형 — procedural, 사용자가 추후 USD ref 교체 가능)
# Mount 위치: /World/Go2/base/weapon_mount (등판 위), muzzle 자식 prim.
# 시각: cylinder 4종 (barrel/receiver/stock/grip) — 절차적 placeholder.
WEAPON_MOUNT_PATH = "/World/Go2/base/weapon_mount"
MUZZLE_PATH = f"{WEAPON_MOUNT_PATH}/muzzle"

def _build_weapon_visual():
    """procedural rifle: barrel(cylinder) + receiver(cube) + stock(cube)."""
    if stage.GetPrimAtPath(WEAPON_MOUNT_PATH).IsValid():
        stage.RemovePrim(WEAPON_MOUNT_PATH)
    _root = UsdGeom.Xform.Define(stage, Sdf.Path(WEAPON_MOUNT_PATH))
    # mount 위치 (등판 위)
    _xfr = UsdGeom.Xformable(_root)
    _xfr.AddTranslateOp().Set(Gf.Vec3f(0.05, 0.0, 0.10))
    # barrel — cylinder along +X (forward)
    _bar = UsdGeom.Cylinder.Define(stage, Sdf.Path(f"{WEAPON_MOUNT_PATH}/barrel"))
    _bar.GetRadiusAttr().Set(0.012)
    _bar.GetHeightAttr().Set(0.55)
    _bar.GetAxisAttr().Set("X")
    _bxf = UsdGeom.Xformable(_bar.GetPrim())
    _bxf.AddTranslateOp().Set(Gf.Vec3f(0.20, 0.0, 0.0))
    _bar.GetDisplayColorAttr().Set([Gf.Vec3f(0.12, 0.12, 0.13)])
    # receiver — short cube
    _rec = UsdGeom.Cube.Define(stage, Sdf.Path(f"{WEAPON_MOUNT_PATH}/receiver"))
    _rec.GetSizeAttr().Set(1.0)
    _rxf = UsdGeom.Xformable(_rec.GetPrim())
    _rxf.AddTranslateOp().Set(Gf.Vec3f(-0.05, 0.0, 0.0))
    _rxf.AddScaleOp().Set(Gf.Vec3f(0.12, 0.05, 0.06))
    _rec.GetDisplayColorAttr().Set([Gf.Vec3f(0.18, 0.16, 0.14)])
    # stock
    _stk = UsdGeom.Cube.Define(stage, Sdf.Path(f"{WEAPON_MOUNT_PATH}/stock"))
    _stk.GetSizeAttr().Set(1.0)
    _sxf = UsdGeom.Xformable(_stk.GetPrim())
    _sxf.AddTranslateOp().Set(Gf.Vec3f(-0.22, 0.0, -0.005))
    _sxf.AddScaleOp().Set(Gf.Vec3f(0.20, 0.045, 0.05))
    _stk.GetDisplayColorAttr().Set([Gf.Vec3f(0.22, 0.18, 0.13)])
    # muzzle prim (raycast/임펄스 origin)
    _muz = UsdGeom.Xform.Define(stage, Sdf.Path(MUZZLE_PATH))
    UsdGeom.Xformable(_muz).AddTranslateOp().Set(Gf.Vec3f(0.475, 0.0, 0.0))
    log(f"weapon 시각 prim 생성: {WEAPON_MOUNT_PATH} (procedural rifle)")

try:
    _build_weapon_visual()
except Exception as _e:
    log(f"⚠ weapon prim 생성 실패: {_e!r}")

def _update_weapon_xform():
    """weapon_mount 를 inspect 카메라 pan/tilt 와 동기 — inspect 가 보는
    방향 = weapon 이 가리키는 방향 (HITL 운용자가 YOLO bbox 따라 회전)."""
    try:
        _w = stage.GetPrimAtPath(WEAPON_MOUNT_PATH)
        if not (_w and _w.IsValid()):
            return
        import math as _math
        _LIM = _math.radians(_INSPECT_LIM)
        _pan = max(-_LIM, min(_LIM, _inspect_state["pan"]))
        _tilt = max(-_LIM, min(_LIM, _inspect_state["tilt"]))
        # base frame 의 yaw(pan) → +Z 축 회전, pitch(tilt) → +Y 축 회전
        _hp, _ht = _pan * 0.5, _tilt * 0.5
        _qz = Gf.Quatf(_math.cos(_hp), Gf.Vec3f(0.0, 0.0, _math.sin(_hp)))
        _qy = Gf.Quatf(_math.cos(_ht), Gf.Vec3f(0.0, _math.sin(_ht), 0.0))
        _q = _qz * _qy
        _xf = UsdGeom.Xformable(_w)
        _orient_op = None
        for _op in _xf.GetOrderedXformOps():
            if _op.GetOpType() == UsdGeom.XformOp.TypeOrient:
                _orient_op = _op; break
        if _orient_op is None:
            _orient_op = _xf.AddOrientOp()
        _orient_op.Set(_q)
    except Exception:
        pass

# ── 사격 시퀀스 상태머신 ────────────────────────────────────────────────
# states: IDLE → RAMP_DOWN(0.2s) → FIRE(1step impulse) → HOLD(0.5s) →
#         RAMP_UP(0.2s) → COOLDOWN(2s) → IDLE
_FIRE_CMD_FILE = "/tmp/cobot3_fire_cmd.json"
_FIRE_RESULT_FILE = "/tmp/cobot3_fire_result.json"
_WEAPON_STATE_FILE = "/tmp/cobot3_weapon_state.json"
_fire = {"state": "IDLE", "t_state": 0.0, "fire_id": None,
         "last_cmd_mtime": 0.0, "cooldown_until": 0.0}
# stance ramp 목표 (Margolis WTW: body_height -0.08, stance_w +0.05)
_FIRE_BH = -0.08
_FIRE_SW = +0.05
# 7.62 NATO 실측 임펄스 ≈ 10 N·s. 1 physics step (5ms @ 200Hz) → 2000 N.
# 12kg base → Δv=0.83 m/s 후방 점프 (WTW 보행 정책이 흡수). 2026-05-21:
# 이전 2500N + apply_body_force 인자 swap 버그 → Go2 가 발사되는 증상 →
# 인자 순서 fix + 임펄스 적정값. 시각적 반동도 자연스러움.
_FIRE_IMPULSE_N = 2000.0

def _write_weapon_state():
    import json as _json
    try:
        cd = max(0.0, _fire["cooldown_until"] - time.time())
        payload = {"state": _fire["state"], "fire_id": _fire["fire_id"],
                   "cooldown_remaining_s": cd, "ts": time.time()}
        with open(_WEAPON_STATE_FILE + ".tmp", "w") as _f:
            _json.dump(payload, _f)
        os.replace(_WEAPON_STATE_FILE + ".tmp", _WEAPON_STATE_FILE)
    except Exception:
        pass

def _write_fire_result(ok: bool, state: str):
    import json as _json
    try:
        payload = {"fire_id": _fire["fire_id"], "ok": ok, "state": state,
                   "ts": time.time()}
        with open(_FIRE_RESULT_FILE + ".tmp", "w") as _f:
            _json.dump(payload, _f)
        os.replace(_FIRE_RESULT_FILE + ".tmp", _FIRE_RESULT_FILE)
    except Exception:
        pass

def _poll_fire_cmd():
    try:
        m = os.path.getmtime(_FIRE_CMD_FILE)
    except OSError:
        return
    if m <= _fire["last_cmd_mtime"]:
        return
    _fire["last_cmd_mtime"] = m
    if _fire["state"] != "IDLE" or time.time() < _fire["cooldown_until"]:
        log(f"[weapon] busy ({_fire['state']}) — 명령 무시")
        return
    import json as _json
    try:
        with open(_FIRE_CMD_FILE) as _f:
            d = _json.load(_f)
        _fire["fire_id"] = d.get("fire_id")
    except Exception:
        return
    _fire["state"] = "RAMP_DOWN"
    _fire["t_state"] = time.time()
    log(f"[weapon] FIRE 시작 id={_fire['fire_id']}")
    _write_weapon_state()

def _step_fire(dt: float):
    """매 step 호출 — 상태머신 진행."""
    if _ctrl is None:
        return
    if _fire["state"] == "IDLE":
        return
    elapsed = time.time() - _fire["t_state"]
    st = _fire["state"]
    if st == "RAMP_DOWN":
        # 0~0.2s 동안 stance 목표로 ramp
        a = min(1.0, elapsed / 0.2)
        _ctrl.set_stance_override(_FIRE_BH * a, _FIRE_SW * a, 0.0)
        if elapsed >= 0.2:
            _fire["state"] = "FIRE"
            _fire["t_state"] = time.time()
            log(f"[weapon] stance 완료 → impulse 인가")
    elif st == "FIRE":
        # 1 step 임펄스 — muzzle 방향(inspect pan/tilt 적용된 weapon forward)
        try:
            import math as _math
            _pan = _inspect_state["pan"]
            _tilt = _inspect_state["tilt"]
            # base 중심 world pose (force 적용 위치 — muzzle 사용 시 회전
            # 모멘트로 Go2 가 휘청거림. base 중심 직접 인가가 더 안정.
            _base_prim = stage.GetPrimAtPath(BASE_PRIM)
            if _base_prim and _base_prim.IsValid():
                _base_world = UsdGeom.Xformable(_base_prim) \
                    .ComputeLocalToWorldTransform(Usd.TimeCode.Default()) \
                    .ExtractTranslation()
                _muz_pos = (float(_base_world[0]), float(_base_world[1]),
                            float(_base_world[2]))
            else:
                _muz_pos = (0.0, 0.0, 0.0)
            # force 방향: inspect 가 가리키는 방향의 역방향 (반동)
            # base yaw 까지 합성 필요 — Go2 base orientation 가져와서 world 좌표
            _bp = stage.GetPrimAtPath(BASE_PRIM)
            _base_yaw = 0.0
            if _bp and _bp.IsValid():
                from pxr import Gf as _GF
                _w2l = UsdGeom.Xformable(_bp).ComputeLocalToWorldTransform(
                    Usd.TimeCode.Default())
                # 회전 quat → yaw 추출
                _q = _w2l.ExtractRotation().GetQuat()
                _qw, _qi = _q.GetReal(), _q.GetImaginary()
                _qx, _qy, _qz = float(_qi[0]), float(_qi[1]), float(_qi[2])
                _base_yaw = _math.atan2(2 * (_qw * _qz + _qx * _qy),
                                        1 - 2 * (_qy * _qy + _qz * _qz))
            # weapon world yaw = base_yaw + pan
            _fyaw = _base_yaw + _pan
            _fpitch = _tilt
            _Fx_world = -_FIRE_IMPULSE_N * _math.cos(_fpitch) * _math.cos(_fyaw)
            _Fy_world = -_FIRE_IMPULSE_N * _math.cos(_fpitch) * _math.sin(_fyaw)
            _Fz_world = +_FIRE_IMPULSE_N * 0.10
            _ctrl.apply_external_impulse(
                (_Fx_world, _Fy_world, _Fz_world),
                _muz_pos)
            log(f"[weapon] impulse F=({_Fx_world:.0f},{_Fy_world:.0f},"
                f"{_Fz_world:.0f}) @ muzzle yaw={_math.degrees(_fyaw):.1f}°")
        except Exception as _e:
            log(f"[weapon] impulse 실패: {_e!r}")
        _fire["state"] = "HOLD"
        _fire["t_state"] = time.time()
    elif st == "HOLD":
        # stance 유지 0.5s — 반동 시각효과 + 안정화
        if elapsed >= 0.5:
            _fire["state"] = "RAMP_UP"
            _fire["t_state"] = time.time()
    elif st == "RAMP_UP":
        a = max(0.0, 1.0 - elapsed / 0.2)
        _ctrl.set_stance_override(_FIRE_BH * a, _FIRE_SW * a, 0.0)
        if elapsed >= 0.2:
            _ctrl.set_stance_override(0, 0, 0)
            _fire["state"] = "COOLDOWN"
            _fire["t_state"] = time.time()
            _fire["cooldown_until"] = time.time() + 2.0
            log(f"[weapon] 사격 완료 id={_fire['fire_id']} → cooldown 2s")
            _write_fire_result(True, "completed")
            _write_weapon_state()
    elif st == "COOLDOWN":
        if elapsed >= 2.0:
            _fire["state"] = "IDLE"
            _fire["fire_id"] = None
            _write_weapon_state()
    # state file 1Hz 업데이트
    if int(elapsed * 4) != int((elapsed - dt) * 4):
        _write_weapon_state()


n = 0
_TL = omni.timeline.get_timeline_interface()
_tl_replays = 0
try:
    while simulation_app.is_running():
        world.step(render=True)
        n += 1
        _apply_cmd()
        _apply_inspect_cmd()
        _apply_npc_cmd()
        _update_overhead_xform()
        _update_weapon_xform()
        _apply_weather_cmd()
        if _weather is not None:
            _weather.update(world.get_physics_dt())
        _apply_wind_force()
        _poll_fire_cmd()
        _step_fire(world.get_physics_dt())
        if n in (60, 150):
            _diag()
        # timeline play 자가 복원 — GUI 일시정지나 외부 stop() 으로 멈춰
        # simTime 이 동결되면 OG 모든 토픽 0Hz. 100 step 마다 확인.
        if n % 100 == 0 and not _TL.is_playing():
            _TL.play()
            _tl_replays += 1
            log(f"timeline.play() 자동 재시작 (n={n} replays={_tl_replays})")
        if n % 300 == 0:
            t = _TL.get_current_time()
            log(f"stepped {n} | simTime={t:.2f} | cmd_rx={_cmd_state['rx']} "
                f"playing={_TL.is_playing()} replays={_tl_replays}")
            _diag()
except KeyboardInterrupt:
    log("중지(Ctrl+C)")
finally:
    simulation_app.close()
