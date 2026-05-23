"""M1 §2: 컨베이어 메시 + kinematic + surface velocity.

cobot3 의 컨베이어:
- 길이 4m × 폭 0.5m × 두께 0.05m (시뮬용 단순 박스)
- 위치: y = -0.5 (로봇 base 앞쪽), z = 0.4 (지면 위 40cm)
- Surface velocity: (0.3, 0, 0) — +X 방향 0.3 m/s
- Kinematic body (실제로 회전 X, 표면만 마찰로 끎)

prim path:
  /World/Conveyor              (Xform)
    ├── belt                   (Cube, kinematic + surface vel)
    └── frame                  (Xform — 시각용, 옵션)
"""
from pxr import UsdGeom, UsdPhysics, PhysxSchema, Gf, Sdf
import omni.usd


# 디자인 doc 의 prim path 와 일치
BELT_PATH = "/World/Conveyor/belt"

BELT_LENGTH = 4.0      # +X 방향
BELT_WIDTH  = 0.5      # +Y 방향
BELT_HEIGHT = 0.05     # +Z 방향 두께
BELT_TOP_Z  = 0.4      # 벨트 상면 높이 (지면 위)

SURFACE_VELOCITY = (0.3, 0.0, 0.0)   # +X 0.3 m/s
DYNAMIC_FRICTION = 0.7
STATIC_FRICTION  = 0.8


def run() -> str:
    stage = omni.usd.get_context().get_stage()

    # /World/Conveyor 컨테이너
    if not stage.GetPrimAtPath("/World/Conveyor").IsValid():
        UsdGeom.Xform.Define(stage, "/World/Conveyor")

    # 1. belt mesh — Cube prim
    belt_prim = stage.GetPrimAtPath(BELT_PATH)
    if not belt_prim.IsValid():
        cube = UsdGeom.Cube.Define(stage, BELT_PATH)
        cube.GetSizeAttr().Set(1.0)
        belt_prim = cube.GetPrim()

    # Transform: scale 로 사이즈 + 위치
    xf = UsdGeom.Xformable(belt_prim)
    xf.ClearXformOpOrder()
    xf.AddTranslateOp().Set(Gf.Vec3f(0.0, -0.5, BELT_TOP_Z - BELT_HEIGHT / 2))
    xf.AddScaleOp().Set(Gf.Vec3f(BELT_LENGTH, BELT_WIDTH, BELT_HEIGHT))

    # 2. RigidBody (kinematic)
    rb_api = UsdPhysics.RigidBodyAPI.Apply(belt_prim)
    rb_api.CreateKinematicEnabledAttr().Set(True)
    rb_api.CreateRigidBodyEnabledAttr().Set(True)

    # 3. CollisionAPI
    UsdPhysics.CollisionAPI.Apply(belt_prim)

    # 4. Material (마찰 + restitution)
    mat_path = "/World/Conveyor/belt_material"
    mat_prim = stage.GetPrimAtPath(mat_path)
    if not mat_prim.IsValid():
        from pxr import UsdShade
        mat = UsdShade.Material.Define(stage, mat_path)
        mat_prim = mat.GetPrim()
    phys_mat = UsdPhysics.MaterialAPI.Apply(mat_prim)
    phys_mat.CreateDynamicFrictionAttr().Set(DYNAMIC_FRICTION)
    phys_mat.CreateStaticFrictionAttr().Set(STATIC_FRICTION)
    phys_mat.CreateRestitutionAttr().Set(0.05)

    # belt 에 material binding
    from pxr import UsdShade
    UsdShade.MaterialBindingAPI.Apply(belt_prim).Bind(
        UsdShade.Material.Get(stage, mat_path),
        bindingStrength=UsdShade.Tokens.weakerThanDescendants,
        materialPurpose="physics",
    )

    # 5. Surface velocity (PhysxSurfaceVelocity)
    sva = PhysxSchema.PhysxSurfaceVelocityAPI.Apply(belt_prim)
    sva.CreateSurfaceVelocityAttr().Set(Gf.Vec3f(*SURFACE_VELOCITY))
    sva.CreateSurfaceVelocityEnabledAttr().Set(True)

    return f"conveyor OK at {BELT_PATH}, surface_vel={SURFACE_VELOCITY}"


if __name__ == "__main__":
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True})
    print(run())
    app.close()
