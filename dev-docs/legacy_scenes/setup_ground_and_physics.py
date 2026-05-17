"""M1 §1: PhysicsScene + GroundPlane 셋업.

호출:
- MCP: execute_script 안에서 `from scenes import setup_ground_and_physics; setup_ground_and_physics.run()`
- standalone: `python.sh -m scenes.setup_ground_and_physics`
"""
from pxr import UsdPhysics, PhysxSchema, Gf, UsdGeom
import omni.usd


def run() -> str:
    stage = omni.usd.get_context().get_stage()

    # /World 가 없으면 생성
    world = stage.GetPrimAtPath("/World")
    if not world.IsValid():
        UsdGeom.Xform.Define(stage, "/World")
        stage.SetDefaultPrim(stage.GetPrimAtPath("/World"))

    # PhysicsScene
    scene_path = "/physicsScene"
    scene_prim = stage.GetPrimAtPath(scene_path)
    if not scene_prim.IsValid():
        scene = UsdPhysics.Scene.Define(stage, scene_path)
        scene.CreateGravityDirectionAttr().Set(Gf.Vec3f(0.0, 0.0, -1.0))
        scene.CreateGravityMagnitudeAttr().Set(9.81)

        physx_scene = PhysxSchema.PhysxSceneAPI.Apply(stage.GetPrimAtPath(scene_path))
        physx_scene.CreateTimeStepsPerSecondAttr().Set(60)
        physx_scene.CreateSolverTypeAttr().Set("TGS")
        physx_scene.CreateEnableCCDAttr().Set(True)
        physx_scene.CreateEnableGPUDynamicsAttr().Set(True)
        physx_scene.CreateBroadphaseTypeAttr().Set("GPU")

    # GroundPlane — Isaac core helper 사용
    try:
        from isaacsim.core.api.objects.ground_plane import GroundPlane
        gp = GroundPlane(prim_path="/World/GroundPlane", z_position=0.0)
    except ImportError:
        # core.api 사용 불가 시 raw USD 로 fallback
        if not stage.GetPrimAtPath("/World/GroundPlane").IsValid():
            UsdGeom.Xform.Define(stage, "/World/GroundPlane")
            # 큰 박스를 ground 로 — 5m × 5m × 0.01m
            box = UsdGeom.Cube.Define(stage, "/World/GroundPlane/cube")
            box.GetSizeAttr().Set(1.0)
            xf = UsdGeom.Xformable(box.GetPrim())
            xf.AddScaleOp().Set(Gf.Vec3f(5.0, 5.0, 0.01))
            xf.AddTranslateOp().Set(Gf.Vec3f(0, 0, -0.005))
            UsdPhysics.CollisionAPI.Apply(box.GetPrim())

    return "ground+physics OK"


if __name__ == "__main__":
    # standalone 모드: SimulationApp 띄우고 실행 후 종료
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True})
    print(run())
    app.close()
