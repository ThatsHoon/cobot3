"""M1 §6 (test): Spawn zone 에서 박스 1 개 생성 → 컨베이어 위에 떨어뜨림.

검증용:
- 박스가 중력으로 떨어져 벨트에 닿음
- 벨트 surface velocity (0.3, 0, 0) 로 +X 방향 이동
- r0 zone (x = -1.8 ~ -1.2) 진입 가능

prim path: /World/SpawnZone/test_box_<idx>
"""
from pxr import UsdGeom, UsdPhysics, Gf
import omni.usd
from omni.physx.scripts import utils as physx_utils


SPAWN_X = -1.8       # 컨베이어 시작 부근 (r0 zone 왼쪽)
SPAWN_Z = 0.7        # 벨트 위 30cm
BOX_SIZE = 0.08      # 8 cm cube


def run(label: str = "red", idx: int = 1) -> str:
    """단일 박스 spawn. label 은 r/g/b/yellow 등 시각 구분용."""
    stage = omni.usd.get_context().get_stage()

    if not stage.GetPrimAtPath("/World/SpawnZone").IsValid():
        UsdGeom.Xform.Define(stage, "/World/SpawnZone")

    box_path = f"/World/SpawnZone/test_box_{label}_{idx}"
    prim = stage.GetPrimAtPath(box_path)
    if not prim.IsValid():
        cube = UsdGeom.Cube.Define(stage, box_path)
        cube.GetSizeAttr().Set(1.0)
        prim = cube.GetPrim()

    xf = UsdGeom.Xformable(prim)
    xf.ClearXformOpOrder()
    xf.AddTranslateOp().Set(Gf.Vec3f(SPAWN_X, -0.5, SPAWN_Z))
    xf.AddScaleOp().Set(Gf.Vec3f(BOX_SIZE, BOX_SIZE, BOX_SIZE))

    # 색
    color_map = {
        "red":   (0.9, 0.1, 0.1),
        "blue":  (0.1, 0.1, 0.9),
        "green": (0.1, 0.9, 0.1),
        "yellow":(0.9, 0.9, 0.1),
    }
    rgb = color_map.get(label, (0.7, 0.7, 0.7))
    UsdGeom.Gprim(prim).CreateDisplayColorAttr().Set([Gf.Vec3f(*rgb)])

    # Rigid Body + Collider preset (convex hull, 0.1 kg)
    physx_utils.setRigidBody(prim, approximationShape="convexHull", kinematic=False)
    mass_api = UsdPhysics.MassAPI.Apply(prim)
    mass_api.CreateMassAttr().Set(0.1)   # 100 g

    return f"box {label}#{idx} spawned at ({SPAWN_X}, -0.5, {SPAWN_Z})"


if __name__ == "__main__":
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True})
    print(run("red", 1))
    app.close()
