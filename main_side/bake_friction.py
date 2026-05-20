"""지형/발 접지 마찰을 USD 파일에 영구 저장(베이크).

런타임(camera_publisher)에서만 바인딩하던 physics material(마찰 0.8)을
gp_scene.usd(지형 collider) + go2_unitree.usd(발/다리 collider)에 직접
기록·저장한다. 1회 실행. 이후 파일 자체에 마찰이 영구 존재.

실행: python.sh bake_friction.py
"""
import os

from isaacsim import SimulationApp

simulation_app = SimulationApp({"headless": True})

import omni.usd  # noqa: E402
from pxr import Usd, UsdPhysics, UsdShade  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
SCENE = os.path.join(_HERE, "scene", "gp_scene.usd")
GO2 = os.path.join(_HERE, "go2_unitree", "go2_unitree.usd")
PM_PATH = "/World/Physics_Materials/physics_material"
GO2_PM_PATH = "/go2_description/Physics_Materials/foot_material"


def _ensure_mat(stage, path, sf=0.8, df=0.8, rest=0.0):
    prim = stage.GetPrimAtPath(path)
    if not (prim and prim.IsValid()):
        UsdShade.Material.Define(stage, path)
        prim = stage.GetPrimAtPath(path)
    if not prim.HasAPI(UsdPhysics.MaterialAPI):
        UsdPhysics.MaterialAPI.Apply(prim)
    m = UsdPhysics.MaterialAPI(prim)
    m.CreateStaticFrictionAttr(sf)
    m.CreateDynamicFrictionAttr(df)
    m.CreateRestitutionAttr(rest)
    return UsdShade.Material(prim)


def _bind(prim, mat):
    UsdShade.MaterialBindingAPI.Apply(prim)
    UsdShade.MaterialBindingAPI(prim).Bind(
        mat, bindingStrength=UsdShade.Tokens.weakerThanDescendants,
        materialPurpose="physics")


# ── 1. gp_scene.usd : 지형 collider 마찰 베이크 ──────────────────────
ctx = omni.usd.get_context()
ctx.open_stage(SCENE)
st = ctx.get_stage()
mat = _ensure_mat(st, PM_PATH, 0.8, 0.8, 0.0)
nb = 0
for p in st.Traverse():
    if not p.HasAPI(UsdPhysics.CollisionAPI):
        continue
    pp = str(p.GetPath())
    if pp.startswith("/World/Terrain") or "GP_NoiseTerrain" in pp:
        _bind(p, mat)
        nb += 1
gnt = st.GetPrimAtPath("/World/Xform_01/GP_NoiseTerrain")
if gnt and gnt.IsValid() and not gnt.HasAPI(UsdPhysics.CollisionAPI):
    UsdPhysics.CollisionAPI.Apply(gnt)
    UsdPhysics.MeshCollisionAPI.Apply(gnt).CreateApproximationAttr("none")
    _bind(gnt, mat)
    nb += 1
ok1 = st.GetRootLayer().Export(SCENE)
print(f"[bake] gp_scene.usd: terrain collider {nb}개 마찰0.8 바인딩, "
      f"save={ok1}")

# ── 2. go2_unitree.usd : 발/다리 collider 마찰 베이크 ────────────────
ctx.open_stage(GO2)
st2 = ctx.get_stage()
mat2 = _ensure_mat(st2, GO2_PM_PATH, 0.8, 0.8, 0.0)
ng = 0
for p in st2.Traverse():
    if not p.HasAPI(UsdPhysics.CollisionAPI):
        continue
    pp = str(p.GetPath()).lower()
    if any(k in pp for k in ("foot", "calf", "thigh", "hip", "base")):
        _bind(p, mat2)
        ng += 1
ok2 = st2.GetRootLayer().Export(GO2)
print(f"[bake] go2_unitree.usd: 발/다리 collider {ng}개 마찰0.8 바인딩, "
      f"save={ok2}")

with open("/tmp/go2_bake.txt", "w") as f:
    f.write(f"gp_scene terrain_bind={nb} save={ok1}\n")
    f.write(f"go2_unitree leg_bind={ng} save={ok2}\n")

simulation_app.close()
