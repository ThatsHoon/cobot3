"""M2 §1: RGB-D 카메라 (overhead) 셋업.

r0 zone 상공 2m 에 카메라 배치. focal 24mm + aperture 20.955mm 로 1280x720 영상.

prim path: /World/Cameras/r0_overhead

K 행렬:
  fx = 24 / 20.955 * 1280 ≈ 1466.3
  fy = 24 / 11.787 * 720  ≈ 1466.3
  cx = 640, cy = 360
"""
from pxr import UsdGeom, Gf
import omni.usd


# r0 zone 상공 2m, 컨베이어 중심 위
CAMERAS = [
    # (robot_id, prim_path, position(x,y,z), rotation(rx,ry,rz) degrees)
    ("r0", "/World/Cameras/r0_overhead", (-1.5, -0.5, 2.0), (0, -90, 0)),
]

FOCAL_MM       = 24.0
H_APERTURE_MM  = 20.955
V_APERTURE_MM  = 11.787
WIDTH_PX       = 1280
HEIGHT_PX      = 720
CLIP_NEAR      = 0.1
CLIP_FAR       = 10.0


def run() -> str:
    stage = omni.usd.get_context().get_stage()

    if not stage.GetPrimAtPath("/World/Cameras").IsValid():
        UsdGeom.Xform.Define(stage, "/World/Cameras")

    created = []
    for rid, path, pos, rot in CAMERAS:
        cam_prim = stage.GetPrimAtPath(path)
        if not cam_prim.IsValid():
            cam = UsdGeom.Camera.Define(stage, path)
            cam_prim = cam.GetPrim()
        else:
            cam = UsdGeom.Camera(cam_prim)

        # Intrinsics
        cam.GetFocalLengthAttr().Set(FOCAL_MM)
        cam.GetHorizontalApertureAttr().Set(H_APERTURE_MM)
        cam.GetVerticalApertureAttr().Set(V_APERTURE_MM)
        cam.GetClippingRangeAttr().Set(Gf.Vec2f(CLIP_NEAR, CLIP_FAR))

        # Transform
        xf = UsdGeom.Xformable(cam_prim)
        xf.ClearXformOpOrder()
        xf.AddTranslateOp().Set(Gf.Vec3f(*pos))
        xf.AddRotateXYZOp().Set(Gf.Vec3f(*rot))

        created.append(rid)

    return f"cameras OK: {created}"


if __name__ == "__main__":
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True})
    print(run())
    app.close()
