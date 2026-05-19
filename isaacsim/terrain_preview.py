"""
Terrain-only viewer — no robot, no physics, no ROS 2.
GPU 사용량을 최소화하면서 DMZ 경계 지형만 미리보기.
"""

from isaacsim import SimulationApp

simulation_app = SimulationApp({
    "headless": False,
    "renderer": "RayTracedLighting",   # PathTracing 보다 GPU 절약
    "anti_aliasing": 1,                # 0=off, 1=FXAA(가벼움), 3=DLSS
})

import argparse
from pathlib import Path

import numpy as np
import omni
import omni.client
import carb
from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade
from isaacsim.core.utils.stage import add_reference_to_stage
from isaacsim.core.utils.semantics import add_labels

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GUARD_TOWER_ASSET = PROJECT_ROOT / "assets/props/guard_tower/Guard_Tower_Free_Asset.usdz"
DEFAULT_CHAINLINK_FENCE_ASSET = PROJECT_ROOT / "assets/props/chainlink_fence/chainlink_fence_tileable.usdz"

# ---------------------------------------------------------------------------
# 수치 유틸
# ---------------------------------------------------------------------------

def _smoothstep(v):
    v = np.clip(v, 0.0, 1.0)
    return v * v * (3.0 - 2.0 * v)


def _bilinear_resample(coarse, samples):
    cy = np.linspace(0.0, samples - 1, coarse.shape[0])
    cx = np.linspace(0.0, samples - 1, coarse.shape[1])
    t = np.arange(samples)
    rows = np.array([np.interp(t, cx, row) for row in coarse])
    return np.array([np.interp(t, cy, rows[:, c]) for c in range(samples)]).T


def _get_fence_y(size, fence_y):
    return float(np.clip(fence_y, -size * 0.15, size * 0.35))


