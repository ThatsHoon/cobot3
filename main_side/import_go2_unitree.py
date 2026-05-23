"""Unitree go2.urdf → USD 임포트 (1회 실행).

walk-these-ways 정책이 실제 학습한 자산(Unitree go2.urdf, /tmp/wtw_go2)을
Isaac USD 로 임포트해 NVIDIA go2.usd 를 대체한다. NVIDIA go2.usd 는 기립은
되나 학습 컨벤션과 달라 보행 전이가 안 됨(검증). 학습 자산 일치가 목적.

실행: python.sh import_go2_unitree.py
출력: main_side/scene/go2_unitree/go2_unitree.usd
"""
import os

from isaacsim import SimulationApp

simulation_app = SimulationApp({"headless": True})

import omni.kit.commands
import omni.usd
from isaacsim.core.utils.extensions import enable_extension

enable_extension("isaacsim.asset.importer.urdf")
for _ in range(30):
    simulation_app.update()

_HERE = os.path.dirname(os.path.abspath(__file__))
URDF = os.path.join(_HERE, "scene", "go2_unitree", "urdf", "go2.urdf")
OUT = os.path.join(_HERE, "scene", "go2_unitree", "go2_unitree.usd")

print(f"[import] urdf={URDF}")
print(f"[import] out ={OUT}")

status, cfg = omni.kit.commands.execute("URDFCreateImportConfig")
# 학습 자산 충실 임포트:
cfg.merge_fixed_joints = False       # foot/calflower 고정관절 보존
cfg.convex_decomp = False            # 충돌 단순 convex hull (동적 바디)
cfg.import_inertia_tensor = True     # URDF 관성 텐서 사용
cfg.fix_base = False                 # go2_config: fix_base_link=False
cfg.self_collision = False           # go2 기본 (학습과 일치)
cfg.distance_scale = 1.0
cfg.make_default_prim = True         # ref 가능하도록 robot=defaultPrim
cfg.create_physics_scene = False     # 씬은 camera_publisher 가 제공

status, prim_path = omni.kit.commands.execute(
    "URDFParseAndImportFile",
    urdf_path=URDF,
    import_config=cfg,
    get_articulation_root=True,
)
print(f"[import] status={status} robot_prim={prim_path}")

stage = omni.usd.get_context().get_stage()
# 임포트된 로봇 prim 트리/관절 확인
from pxr import Usd, UsdPhysics

art_root = None
dofs = []
robot = stage.GetPrimAtPath(prim_path)
if robot and robot.IsValid():
    for p in Usd.PrimRange(robot):
        if p.HasAPI(UsdPhysics.ArticulationRootAPI) and art_root is None:
            art_root = str(p.GetPath())
        if p.GetTypeName() == "PhysicsRevoluteJoint":
            dofs.append(p.GetName())
print(f"[import] defaultPrim={stage.GetDefaultPrim().GetPath()}")
print(f"[import] articulation_root={art_root}")
print(f"[import] revolute_joints({len(dofs)})={sorted(dofs)}")

ok = stage.Export(OUT)
print(f"[import] Export({OUT}) = {ok}")
with open("/tmp/go2_import.txt", "w") as f:
    f.write(f"status={status} robot_prim={prim_path}\n")
    f.write(f"defaultPrim={stage.GetDefaultPrim().GetPath()}\n")
    f.write(f"articulation_root={art_root}\n")
    f.write(f"revolute_joints({len(dofs)})={sorted(dofs)}\n")
    f.write(f"export_ok={ok} out={OUT}\n")

simulation_app.close()
