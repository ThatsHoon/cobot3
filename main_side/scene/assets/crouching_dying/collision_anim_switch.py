"""
Crouching Character → Dying on Collision
=========================================
사용법:
  1. Isaac Sim에서 CrouchDying.usd 열기
  2. Script Editor에서 이 파일 실행
  3. Play 누르면 Walking 시작
  4. 캐릭터 주변에 RigidBody 오브젝트가 진입하면 자동으로 Dying 재생
"""

import omni.usd
import omni.timeline
import omni.physx as physx_
import omni.kit.app
import builtins
import carb
from pxr import UsdSkel, Sdf

# ─── 설정 ───────────────────────────────────────────────
SKEL_ROOT    = "/World/mixamorig_Hips"
SKELETON     = "/World/mixamorig_Hips/Skeleton"
WALK_ANIM    = Sdf.Path("/World/mixamorig_Hips/mixamo_com")
DYING_ANIM   = Sdf.Path("/World/mixamorig_Hips/Dying_Anim")
DYING_END_TC = 104.8   # Dying 애니메이션 끝 timecode

TRIGGER_CENTER = carb.Float3(0.0, 1.0, 0.0)  # 캐릭터 중심 위치
TRIGGER_RADIUS = 1.2                           # 충돌 감지 반경 (m)

# overlap_sphere 에서 제외할 경로 키워드 (환경 오브젝트)
IGNORE = ["GroundPlane", "CollisionPlane", "CollisionMesh",
          "mixamorig", "Looks", "Ch49"]
# ────────────────────────────────────────────────────────


def _set_anim(anim_path, end_tc, loop):
    """SkelRoot + Skeleton 바인딩을 동시에 변경 (한 쪽만 바꾸면 적용 안 됨)."""
    s = omni.usd.get_context().get_stage()
    for prim_path in [SKEL_ROOT, SKELETON]:
        prim = s.GetPrimAtPath(prim_path)
        if prim.IsValid():
            UsdSkel.BindingAPI(prim).GetAnimationSourceRel().SetTargets([anim_path])
    s.SetStartTimeCode(0.0)
    s.SetEndTimeCode(end_tc)
    tl = omni.timeline.get_timeline_interface()
    tl.set_looping(loop)
    tl.set_current_time(0.0)
    tl.play()


def setup():
    # 이전 구독 정리 (스크립트 재실행 시 중복 방지)
    for attr in ["_col_step_sub", "_col_update_sub"]:
        sub = getattr(builtins, attr, None)
        if sub:
            try:
                sub.unsubscribe()
            except Exception:
                pass
        setattr(builtins, attr, None)

    builtins._col_trigger  = False
    builtins._col_switched = False

    # Walking 애니메이션으로 초기화
    _set_anim(WALK_ANIM, 30.0, True)

    # ── Physics step: 충돌 감지 (플래그만 세팅, stage 수정 금지) ──
    def on_step(dt):
        if builtins._col_switched or builtins._col_trigger:
            return
        qi  = physx_.get_physx_scene_query_interface()
        hit = [None]

        def report(h):
            col = str(h.collision)
            if any(ig in col for ig in IGNORE):
                return True   # 무시하고 계속
            hit[0] = col
            return False      # 첫 유효 히트에서 중단

        qi.overlap_sphere(TRIGGER_RADIUS, TRIGGER_CENTER, report, False)
        if hit[0]:
            builtins._col_trigger = True  # 플래그 ON

    # ── Kit update: 메인 스레드에서 stage 수정 ──
    def on_update(e):
        if not builtins._col_trigger:
            return
        builtins._col_trigger  = False
        builtins._col_switched = True

        # 구독 해제 (더 이상 감지 불필요)
        builtins._col_step_sub.unsubscribe()
        builtins._col_update_sub.unsubscribe()
        builtins._col_step_sub   = None
        builtins._col_update_sub = None

        _set_anim(DYING_ANIM, DYING_END_TC, False)
        print("[AnimSwitch] 충돌 감지 → Dying 애니메이션 재생")

    builtins._col_step_sub = (
        physx_.get_physx_interface()
        .subscribe_physics_step_events(on_step)
    )
    builtins._col_update_sub = (
        omni.kit.app.get_app()
        .get_update_event_stream()
        .create_subscription_to_push(on_update, name="col_anim_switch")
    )

    print("=" * 50)
    print("충돌 → Dying 애니메이션 시스템 활성화")
    print(f"  감지 반경: {TRIGGER_RADIUS}m  /  중심: {TRIGGER_CENTER}")
    print("  Play 누르면 Walking 시작, 충돌 시 Dying으로 전환")
    print("=" * 50)


setup()