def _generate_heightfield(size, resolution, amplitude, seed, fence_y):
    samples = max(9, int(round(size / resolution)) + 1)
    if samples % 2 == 0:
        samples += 1
    x_values = np.linspace(-size * 0.5, size * 0.5, samples)
    y_values = np.linspace(-size * 0.5, size * 0.5, samples)
    xx, yy = np.meshgrid(x_values, y_values)
    rng = np.random.default_rng(seed)
    ds = max(9, samples // 5)
    detail = _bilinear_resample(rng.uniform(-1.0, 1.0, size=(ds, ds)), samples)
    fence_y = _get_fence_y(size, fence_y)
    fence_band = np.exp(-((yy - fence_y) / 5.5) ** 2)
    interior_falloff = 1.0 - _smoothstep((yy - (fence_y - 11.0)) / 7.0)
    interior_micro = interior_falloff * (0.012 * detail + 0.008 * np.sin(0.23 * xx))
    berm = 0.65 * amplitude * np.exp(-((yy - (fence_y - 1.1)) / 1.3) ** 2)
    ditch = -0.38 * amplitude * np.exp(-((yy - (fence_y + 1.3)) / 1.6) ** 2)
    fence_noise = 0.35 * amplitude * detail * fence_band
    river_drop = -0.42 * _smoothstep((yy - (fence_y + 3.2)) / 8.0)
    patrol = np.exp(-(yy / 5.5) ** 2)
    heights = interior_micro + berm + ditch + fence_noise + river_drop
    heights *= 1.0 - 0.65 * patrol
    ci = samples // 2
    heights -= heights[ci, ci]
    r = np.sqrt(xx * xx + yy * yy)
    heights *= _smoothstep((r - 2.3) / 2.5)
    heights[ci, ci] = 0.0
    return x_values, y_values, heights


def _sample_height(x_values, y_values, heights, x, y):
    x = float(np.clip(x, x_values[0], x_values[-1]))
    y = float(np.clip(y, y_values[0], y_values[-1]))
    col = int(np.clip(np.searchsorted(x_values, x) - 1, 0, len(x_values) - 2))
    row = int(np.clip(np.searchsorted(y_values, y) - 1, 0, len(y_values) - 2))
    x0, x1 = x_values[col], x_values[col + 1]
    y0, y1 = y_values[row], y_values[row + 1]
    tx = 0.0 if x1 == x0 else (x - x0) / (x1 - x0)
    ty = 0.0 if y1 == y0 else (y - y0) / (y1 - y0)
    h00, h10 = heights[row, col], heights[row, col + 1]
    h01, h11 = heights[row + 1, col], heights[row + 1, col + 1]
    return float((1-tx)*(1-ty)*h00 + tx*(1-ty)*h10 + (1-tx)*ty*h01 + tx*ty*h11)

# ---------------------------------------------------------------------------
# USD 유틸
# ---------------------------------------------------------------------------

def _set_xform(prim, translate, scale=None, rotate_xyz=None):
    xf = UsdGeom.Xformable(prim)
    xf.AddTranslateOp().Set(Gf.Vec3f(*translate))
    if rotate_xyz is not None:
        xf.AddRotateXYZOp().Set(Gf.Vec3f(*rotate_xyz))
    if scale is not None:
        xf.AddScaleOp().Set(Gf.Vec3f(*scale))


def _set_display_color(gprim, color):
    gprim.CreateDisplayColorAttr([Gf.Vec3f(*color)])


def _enable_static_collision(prim):
    if not prim.HasAPI(UsdPhysics.CollisionAPI):
        api = UsdPhysics.CollisionAPI.Apply(prim)
    else:
        api = UsdPhysics.CollisionAPI(prim)
    api.CreateCollisionEnabledAttr(True)


def _apply_class_label(prim, label):
    add_labels(prim, [label], instance_name="class")


def _add_cube(stage, path, center, scale, color, rotate_xyz=None):
    cube = UsdGeom.Cube.Define(stage, Sdf.Path(path))
    cube.CreateSizeAttr(1.0)
    _set_xform(cube.GetPrim(), center, scale, rotate_xyz)
    _set_display_color(cube, color)
    _enable_static_collision(cube.GetPrim())
    return cube.GetPrim()


def _add_cylinder(stage, path, center, radius, height, color):
    cyl = UsdGeom.Cylinder.Define(stage, Sdf.Path(path))
    cyl.CreateRadiusAttr(radius)
    cyl.CreateHeightAttr(height)
    _set_xform(cyl.GetPrim(), center)
    _set_display_color(cyl, color)
    _enable_static_collision(cyl.GetPrim())
    return cyl.GetPrim()


def _add_visual_cube(stage, path, center, scale, color, label=None, rotate_xyz=None):
    cube = UsdGeom.Cube.Define(stage, Sdf.Path(path))
    cube.CreateSizeAttr(1.0)
    _set_xform(cube.GetPrim(), center, scale, rotate_xyz)
    _set_display_color(cube, color)
    if label:
        _apply_class_label(cube.GetPrim(), label)
    return cube.GetPrim()


def _add_visual_cylinder(stage, path, center, radius, height, color, label=None):
    cyl = UsdGeom.Cylinder.Define(stage, Sdf.Path(path))
    cyl.CreateRadiusAttr(radius)
    cyl.CreateHeightAttr(height)
    _set_xform(cyl.GetPrim(), center)
    _set_display_color(cyl, color)
    if label:
        _apply_class_label(cyl.GetPrim(), label)
    return cyl.GetPrim()


def _add_visual_sphere(stage, path, center, radius, color, label=None):
    sp = UsdGeom.Sphere.Define(stage, Sdf.Path(path))
    sp.CreateRadiusAttr(radius)
    _set_xform(sp.GetPrim(), center)
    _set_display_color(sp, color)
    if label:
        _apply_class_label(sp.GetPrim(), label)
    return sp.GetPrim()


def _add_curve_lines(stage, path, lines, width, color):
    points, counts = [], []
    for line in lines:
        counts.append(len(line))
        points.extend([Gf.Vec3f(*p) for p in line])
    curves = UsdGeom.BasisCurves.Define(stage, Sdf.Path(path))
    curves.CreateTypeAttr(UsdGeom.Tokens.linear)
    curves.CreateCurveVertexCountsAttr(counts)
    curves.CreatePointsAttr(points)
    curves.CreateWidthsAttr([width])
    curves.CreateDisplayColorAttr([Gf.Vec3f(*color)])


def _add_sphere_light(stage, path, center, radius, intensity, color):
    light = UsdLux.SphereLight.Define(stage, Sdf.Path(path))
    light.CreateRadiusAttr(radius)
    light.CreateIntensityAttr(intensity)
    light.CreateColorAttr(Gf.Vec3f(*color))
    _set_xform(light.GetPrim(), center)


def _label_prim_tree(prim, label):
    for child in Usd.PrimRange(prim):
        _apply_class_label(child, label)

# ---------------------------------------------------------------------------
# 지형 텍스처 / 그리드
# ---------------------------------------------------------------------------

def _add_terrain_uvs(mesh, x_values, y_values, texture_scale):
    x_min, x_range = float(x_values[0]), float(x_values[-1] - x_values[0])
    y_min, y_range = float(y_values[0]), float(y_values[-1] - y_values[0])
    ts = max(0.001, float(texture_scale))
    texcoords = [
        Gf.Vec2f((x - x_min) / x_range * ts, (y - y_min) / y_range * ts)
        for y in y_values for x in x_values
    ]
    pv = UsdGeom.PrimvarsAPI(mesh.GetPrim())
    st = pv.CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex)
    st.Set(texcoords)


