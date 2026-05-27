"""Soldier 소환 + Walking → 피격 시 Dying — camera_publisher 에서 호출.

스폰 영역 (gp_scene 직사각형):
  x∈[166.91, 226.63], y∈[906.25, 915.71], z=4.8

동작 흐름:
  1. C2 spawn_soldier → /robot/npc/spawn ROS → /tmp/cobot3_npc_cmd.json → poll
  2. spawn(): CrouchDying.usd ref 생성 + walk anim 바인딩 + capsule collider 부착
  3. tick(dt): walking 군인 −Y 이동. fence Y 도달 시 정지 (walk 유지).
  4. on_weapon_hit(hit): "/World/Soldiers" 경로 매칭 → dying 전환
  5. dying 완료 (~4.4s): prim 제거, timeline [0-30 loop] 복원

WHY SkelRoot+Skeleton 양쪽 binding: Skeleton 프림이 독립 binding 을 가지므로
한 쪽만 바꾸면 애니메이션이 적용 안 됨 (collision_anim_switch.py 동일 패턴).

WHY timeline reset on die: UsdSkel 은 global stage time 을 사용. dying anim
을 TC=0 부터 재생하려면 tl.set_current_time(0.0) 이 필요.
timeline reset 시 walking 군인들이 TC=0 으로 점프 (0.1s hitch) — 허용.
"""
import json
import math
import os
import random
import time

# ── 스폰 영역 ───────────────────────────────────────────────────────────────
_SPAWN_X0 = 166.91049
_SPAWN_X1 = 226.63029
_SPAWN_Y0 = 915.71301   # 높은 Y (스폰 근원)
_SPAWN_Y1 = 906.25354   # 낮은 Y (fence 쪽)
_SPAWN_Z  = 4.8

# ── 이동 & 한도 ─────────────────────────────────────────────────────────────
_SPEED      = float(os.environ.get("GP_SOLDIER_SPEED",    "1.0"))
_FENCE_Y    = float(os.environ.get("GP_SOLDIER_FENCE_Y",  "903.0"))
# WHY 903.0: gp_scene /World/Fence_Waypoints 에서 spawn X=[166~226] 범위의
# fence 실측 Y = 901.1~901.8. soldier root→body front 오프셋 ~0.72m 감안 시
# root 정지 Y=903 → body front Y≈902.3 → fence(Y≈901.5) 에 닿지 않고 멈춤.
# 기존 900.0 은 fence 보다 1m 낮아 통과 후 1m 지나 정지하는 문제 발생.
_YAW_DEG    = float(os.environ.get("GP_SOLDIER_YAW_DEG",  "0.0"))
# WHY 0°: CrouchDying.usd Y-up 에서 캐릭터는 +Z 를 바라봄.
# RotateX(+90°) 적용 후 +Z_old → -Y_new 이므로 캐릭터가 -Y(fence 방향)를 바라봄.
# 추가 yaw 0° = 방향 그대로 유지. 이전 180° 는 반대 방향(fence 반대)이었음.
_MAX_SOLDIERS = int(os.environ.get("GP_SOLDIER_MAX",      "10"))

# ── USD 경로 ─────────────────────────────────────────────────────────────────
SOLDIER_ROOT = "/World/Soldiers"
_USD_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "scene", "assets", "crouching_dying", "CrouchDying.usd")

# CrouchDying.usd 내부 경로 (character/ sub-prim 기준)
_SKEL_ROOT_REL  = "mixamorig_Hips"
_SKELETON_REL   = "mixamorig_Hips/Skeleton"
_WALK_ANIM_REL  = "mixamorig_Hips/mixamo_com"
_DYING_ANIM_REL = "mixamorig_Hips/Dying_Anim"

_DYING_END_TC = 104.8
_WALK_END_TC  = 30.0

_NPC_CMD_FILE = "/tmp/cobot3_npc_cmd.json"


