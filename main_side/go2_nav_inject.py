"""Go2 자율 보행(walk-these-ways) — 라이브 Isaac+MCP GUI 주입 부트스트랩.

TCP:8766 스크립트실행 RPC 로 이 파일 전체를 Isaac 에 주입한다.
go2_controller.Go2WtwController(actuator-net + nav P-제어)를 단일 소스로
재사용하고, 현 씬의 /World/Go2(/base) 를 그대로 제어한다.

모드 (/tmp/go2_nav_mode.txt, 없으면 'stand'):
  stand : nav_goal 미설정 → 제자리 안정 기립 검증 (M1 gate)
  near  : ready 시 base XY 에서 -X 5m 지점 nav_goal → 단거리 직진 검증
  cone  : ready 시 /World/Cone world XY nav_goal → 자율 주행 (M2)

주입 컨텍스트 규약: world.reset()/app.update() 호출 금지. physx step
이벤트 구독으로 콜백 구동. 상태는 /tmp/go2_nav.txt 로만 검증(콘솔 비의존).
"""
import builtins
import sys

_MAIN = "/home/rokey/dev_ws/isaac_sim/cobot3/main_side"
if _MAIN not in sys.path:
    sys.path.insert(0, _MAIN)

_NAV_LOG = "/tmp/go2_nav.txt"


def _read_mode():
    try:
        with open("/tmp/go2_nav_mode.txt") as f:
            m = f.read().strip().lower()
        return m if m in ("stand", "near", "cone") else "stand"
    except Exception:
        return "stand"


def _cone_xy():
    """/World/Cone world bbox 중심 XY (없으면 None)."""
    try:
        import omni.usd
        from pxr import Usd, UsdGeom
        st = omni.usd.get_context().get_stage()
        pr = st.GetPrimAtPath("/World/Cone")
        if not pr or not pr.IsValid():
            return None
        bc = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])
        rg = bc.ComputeWorldBound(pr).ComputeAlignedRange()
        mn, mx = rg.GetMin(), rg.GetMax()
        return ((float(mn[0]) + float(mx[0])) / 2.0,
                (float(mn[1]) + float(mx[1])) / 2.0)
    except Exception:
        return None


# ── 이전 주입 정리 (재주입 안전) ────────────────────────────────────
_old = getattr(builtins, "_go2_nav_sub", None)
if _old is not None:
    try:
        _old.unsubscribe()
    except Exception:
        pass
    try:
        del builtins._go2_nav_sub
    except Exception:
        pass

from go2_controller import Go2WtwController, _proj_gravity  # noqa: E402

_mode = _read_mode()
_ctrl = Go2WtwController("/World/Go2/base")

builtins._go2_nav_ctrl = _ctrl
builtins._go2_nav_state = {"n": 0, "mode": _mode, "goal_set": False}

with open(_NAV_LOG, "w") as _f:
    _f.write(f"[inject] mode={_mode} ctrl=/World/Go2/base "
             f"latent_dim={_ctrl._latent_dim}\n")

# 라이브 GUI(재생 중) 동기 컨텍스트에서 articulation 미리 init.
# physx 콜백 내 initialize() 는 이 컨텍스트에서 dof_names 를 못 채움(검증).
# 동기 init 는 정상 → _art 주입하고 컨트롤러의 deferred-init 스킵.
try:
    from isaacsim.core.prims import SingleArticulation
    _pa = SingleArticulation(prim_path="/World/Go2/base")
    _pa.initialize()
    _dn = list(_pa.dof_names) if _pa.dof_names else []
    if len(_dn) >= 12:
        _ctrl._art = _pa
        with open(_NAV_LOG, "a") as _f:
            _f.write(f"[preinit] sync articulation init OK dof={len(_dn)}\n")
    else:
        with open(_NAV_LOG, "a") as _f:
            _f.write(f"[preinit] dof={len(_dn)} (<12) — 콜백 init 폴백\n")
except Exception as _e:
    with open(_NAV_LOG, "a") as _f:
        _f.write(f"[preinit_err] {_e!r}\n")


def _nav_step(dt):
    st = builtins._go2_nav_state
    ctrl = builtins._go2_nav_ctrl
    try:
        ctrl.on_physics_step(dt)
    except Exception as exc:
        if st["n"] % 200 == 0:
            with open(_NAV_LOG, "a") as f:
                f.write(f"[on_step_err n={st['n']}] {exc!r}\n")
        st["n"] += 1
        return

    st["n"] += 1

    # ready 가 된 첫 시점에 모드별 nav_goal 1회 설정
    if (not st["goal_set"]) and getattr(ctrl, "_ready", False):
        try:
            pos, _ = ctrl._art.get_world_pose()
            bx, by = float(pos[0]), float(pos[1])
            if st["mode"] == "near":
                ctrl.set_nav_goal(bx - 5.0, by)
            elif st["mode"] == "cone":
                cxy = _cone_xy()
                if cxy is not None:
                    ctrl.set_nav_goal(cxy[0], cxy[1])
            st["goal_set"] = True
            with open(_NAV_LOG, "a") as f:
                f.write(f"[goal] mode={st['mode']} base=[{bx:.2f},{by:.2f}] "
                        f"nav_goal={ctrl._nav_goal}\n")
        except Exception as exc:
            with open(_NAV_LOG, "a") as f:
                f.write(f"[goal_err n={st['n']}] {exc!r}\n")

    # 주기 상태 기록
    if st["n"] % 50 == 1:
        try:
            if getattr(ctrl, "_ready", False):
                pos, quat = ctrl._art.get_world_pose()
                g = _proj_gravity(float(quat[0]), float(quat[1]),
                                  float(quat[2]), float(quat[3]))
                ng = ctrl._nav_goal
                d = None
                if ng is not None:
                    d = ((ng[0] - float(pos[0])) ** 2
                         + (ng[1] - float(pos[1])) ** 2) ** 0.5
                with open(_NAV_LOG, "a") as f:
                    f.write(
                        f"n={st['n']} step={getattr(ctrl,'_step_n',-1)} "
                        f"pos=[{float(pos[0]):.2f},{float(pos[1]):.2f},"
                        f"{float(pos[2]):.2f}] gravz={float(g[2]):.3f} "
                        f"navgoal={ng} "
                        f"dist={('%.2f' % d) if d is not None else 'None'}\n")
            else:
                with open(_NAV_LOG, "a") as f:
                    f.write(f"n={st['n']} (setup 대기...)\n")
        except Exception as exc:
            with open(_NAV_LOG, "a") as f:
                f.write(f"[log_err n={st['n']}] {exc!r}\n")


from omni.physx import get_physx_interface  # noqa: E402

_sub = get_physx_interface().subscribe_physics_step_events(_nav_step)
builtins._go2_nav_sub = _sub

import omni.timeline  # noqa: E402
_tl = omni.timeline.get_timeline_interface()
if not _tl.is_playing():
    _tl.play()

result = {"status": "injected", "mode": _mode,
          "latent_dim": _ctrl._latent_dim}