def _bind_terrain_texture(stage, terrain_prim, texture_path, normal_path, roughness_path):
    if not any([texture_path, normal_path, roughness_path]):
        return
    mat = UsdShade.Material.Define(stage, Sdf.Path("/World/Looks/GP_TerrainPBRMaterial"))
    shader = UsdShade.Shader.Define(stage, Sdf.Path("/World/Looks/GP_TerrainPBRMaterial/PreviewSurface"))
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.92)
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.17, 0.18, 0.12))
    st_reader = UsdShade.Shader.Define(stage, Sdf.Path("/World/Looks/GP_TerrainPBRMaterial/StReader"))
    st_reader.CreateIdAttr("UsdPrimvarReader_float2")
    st_reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")

    def _tex_node(name, file_path):
        t = UsdShade.Shader.Define(stage, Sdf.Path(f"/World/Looks/GP_TerrainPBRMaterial/{name}"))
        t.CreateIdAttr("UsdUVTexture")
        t.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(file_path))
        t.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(st_reader.ConnectableAPI(), "result")
        t.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("repeat")
        t.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("repeat")
        return t

    if texture_path:
        t = _tex_node("AlbedoTexture", texture_path)
        t.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(t.ConnectableAPI(), "rgb")
    if roughness_path:
        t = _tex_node("RoughnessTexture", roughness_path)
        t.CreateOutput("r", Sdf.ValueTypeNames.Float)
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).ConnectToSource(t.ConnectableAPI(), "r")
    if normal_path:
        t = _tex_node("NormalTexture", normal_path)
        t.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
        shader.CreateInput("normal", Sdf.ValueTypeNames.Normal3f).ConnectToSource(t.ConnectableAPI(), "rgb")

    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    UsdShade.MaterialBindingAPI.Apply(terrain_prim).Bind(mat)


def _add_terrain_grid(stage, x_values, y_values, heights, grid_step):
    if grid_step <= 0.0:
        return
    resolution = float(abs(x_values[1] - x_values[0]))
    stride = max(1, int(round(grid_step / resolution)))
    samples = heights.shape[0]
    points, counts = [], []
    for row in range(0, samples, stride):
        counts.append(samples)
        for col in range(samples):
            points.append(Gf.Vec3f(float(x_values[col]), float(y_values[row]), float(heights[row, col] + 0.012)))
    for col in range(0, samples, stride):
        counts.append(samples)
        for row in range(samples):
            points.append(Gf.Vec3f(float(x_values[col]), float(y_values[row]), float(heights[row, col] + 0.012)))
    curves = UsdGeom.BasisCurves.Define(stage, Sdf.Path("/World/GP_TerrainGrid"))
    curves.CreateTypeAttr(UsdGeom.Tokens.linear)
    curves.CreateCurveVertexCountsAttr(counts)
    curves.CreatePointsAttr(points)
    curves.CreateWidthsAttr([0.018])
    curves.CreateDisplayColorAttr([Gf.Vec3f(0.035, 0.045, 0.03)])

# ---------------------------------------------------------------------------
# 씬 구성 요소
# ---------------------------------------------------------------------------

def _add_concertina_wire(stage, path, x_values, y_values, heights, x_min, x_max,
                          center_y, center_z_offset, radius, loops, width, color):
    points = []
    n = max(80, loops * 18)
    for i, x in enumerate(np.linspace(x_min, x_max, n)):
        angle = 2.0 * np.pi * loops * i / max(1, n - 1)
        gz = _sample_height(x_values, y_values, heights, x, center_y)
        y = center_y + radius * np.cos(angle)
        z = gz + center_z_offset + radius * np.sin(angle)
        points.append((float(x), float(y), float(z)))
    _add_curve_lines(stage, path, [points], width=width, color=color)


def _add_river(stage, x_values, y_values, heights, terrain_size, fence_y, river_width):
    stage.DefinePrim("/World/GP_River", "Xform")
    rw = max(4.0, min(river_width, terrain_size * 0.38))
    river_start_y = fence_y + 5.0
    river_center_y = min(terrain_size * 0.5 - rw * 0.5 - 0.4, river_start_y + rw * 0.5)
    river_z = _sample_height(x_values, y_values, heights, 0.0, min(y_values[-1], river_start_y + 1.0)) + 0.035
    _add_cube(stage, "/World/GP_River/Water",
              (0.0, river_center_y, river_z), (terrain_size * 0.92, rw, 0.035), (0.05, 0.19, 0.30))
    _add_cube(stage, "/World/GP_River/FarBank",
              (0.0, river_center_y + rw * 0.5 + 0.8, river_z + 0.12),
              (terrain_size * 0.92, 1.2, 0.24), (0.12, 0.18, 0.10))