class SoldierManager:
    """군인 NPC 생명주기 관리 (spawn / walk / die / cleanup)."""

    def __init__(self):
        self._stage = None
        self._tl    = None
        self._soldiers: dict = {}   # {prim_path: state_dict}
        self._idx = 0
        self._last_mtime = 0.0

    # ── 초기화 ────────────────────────────────────────────────────────────────
    def init(self, stage):
        """씬 로드 직후 호출. stage 참조 저장 + /World/Soldiers 생성 + timeline."""
        import omni.timeline
        from pxr import UsdGeom, Sdf
        self._stage = stage
        self._tl    = omni.timeline.get_timeline_interface()
        # 컨테이너 prim
        if not stage.GetPrimAtPath(SOLDIER_ROOT).IsValid():
            stage.DefinePrim(SOLDIER_ROOT, "Xform")
        # 초기 timeline: walk 루프 범위 보장
        self._restore_walk_timeline()
        # 기존 cmd 파일 mtime 으로 초기화 — 이전 세션 파일로 자동 소환 방지
        # WHY: _last_mtime=0.0 이면 init 직후 첫 tick 에서 기존 파일을 "새 명령"
        # 으로 오해해 spawn 됨.
        try:
            self._last_mtime = os.path.getmtime(_NPC_CMD_FILE)
        except OSError:
            self._last_mtime = 0.0
        _log(f"[soldier] init 완료. USD={_USD_PATH} speed={_SPEED}m/s "
             f"fence_y={_FENCE_Y} max={_MAX_SOLDIERS}")

    # ── 매 프레임 ─────────────────────────────────────────────────────────────
    def tick(self, dt: float):
        """camera_publisher 메인 루프에서 매 프레임 호출."""
        self._poll_spawn_cmd()
        self._update_walking(dt)
        self._update_dying()

    # ── 피격 콜백 ─────────────────────────────────────────────────────────────
    def on_weapon_hit(self, hit: dict):
        """_step_fire() 가 완료 결과에서 호출. hit = {target, point, range_m}."""
        if not hit:
            return
        target = str(hit.get("target", ""))
        if SOLDIER_ROOT not in target:
            return
        # 1-at-a-time: dying 중인 군인 있으면 무시
        if any(s["state"] == "dying" for s in self._soldiers.values()):
            return
        # 피격 군인 root 경로 추출: "/World/Soldiers/soldier_NNN/..." → ".../soldier_NNN"
        for path in list(self._soldiers.keys()):
            if path in target and self._soldiers[path]["state"] == "walking":
                _log(f"[soldier] 피격 → dying: {path}  "
                     f"range={hit.get('range_m', 0):.1f}m")
                self._trigger_die(path)
                return

    # ── spawn ─────────────────────────────────────────────────────────────────
    def spawn(self, count: int = 1):
        """직사각형 내 랜덤 위치에 군인 소환."""
        active = len(self._soldiers)
        if active >= _MAX_SOLDIERS:
            _log(f"[soldier] max({_MAX_SOLDIERS}) 초과 — 소환 무시")
            return
        count = min(count, _MAX_SOLDIERS - active)
        for _ in range(count):
            x = random.uniform(_SPAWN_X0, _SPAWN_X1)
            y = random.uniform(_SPAWN_Y1, _SPAWN_Y0)
            self._create_soldier(x, y, _SPAWN_Z)

    # ── 내부 ──────────────────────────────────────────────────────────────────
    def _create_soldier(self, x: float, y: float, z: float):
        from pxr import UsdGeom, Gf, Sdf, UsdPhysics
        stage = self._stage
        idx = self._idx
        self._idx += 1
        root_path = f"{SOLDIER_ROOT}/soldier_{idx:03d}"

        # 기존 prim 제거(재생성 방어)
        if stage.GetPrimAtPath(root_path).IsValid():
            stage.RemovePrim(Sdf.Path(root_path))

        # root Xform: 위치 + 방향
        root = stage.DefinePrim(root_path, "Xform")
        xf = UsdGeom.Xformable(root)
        trans_op = xf.AddTranslateOp()
        trans_op.Set(Gf.Vec3d(float(x), float(y), float(z)))
        rad = math.radians(_YAW_DEG / 2.0)
        xf.AddOrientOp().Set(
            Gf.Quatf(math.cos(rad), Gf.Vec3f(0.0, 0.0, math.sin(rad))))

        # Capsule collider (hit-scan raycast 인식 안정화)
        # WHY: SkelRoot mesh 만으로는 PhysX collider 없어 raycast 미검출 가능.
        cap_prim = stage.DefinePrim(f"{root_path}/hitbox", "Capsule")
        cap_xf = UsdGeom.Xformable(cap_prim)
        cap_xf.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 0.8))  # 발→머리 중심
        UsdGeom.Capsule(cap_prim).GetRadiusAttr().Set(0.3)
        UsdGeom.Capsule(cap_prim).GetHeightAttr().Set(1.6)
        UsdGeom.Gprim(cap_prim).CreateDisplayColorAttr([Gf.Vec3f(0.0, 1.0, 0.0)])
        UsdGeom.Imageable(cap_prim).CreateVisibilityAttr("invisible")  # 시각 숨김
        UsdPhysics.CollisionAPI.Apply(cap_prim)

        # CrouchDying.usd 참조
        # WHY scale=0.01 + RotateX(90°):
        #   CrouchDying.usd 는 metersPerUnit=0.01(cm 스케일) + upAxis=Y.
        #   gp_scene 은 metersPerUnit=1.0(m) + upAxis=Z.
        #   scale=0.01 로 cm→m 변환, RotateX(90°) 로 Y-up→Z-up 축 정렬.
        #   (RotateX +90°: Y_old→Z_new 이므로 캐릭터 "위"가 Z 로 맞춰짐)
        char_prim = stage.DefinePrim(f"{root_path}/character", "Xform")
        char_xf = UsdGeom.Xformable(char_prim)
        char_xf.AddScaleOp().Set(Gf.Vec3f(0.01, 0.01, 0.01))
        char_xf.AddRotateXOp().Set(90.0)
        char_prim.GetReferences().AddReference(_USD_PATH)

        # GroundPlane 비활성화 — CrouchDying.usd 에 포함된 50×50m 충돌 평면이
        # 씬 지형을 흰색으로 덮어버리므로 반드시 비활성화해야 함.
        # WHY: GroundPlane/CollisionMesh 는 Z=[-2500,2500] cm 범위의 거대 평면.
        # RotateX(90°)+scale(0.01) 후 씬 지면 높이(z=4.8)에 50×50m 흰 평면 생성.
        ground_prim = stage.GetPrimAtPath(f"{root_path}/character/GroundPlane")
        if ground_prim.IsValid():
            ground_prim.SetActive(False)

        # Walking 애니메이션 바인딩 (첫 스폰은 USD 로드 후 prim 이 valid 해야 함)
        # Isaac Sim 은 reference 를 즉시 resolve 하므로 바인딩 가능.
        self._bind_anim(root_path, walk=True)

        # timeline walk 루프 확인 + 재생
        self._restore_walk_timeline()

        self._soldiers[root_path] = {
            "state":        "walking",
            "x":            x,
            "y":            y,
            "trans_op":     trans_op,
            "die_start_ts": None,
        }
        _log(f"[soldier] 소환 #{idx} @ ({x:.1f},{y:.1f},{z}) "
             f"yaw={_YAW_DEG:.0f}°  활성={len(self._soldiers)}")

    def _bind_anim(self, root_path: str, walk: bool):
        """SkelRoot + Skeleton 양쪽에 walk/dying 애니메이션 소스 바인딩.
        collision_anim_switch.py 의 _set_anim 패턴을 per-instance 로 적용."""
        from pxr import UsdSkel, Sdf
        stage = self._stage
        anim_rel = _WALK_ANIM_REL if walk else _DYING_ANIM_REL
        anim_path = Sdf.Path(f"{root_path}/character/{anim_rel}")
        bound = 0
        for sub_rel in (_SKEL_ROOT_REL, _SKELETON_REL):
            prim = stage.GetPrimAtPath(f"{root_path}/character/{sub_rel}")
            if prim.IsValid():
                try:
                    UsdSkel.BindingAPI(prim).GetAnimationSourceRel().SetTargets(
                        [anim_path])
                    bound += 1
                except Exception as exc:
                    _log(f"[soldier] anim bind 실패 {prim.GetPath()}: {exc!r}")
        if bound == 0:
            _log(f"[soldier] {root_path} — SkelRoot/Skeleton prim 아직 미확인 "
                 f"(reference 로드 지연 가능). anim_rel={anim_rel}")

    def _trigger_die(self, path: str):
        """피격 군인을 dying 상태로 전환. timeline reset → dying anim 재생."""
        s = self._soldiers[path]
        s["state"] = "dying"
        s["die_start_ts"] = time.monotonic()
        self._bind_anim(path, walk=False)
        # collision_anim_switch.py 동일: timeline TC=0 reset + dying 범위 + play
        stage = self._stage
        tl = self._tl
        stage.SetStartTimeCode(0.0)
        stage.SetEndTimeCode(_DYING_END_TC)
        tl.set_looping(False)
        tl.set_current_time(0.0)
        tl.play()

    def _update_walking(self, dt: float):
        """Walking 군인 −Y 방향 이동. fence_y 도달 시 정지 (prim 유지)."""
        from pxr import Gf
        for s in self._soldiers.values():
            if s["state"] != "walking":
                continue
            if s["y"] <= _FENCE_Y:
                continue   # fence 도달 → 이동 중지, walk anim 유지
            s["y"] = max(_FENCE_Y, s["y"] - _SPEED * dt)
            s["trans_op"].Set(Gf.Vec3d(s["x"], s["y"], _SPAWN_Z))

    def _update_dying(self):
        """dying 완료 (~4.4s) 후 prim 제거 + timeline 복원."""
        from pxr import Sdf
        stage = self._stage
        now = time.monotonic()
        dying_duration = _DYING_END_TC / 24.0   # 104.8 frames @ 24fps ≈ 4.37s
        for path, s in list(self._soldiers.items()):
            if s["state"] != "dying":
                continue
            if now - s["die_start_ts"] < dying_duration:
                continue
            # 제거
            try:
                stage.RemovePrim(Sdf.Path(path))
            except Exception as exc:
                _log(f"[soldier] prim 제거 실패 {path}: {exc!r}")
            del self._soldiers[path]
            _log(f"[soldier] prim 제거 완료: {path}  활성={len(self._soldiers)}")
            # 남은 dying 없으면 walk timeline 복원
            if not any(s2["state"] == "dying" for s2 in self._soldiers.values()):
                self._restore_walk_timeline()
            break  # 한 번에 하나씩 처리

    def _restore_walk_timeline(self):
        """timeline 을 [0, 30, loop=True, play] 로 복원."""
        stage = self._stage
        tl = self._tl
        if stage is None or tl is None:
            return
        stage.SetStartTimeCode(0.0)
        stage.SetEndTimeCode(_WALK_END_TC)
        tl.set_looping(True)
        if not tl.is_playing():
            tl.play()

    def _poll_spawn_cmd(self):
        """/tmp/cobot3_npc_cmd.json mtime 변화 시 spawn 호출.
        기존 _apply_npc_cmd() 와 동일 IPC 구조. forward_m/z_offset 무시."""
        try:
            m = os.path.getmtime(_NPC_CMD_FILE)
        except OSError:
            return
        if m <= self._last_mtime:
            return
        self._last_mtime = m
        try:
            with open(_NPC_CMD_FILE) as f:
                cmd = json.load(f)
        except Exception as exc:
            _log(f"[soldier] spawn cmd 파싱 실패: {exc!r}")
            return
        count = max(1, int(cmd.get("count", 1)))
        _log(f"[soldier] spawn cmd 수신: count={count}")
        self.spawn(count)


def _log(msg: str):
    """stdout 으로 출력 — camera_publisher console.log 에 캡처됨."""
    print(msg, flush=True)
