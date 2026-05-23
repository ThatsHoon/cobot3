"""M1 §3: r0 의 3 bin (red, blue, reject) 생성.

prim paths:
  /World/Bins                    (Xform 컨테이너)
    ├── r0_bin_red               (Cube)
    ├── r0_bin_blue              (Cube)
    └── r0_bin_reject            (Cube)

각 bin:
- 40cm × 40cm × 10cm
- 컨베이어 옆 (y = -1.2 ~ -1.5)
- Static (RigidBody X, Collider 만)
"""
from pxr import UsdGeom, UsdPhysics, Gf
import omni.usd


BINS = [
    # (label, prim_path, x, y, z, color_rgb)
    ("red",    "/World/Bins/r0_bin_red",    -1.5, -1.2, 0.05, (0.9, 0.1, 0.1)),
    ("blue",   "/World/Bins/r0_bin_blue",   -1.5, -1.4, 0.05, (0.1, 0.1, 0.9)),
    ("reject", "/World/Bins/r0_bin_reject", -1.0, -1.4, 0.05, (0.5, 0.5, 0.5)),
]

BIN_W = 0.4   # X
BIN_D = 0.18  # Y (좁게 — 인접 bin 간 간격 확보)
BIN_H = 0.10  # Z


def run() -> str:
    stage = omni.usd.get_context().get_stage()

    # 컨테이너
    if not stage.GetPrimAtPath("/World/Bins").IsValid():
        UsdGeom.Xform.Define(stage, "/World/Bins")

    for label, path, x, y, z, color in BINS:
        prim = stage.GetPrimAtPath(path)
        if not prim.IsValid():
            cube = UsdGeom.Cube.Define(stage, path)
            cube.GetSizeAttr().Set(1.0)
            prim = cube.GetPrim()

        # transform
        xf = UsdGeom.Xformable(prim)
        xf.ClearXformOpOrder()
        xf.AddTranslateOp().Set(Gf.Vec3f(x, y, z))
        xf.AddScaleOp().Set(Gf.Vec3f(BIN_W, BIN_D, BIN_H))

        # static collider (RigidBody X)
        UsdPhysics.CollisionAPI.Apply(prim)

        # 색상 (display color)
        UsdGeom.Gprim(prim).CreateDisplayColorAttr().Set([Gf.Vec3f(*color)])

    return f"3 bins OK ({len(BINS)})"


if __name__ == "__main__":
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True})
    print(run())
    app.close()