def _add_ground_surface_variation(stage, x_values, y_values, heights, terrain_size, fence_y):
    rng = np.random.default_rng(20260517)
    stage.DefinePrim("/World/GP_GroundDetail", "Xform")
    xl = terrain_size * 0.43
    iy_min, iy_max = -terrain_size * 0.42, fence_y - 1.5
    fy_max = fence_y + 2.8
    dirt   = ((0.19,0.16,0.10),(0.23,0.19,0.12),(0.15,0.13,0.09),(0.27,0.23,0.15))
    grass  = ((0.11,0.16,0.07),(0.15,0.20,0.08),(0.08,0.13,0.06),(0.20,0.22,0.10))
    gravel = ((0.28,0.27,0.24),(0.20,0.20,0.18),(0.35,0.33,0.29))
    for i in range(34):
        x = float(rng.uniform(-xl, xl)); y = float(rng.uniform(iy_min, fy_max))
        if abs(y) < 3.2 and abs(x) < 8.0: y += 5.5
        z = _sample_height(x_values, y_values, heights, x, y)
        _add_visual_cube(stage, f"/World/GP_GroundDetail/BareSoilPatch_{i}",
            (x, y, z+0.018), (float(rng.uniform(1.4,4.8)), float(rng.uniform(0.7,2.4)), 0.018),
            dirt[i%len(dirt)], rotate_xyz=(0,0,float(rng.uniform(-35,35))))
    for i in range(24):
        x = float(rng.uniform(-xl, xl)); y = float(rng.uniform(iy_min, iy_max))
        z = _sample_height(x_values, y_values, heights, x, y)
        _add_visual_cube(stage, f"/World/GP_GroundDetail/GravelPatch_{i}",
            (x, y, z+0.024),
            (float(rng.uniform(0.45,1.2)), float(rng.uniform(0.25,0.75)), 0.020),
            gravel[i%len(gravel)], rotate_xyz=(0,0,float(rng.uniform(-45,45))))
    for i in range(72):
        x = float(rng.uniform(-xl, xl)); y = float(rng.uniform(iy_min, fence_y+3.0))
        if -6.5 < y < -3.4: continue
        z = _sample_height(x_values, y_values, heights, x, y)
        h = float(rng.uniform(0.12, 0.42))
        _add_visual_cube(stage, f"/World/GP_GroundDetail/GrassClump_{i}",
            (x, y, z+h*0.5),
            (float(rng.uniform(0.06,0.14)), float(rng.uniform(0.04,0.10)), h),
            grass[i%len(grass)],
            rotate_xyz=(float(rng.uniform(-6,6)), float(rng.uniform(-5,5)), float(rng.uniform(0,180))))


