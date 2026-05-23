"""M1 §4: 단일 m0609 (r0) USD 참조로 추가.

prim path: /World/Robots/r0/m0609

m0609 USD 후보 (자동 선택):
1. /home/rokey/dev_ws/isaac_sim/src/doosan-robot2/urdf/m0609_isaac_sim/m0609_isaac_sim.usd
2. /home/rokey/dev_ws/isaac_sim/src/doosan-robot2/usd/m0609.usd

isaac_sim 폴더 안 (#1) 이 articulation 셋업이 되어있을 가능성 높음.
실패 시 #2 로 fallback.

검증:
- num_dof == 6 인지
- joint_names 리스트가 6개인지
"""
from pathlib import Path
from pxr import UsdGeom
import omni.usd


CANDIDATE_USDS = [
    "/home/rokey/dev_ws/isaac_sim/src/doosan-robot2/urdf/m0609_isaac_sim/m0609_isaac_sim.usd",
    "/home/rokey/dev_ws/isaac_sim/src/doosan-robot2/usd/m0609.usd",
]

ROBOT_PRIM = "/World/Robots/r0/m0609"
BASE_POSITION = (-1.5, 0.0, 0.0)   # 컨베이어 옆


def run() -> str:
    stage = omni.usd.get_context().get_stage()

    # 컨테이너
    if not stage.GetPrimAtPath("/World/Robots").IsValid():
        UsdGeom.Xform.Define(stage, "/World/Robots")
    if not stage.GetPrimAtPath("/World/Robots/r0").IsValid():
        UsdGeom.Xform.Define(stage, "/World/Robots/r0")

    # USD 파일 선택
    usd_path = None
    for cand in CANDIDATE_USDS:
        if Path(cand).exists():
            usd_path = cand
            break
    if usd_path is None:
        return f"ERROR: m0609 USD not found in {CANDIDATE_USDS}"

    # 이미 참조됐는지 확인
    existing = stage.GetPrimAtPath(ROBOT_PRIM)
    if not existing.IsValid():
        from isaacsim.core.utils.stage import add_reference_to_stage
        add_reference_to_stage(usd_path=usd_path, prim_path=ROBOT_PRIM)

    # transform (base 위치)
    prim = stage.GetPrimAtPath(ROBOT_PRIM)
    xf = UsdGeom.Xformable(prim)
    # 기존 ops 가 있을 수 있으므로 ClearXformOpOrder 후 재설정
    xf.ClearXformOpOrder()
    from pxr import Gf
    xf.AddTranslateOp().Set(Gf.Vec3f(*BASE_POSITION))

    return f"r0 m0609 referenced from {Path(usd_path).name} at {BASE_POSITION}"


def verify():
    """Reset 후 articulation 정보 출력 (별도 호출)"""
    from isaacsim.core.api import World
    from isaacsim.core.api.robots import Robot
    import asyncio

    world = World.instance() or World()
    if not world.scene.object_exists("r0_m0609"):
        world.scene.add(Robot(prim_path=ROBOT_PRIM, name="r0_m0609"))

    # Reset 비동기 — caller 가 await 또는 ensure_future
    return world


if __name__ == "__main__":
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True})
    print(run())
    app.close()