def _add_gp_props(stage, x_values, y_values, heights, terrain_size, fence_y, river_width, skip_watchtowers=False):
    stage.DefinePrim("/World/GP_Props", "Xform")
    fence_y = _get_fence_y(terrain_size, fence_y)
    x_min, x_max = -terrain_size * 0.44, terrain_size * 0.44
    post_spacing = 3.5
    main_post_height = 2.55
    wire_lines = []
    for fname, fy, ph, radius, color in [
        ("Main",  fence_y,       main_post_height, 0.055, (0.10,0.12,0.10)),
        ("Inner", fence_y - 2.4, 1.55,             0.045, (0.12,0.12,0.10)),
    ]:
        for pi, x in enumerate(np.arange(x_min, x_max + 0.001, post_spacing)):
            z = _sample_height(x_values, y_values, heights, x, fy)
            _add_cylinder(stage, f"/World/GP_Props/Fence_{fname}_Post_{pi}",
                          (float(x), float(fy), z + ph * 0.5), radius, ph, color)
        whs = (0.65,1.15,1.65,2.15) if fname == "Main" else (0.55,1.05,1.42)
        for wh in whs:
            line = []
            for x in np.linspace(x_min, x_max, 80):
                z = _sample_height(x_values, y_values, heights, x, fy)
                line.append((float(x), float(fy), z + wh))
            wire_lines.append(line)
    _add_curve_lines(stage, "/World/GP_Props/FenceWires", wire_lines, 0.025, (0.05,0.06,0.05))
    mesh_lines = []
    for mi, x in enumerate(np.arange(x_min, x_max - post_spacing, post_spacing)):
        for bh, th in ((0.55,1.15),(1.15,1.75),(1.75,2.25)):
            z0 = _sample_height(x_values, y_values, heights, x, fence_y)
            z1 = _sample_height(x_values, y_values, heights, x + post_spacing, fence_y)
            if mi % 2 == 0:
                mesh_lines.append(((float(x), float(fence_y-0.015), z0+bh), (float(x+post_spacing), float(fence_y-0.015), z1+th)))
            else:
                mesh_lines.append(((float(x), float(fence_y-0.015), z0+th), (float(x+post_spacing), float(fence_y-0.015), z1+bh)))
    _add_curve_lines(stage, "/World/GP_Props/FenceDiamondMesh", mesh_lines, 0.012, (0.035,0.045,0.035))
    for cpath, cy, czo, cr, cl, cw, cc in [
        ("/World/GP_Props/MainFenceTopConcertina",     fence_y,       2.35, 0.23, 34, 0.025, (0.055,0.065,0.055)),
        ("/World/GP_Props/RiverSideGroundConcertina",  fence_y+1.55,  0.35, 0.28, 32, 0.023, (0.055,0.060,0.052)),
        ("/World/GP_Props/InteriorGroundConcertina",   fence_y-3.15,  0.30, 0.22, 28, 0.021, (0.065,0.060,0.050)),
    ]:
        _add_concertina_wire(stage, cpath, x_values, y_values, heights, x_min, x_max, cy, czo, cr, cl, cw, cc)
    for ri, (rname, ry, rh, rt, rc) in enumerate([
        ("Main",    fence_y,      1.15, 0.12, (0.06,0.075,0.06)),
        ("MainTop", fence_y,      1.95, 0.08, (0.06,0.075,0.06)),
        ("Inner",   fence_y-2.4,  0.95, 0.10, (0.075,0.075,0.06)),
    ]):
        rz = _sample_height(x_values, y_values, heights, 0.0, ry) + rh
        _add_cube(stage, f"/World/GP_Props/Fence_{rname}_CollisionRail_{ri}",
                  (0.0, ry, rz), (x_max-x_min, rt, rt), rc)
    road_cy = fence_y - 5.0
    road_z = _sample_height(x_values, y_values, heights, 0.0, road_cy) + 0.018
    _add_visual_cube(stage, "/World/GP_Props/PatrolRoadPackedSoil",
                     (0.0, road_cy, road_z), (x_max-x_min, 2.0, 0.018), (0.18,0.15,0.10))
    srl = []
    for ro in (-4.1, -5.7):
        line = []
        for x in np.linspace(x_min, x_max, 90):
            z = _sample_height(x_values, y_values, heights, x, fence_y + ro)
            line.append((float(x), float(fence_y + ro), z + 0.025))
        srl.append(line)
    _add_curve_lines(stage, "/World/GP_Props/FenceServiceRoadEdges", srl, 0.12, (0.22,0.18,0.11))
    if not skip_watchtowers:
        for ti, tx in enumerate((-terrain_size * 0.30, terrain_size * 0.30)):
            ty = fence_y - 4.8
            tz = _sample_height(x_values, y_values, heights, tx, ty)
            for li, (dx, dy) in enumerate(((-0.8,-0.8),(0.8,-0.8),(-0.8,0.8),(0.8,0.8))):
                _add_cube(stage, f"/World/GP_Props/Watchtower_{ti}_Leg_{li}",
                          (tx+dx, ty+dy, tz+1.75), (0.12,0.12,3.5), (0.16,0.12,0.08))
            _add_cube(stage, f"/World/GP_Props/Watchtower_{ti}_Platform", (tx,ty,tz+3.35),(2.25,2.25,0.18),(0.18,0.15,0.10))
            _add_cube(stage, f"/World/GP_Props/Watchtower_{ti}_Cabin",    (tx,ty,tz+4.10),(1.75,1.55,1.15),(0.25,0.29,0.19))
            _add_cube(stage, f"/World/GP_Props/Watchtower_{ti}_Roof",     (tx,ty,tz+4.78),(2.25,1.95,0.18),(0.09,0.10,0.08))
            _add_cube(stage, f"/World/GP_Props/Watchtower_{ti}_SearchLightHousing",
                      (tx, ty+0.95, tz+4.42), (0.42,0.22,0.22), (0.04,0.045,0.04))
            _add_sphere_light(stage, f"/World/GP_Props/Watchtower_{ti}_SearchLight",
                              (tx, ty+1.08, tz+4.42), 0.16, 2200.0, (1.0,0.86,0.60))
    for bi, bx in enumerate((-terrain_size*0.16, terrain_size*0.08, terrain_size*0.24)):
        by = fence_y - 7.2 - 1.0*(bi%2)
        bz = _sample_height(x_values, y_values, heights, bx, by)
        _add_cube(stage, f"/World/GP_Props/Bunker_{bi}_Body",  (bx,by,bz+0.70),(3.6,2.4,1.4),(0.23,0.24,0.21))
        _add_cube(stage, f"/World/GP_Props/Bunker_{bi}_Roof",  (bx,by,bz+1.52),(4.0,2.8,0.28),(0.16,0.18,0.15))
        _add_cube(stage, f"/World/GP_Props/Bunker_{bi}_Slit",  (bx,by+1.22,bz+0.92),(1.8,0.07,0.22),(0.02,0.025,0.02))
    for i, x in enumerate(np.linspace(-terrain_size*0.34, terrain_size*0.34, 9)):
        y = fence_y - 3.25 - 0.35*(i%2)
        z = _sample_height(x_values, y_values, heights, x, y)
        _add_cube(stage, f"/World/GP_Props/Concrete_Block_{i}", (float(x),float(y),z+0.28),
                  (1.1,0.35,0.55),(0.34,0.34,0.31), rotate_xyz=(0,0,8.0 if i%2==0 else -8.0))
    for i, x in enumerate(np.linspace(-terrain_size*0.40, terrain_size*0.40, 13)):
        y = fence_y - 2.0
        z = _sample_height(x_values, y_values, heights, x, y)
        color = (0.72,0.62,0.12) if i%2==0 else (0.55,0.08,0.06)
        _add_cylinder(stage, f"/World/GP_Props/BoundaryMarker_{i}", (float(x),y,z+0.42), 0.045, 0.84, color)
    for i, x in enumerate(np.linspace(-terrain_size*0.38, terrain_size*0.38, 7)):
        sy = fence_y - 1.0
        sz = _sample_height(x_values, y_values, heights, x, sy)
        _add_cylinder(stage, f"/World/GP_Props/WarningSign_{i}_Post",  (x,sy,sz+0.65), 0.03, 1.3, (0.08,0.08,0.07))
        _add_cube(stage,      f"/World/GP_Props/WarningSign_{i}_Plate", (x,sy,sz+1.23),(0.75,0.05,0.45),(0.85,0.72,0.18))
        _add_visual_cube(stage,f"/World/GP_Props/WarningSign_{i}_RedStripe",(x,sy-0.028,sz+1.23),(0.72,0.018,0.08),(0.70,0.08,0.06))
    rsy = fence_y + 5.0
    for i, x in enumerate(np.linspace(-terrain_size*0.32, terrain_size*0.32, 8)):
        y = rsy + 3.8 + 0.55*(i%2)
        z = _sample_height(x_values, y_values, heights, x, y) + 0.17
        _add_visual_cylinder(stage, f"/World/GP_Props/RiverMarkerBuoy_{i}", (float(x),y,z), 0.13, 0.34, (0.80,0.22,0.08))
    for i, x in enumerate(np.linspace(-terrain_size*0.43, terrain_size*0.43, 28)):
        y = rsy - 0.65 + 0.35*np.sin(i*1.7)
        z = _sample_height(x_values, y_values, heights, x, y)
        h = 0.38 + 0.18*((i*37)%11)/10.0
        _add_visual_cube(stage, f"/World/GP_Props/RiverBankReed_{i}",
                         (float(x),float(y),z+h*0.5),(0.035,0.035,h),(0.16,0.20,0.08),
                         rotate_xyz=(0,0,-9.0+(i%5)*4.5))
    for i, x in enumerate(np.linspace(-terrain_size*0.36, terrain_size*0.36, 5)):
        y = fence_y - 6.8
        z = _sample_height(x_values, y_values, heights, x, y)
        _add_cylinder(stage, f"/World/GP_Props/PatrolLight_{i}_Pole", (float(x),y,z+1.7), 0.045, 3.4, (0.08,0.08,0.07))
        _add_cube(stage,     f"/World/GP_Props/PatrolLight_{i}_Head", (float(x),y+0.18,z+3.45),(0.45,0.22,0.18),(0.04,0.045,0.04))
        _add_sphere_light(stage,f"/World/GP_Props/PatrolLight_{i}_Lamp",(float(x),y+0.28,z+3.45),0.10,1300.0,(1.0,0.84,0.55))


def _enable_alpha_cutout_for_prop(root_prim, threshold=0.43):
    alpha_tex = None
    preview_shaders = []
    for prim in Usd.PrimRange(root_prim):
        if prim.GetTypeName() != "Shader":
            continue
        shader = UsdShade.Shader(prim)
        sid = shader.GetIdAttr().Get()
        if sid == "UsdPreviewSurface":
            preview_shaders.append(shader)
        elif sid == "UsdUVTexture":
            fi = shader.GetInput("file")
            fs = str(fi.Get()).lower() if fi else ""
            if any(k in fs for k in ("basecolor","cutoff","alpha")):
                alpha_tex = shader
    if alpha_tex:
        alpha_tex.CreateOutput("a", Sdf.ValueTypeNames.Float)
    for s in preview_shaders:
        s.CreateInput("opacityThreshold", Sdf.ValueTypeNames.Float).Set(float(threshold))
        if alpha_tex:
            s.CreateInput("opacity", Sdf.ValueTypeNames.Float).ConnectToSource(alpha_tex.ConnectableAPI(), "a")


def _add_external_prop_reference(stage, prim_path, asset_path, center, scale, rotate_xyz=(0,0,0), label=None):
    if not asset_path:
        return False
    resolved = str(Path(asset_path).expanduser())
    if not Path(resolved).exists():
        carb.log_warn(f"External prop asset not found: {resolved}")
        return False
    try:
        root_prim = add_reference_to_stage(usd_path=resolved, prim_path=prim_path)
    except Exception as exc:
        carb.log_warn(f"Failed to add external prop '{resolved}': {exc}")
        return False
    if root_prim is None or not root_prim.IsValid():
        return False
    xf = UsdGeom.Xformable(root_prim)
    xf.ClearXformOpOrder()
    xf.AddTranslateOp().Set(Gf.Vec3f(*[float(v) for v in center]))
    xf.AddRotateXYZOp().Set(Gf.Vec3f(*[float(v) for v in rotate_xyz]))
    xf.AddScaleOp().Set(Gf.Vec3f(float(scale), float(scale), float(scale)))
    if label:
        _label_prim_tree(root_prim, label)
    print(f"Loaded external prop: {resolved} -> {prim_path}")
    return True


def _add_external_gp_props(stage, x_values, y_values, heights, terrain_size, fence_y,
                            guard_tower_asset, guard_tower_scale, fence_asset, fence_asset_scale, fence_asset_count):
    stage.DefinePrim("/World/GP_ExternalProps", "Xform")
    fy = _get_fence_y(terrain_size, fence_y)
    for ti, tx in enumerate((-terrain_size*0.31, terrain_size*0.31)):
        ty = fy - 6.0
        tz = _sample_height(x_values, y_values, heights, tx, ty)
        _add_external_prop_reference(stage, f"/World/GP_ExternalProps/GuardTower_{ti}",
                                     guard_tower_asset, (float(tx),float(ty),float(tz)), guard_tower_scale,
                                     rotate_xyz=(0,0,0 if ti==0 else 180), label="guard_tower")
    count = max(0, int(fence_asset_count))
    if count > 0:
        for i, x in enumerate(np.linspace(-terrain_size*0.40, terrain_size*0.40, count)):
            z = _sample_height(x_values, y_values, heights, x, fy)
            _add_external_prop_reference(stage, f"/World/GP_ExternalProps/ChainlinkFenceTile_{i}",
                                         fence_asset, (float(x),float(fy),float(z)), fence_asset_scale,
                                         label="fence")
            fp = stage.GetPrimAtPath(f"/World/GP_ExternalProps/ChainlinkFenceTile_{i}")
            if fp.IsValid():
                _enable_alpha_cutout_for_prop(fp)


def _add_scene_lighting(stage):
    dome = UsdLux.DomeLight.Define(stage, Sdf.Path("/World/DomeLight"))
    dome.CreateIntensityAttr(650.0)
    dome.CreateColorAttr(Gf.Vec3f(0.86, 0.92, 1.0))
    sun = UsdLux.DistantLight.Define(stage, Sdf.Path("/World/Sun"))
    sun.CreateIntensityAttr(1800.0)
    sun.CreateAngleAttr(0.7)
    UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-55.0, 0.0, 35.0))

# ---------------------------------------------------------------------------
# 지형 메쉬 생성
# ---------------------------------------------------------------------------

def build_terrain(stage, args):
    x_values, y_values, heights = _generate_heightfield(
        args.terrain_size, args.terrain_resolution, args.terrain_amplitude,
        args.terrain_seed, args.fence_y,
    )
    samples = heights.shape[0]
    mesh = UsdGeom.Mesh.Define(stage, Sdf.Path("/World/GP_NoiseTerrain"))
    points = [
        Gf.Vec3f(float(x_values[col]), float(y_values[row]), float(heights[row, col]))
        for row in range(samples) for col in range(samples)
    ]
    indices = []
    for row in range(samples - 1):
        for col in range(samples - 1):
            p00 = row * samples + col
            indices.extend([p00, p00+1, p00+samples+1, p00, p00+samples+1, p00+samples])
    mesh.CreatePointsAttr(points)
    mesh.CreateFaceVertexCountsAttr([3] * (len(indices) // 3))
    mesh.CreateFaceVertexIndicesAttr(indices)
    mesh.CreateSubdivisionSchemeAttr().Set("none")
    mesh.CreateDoubleSidedAttr(True)
    mesh.CreateDisplayColorAttr([Gf.Vec3f(0.17, 0.18, 0.12)])
    _add_terrain_uvs(mesh, x_values, y_values, args.terrain_texture_scale)
    mesh.CreateExtentAttr([
        Gf.Vec3f(float(x_values[0]), float(y_values[0]), float(np.min(heights))),
        Gf.Vec3f(float(x_values[-1]), float(y_values[-1]), float(np.max(heights))),
    ])
    _bind_terrain_texture(stage, mesh.GetPrim(),
                          args.terrain_texture, args.terrain_normal_texture, args.terrain_roughness_texture)
    _add_terrain_grid(stage, x_values, y_values, heights, args.terrain_grid_step)
    fy = _get_fence_y(args.terrain_size, args.fence_y)
    _add_river(stage, x_values, y_values, heights, args.terrain_size, fy, args.river_width)
    if not args.no_ground_detail:
        _add_ground_surface_variation(stage, x_values, y_values, heights, args.terrain_size, fy)
    if not args.no_gp_props:
        ext_towers = (not args.no_external_props and bool(args.guard_tower_asset)
                      and Path(str(args.guard_tower_asset)).expanduser().exists())
        _add_gp_props(stage, x_values, y_values, heights, args.terrain_size, fy,
                      args.river_width, skip_watchtowers=ext_towers)
    if not args.no_external_props:
        _add_external_gp_props(stage, x_values, y_values, heights, args.terrain_size, fy,
                                args.guard_tower_asset, args.guard_tower_scale,
                                args.fence_asset, args.fence_asset_scale, args.fence_asset_count)
    _add_scene_lighting(stage)
    print(f"[terrain_preview] height range: {np.min(heights):.3f}m ~ {np.max(heights):.3f}m")
    return x_values, y_values, heights

# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Terrain-only preview (no robot / no physics / no ROS 2)")
    parser.add_argument("--terrain-amplitude",       type=float, default=0.28)
    parser.add_argument("--terrain-size",            type=float, default=80.0)
    parser.add_argument("--terrain-resolution",      type=float, default=0.5)
    parser.add_argument("--terrain-grid-step",       type=float, default=0.0)
    parser.add_argument("--trail-width",             type=float, default=5.0)
    parser.add_argument("--fence-y",                 type=float, default=16.0)
    parser.add_argument("--river-width",             type=float, default=18.0)
    parser.add_argument("--terrain-texture",         type=str,   default="")
    parser.add_argument("--terrain-normal-texture",  type=str,   default="")
    parser.add_argument("--terrain-roughness-texture",type=str,  default="")
    parser.add_argument("--terrain-texture-scale",   type=float, default=1.0)
    parser.add_argument("--terrain-seed",            type=int,   default=7)
    parser.add_argument("--no-ground-detail",        action="store_true")
    parser.add_argument("--no-gp-props",             action="store_true")
    parser.add_argument("--no-external-props",       action="store_true")
    parser.add_argument("--guard-tower-asset",       type=str,   default=str(DEFAULT_GUARD_TOWER_ASSET))
    parser.add_argument("--guard-tower-scale",       type=float, default=1.0)
    parser.add_argument("--fence-asset",             type=str,   default=str(DEFAULT_CHAINLINK_FENCE_ASSET))
    parser.add_argument("--fence-asset-scale",       type=float, default=1.0)
    parser.add_argument("--fence-asset-count",       type=int,   default=12)
    parser.add_argument(
        "--save-path", type=str,
        default=str(PROJECT_ROOT / "saved_scenes" / "terrain.usd"),
        help="저장/로드할 USD 파일 경로",
    )
    parser.add_argument(
        "--rebuild", action="store_true",
        help="저장 파일이 있어도 무시하고 처음부터 다시 빌드",
    )
    args, _ = parser.parse_known_args()

    save_path = Path(args.save_path)
    usd_ctx = omni.usd.get_context()

    if save_path.exists() and not args.rebuild:
        # 저장된 씬 로드
        print(f"[terrain_preview] 저장된 씬 로드: {save_path}")
        usd_ctx.open_stage(str(save_path))
        simulation_app.update()
        print("[terrain_preview] 로드 완료.")
    else:
        # 처음부터 빌드
        if args.rebuild:
            print("[terrain_preview] --rebuild: 씬을 새로 생성합니다.")
        else:
            print("[terrain_preview] 저장 파일 없음. 씬을 새로 생성합니다.")
        stage = usd_ctx.get_stage()
        stage.DefinePrim("/World", "Xform")
        build_terrain(stage, args)
        simulation_app.update()
        # 저장
        save_path.parent.mkdir(parents=True, exist_ok=True)
        usd_ctx.save_as_stage(str(save_path))
        print(f"[terrain_preview] 씬 저장 완료: {save_path}")
        print("[terrain_preview] 다음 실행 시 이 파일을 자동 로드합니다.")
        print("[terrain_preview] Isaac Sim 안에서 수정 후 Ctrl+S 로 저장하면 반영됩니다.")

    print("[terrain_preview] 창을 닫으면 종료됩니다.")
    while simulation_app.is_running():
        simulation_app.update()

    simulation_app.close()


if __name__ == "__main__":
    main()
