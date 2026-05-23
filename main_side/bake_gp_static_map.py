"""gp_scene.usd 의 정적 점유격자(Nav2 map_server 포맷)를 베이크.

`CollisionAPI` 가 적용된 prim 중 `/World/Terrain` 트리 외 것들의 world AABB 를
XY 평면에 투영해 occupied 셀로 표시. 출력은 PGM(P5) + yaml.

런타임(camera_publisher) 의존 0 — bake_friction.py 와 동일한 standalone Kit 패턴.

실행:
    ${ISAAC_PYTHON} bake_gp_static_map.py
    ${ISAAC_PYTHON} bake_gp_static_map.py --xmin -1000 --xmax -600 \\
            --ymin 880 --ymax 1020 --res 0.5

출력:
    main_side/scene/maps/gp_static.pgm
    main_side/scene/maps/gp_static.yaml
"""
import os
import sys

from isaacsim import SimulationApp

simulation_app = SimulationApp({"headless": True})

import omni.usd  # noqa: E402
from pxr import Usd, UsdGeom, UsdPhysics  # noqa: E402
import numpy as np  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
SCENE = os.path.join(_HERE, "scene", "gp_scene.usd")
OUT_DIR = os.path.join(_HERE, "scene", "maps")
PGM = os.path.join(OUT_DIR, "gp_static.pgm")
YAML = os.path.join(OUT_DIR, "gp_static.yaml")

_DEFAULT_RES = 0.5  # m/px — patrol 스케일 적정 해상도
_PATROL_PAD = 80.0  # Cube/Cone AABB 외곽 여유 (m)
_MARKER_PATHS = ("/World/Cube", "/World/Cone", "/World/recharge_station")


def _parse_args():
    # SimulationApp 초기화 이후 argv 가져옴
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--res", type=float, default=_DEFAULT_RES)
    p.add_argument("--xmin", type=float, default=None)
    p.add_argument("--xmax", type=float, default=None)
    p.add_argument("--ymin", type=float, default=None)
    p.add_argument("--ymax", type=float, default=None)
    p.add_argument("--no-clamp", action="store_true",
                   help="Cube/Cone+pad 영역으로의 자동 클램프 비활성")
    p.add_argument("--zone", choices=["gp", "dmz"], default="gp",
                   help="gp(기본): Cube/Cone+terrain. dmz: /World/DMZ_Zone "
                        "AABB(-40~+40) 만 베이크 → dmz_static.{pgm,yaml}")
    return p.parse_args(sys.argv[1:])


def _aabb_world(prim):
    cache = UsdGeom.BBoxCache(
        Usd.TimeCode.Default(),
        includedPurposes=[UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
    bbox = cache.ComputeWorldBound(prim)
    rng = bbox.ComputeAlignedRange()
    if rng.IsEmpty():
        return None
    return (float(rng.GetMin()[0]), float(rng.GetMin()[1]),
            float(rng.GetMax()[0]), float(rng.GetMax()[1]))


def _is_marker(path):
    return any(path.startswith(m) for m in _MARKER_PATHS)


def _is_terrain(path):
    return path.startswith("/World/Terrain") or "GP_NoiseTerrain" in path


def main():
    args = _parse_args()

    ctx = omni.usd.get_context()
    ctx.open_stage(SCENE)
    stage = ctx.get_stage()

    terr_xmin = terr_ymin = float("inf")
    terr_xmax = terr_ymax = float("-inf")
    obstacles = []

    for prim in stage.Traverse():
        if not prim.HasAPI(UsdPhysics.CollisionAPI):
            continue
        path = str(prim.GetPath())
        if _is_marker(path):
            continue
        ab = _aabb_world(prim)
        if ab is None:
            continue
        x0, y0, x1, y1 = ab
        if _is_terrain(path):
            terr_xmin = min(terr_xmin, x0)
            terr_ymin = min(terr_ymin, y0)
            terr_xmax = max(terr_xmax, x1)
            terr_ymax = max(terr_ymax, y1)
        else:
            obstacles.append((path, x0, y0, x1, y1))

    # zone=dmz: DMZ_Zone AABB(-40~+40) 만 베이크 (DMZ_Zone 자체는 런타임
    # 생성이라 USD 에 없을 수 있으므로 좌표 하드코딩)
    if args.zone == "dmz":
        xmin, xmax, ymin, ymax = -40.0, 40.0, -40.0, 40.0
        src = "dmz_zone"
        # 출력 파일명도 dmz_static.* 로 변경
        global PGM, YAML
        PGM = os.path.join(OUT_DIR, "dmz_static.pgm")
        YAML = os.path.join(OUT_DIR, "dmz_static.yaml")
    # 1. AABB 결정 우선순위: 사용자 지정 > 지형 > Cube/Cone+pad
    elif all(v is not None for v in
           (args.xmin, args.xmax, args.ymin, args.ymax)):
        xmin, xmax = args.xmin, args.xmax
        ymin, ymax = args.ymin, args.ymax
        src = "args"
    elif terr_xmin < terr_xmax:
        xmin, xmax = terr_xmin, terr_xmax
        ymin, ymax = terr_ymin, terr_ymax
        src = "terrain"
    else:
        xmin = xmax = ymin = ymax = None
        src = None

    cube = stage.GetPrimAtPath("/World/Cube")
    cone = stage.GetPrimAtPath("/World/Cone")
    c_ab = _aabb_world(cube) if cube and cube.IsValid() else None
    n_ab = _aabb_world(cone) if cone and cone.IsValid() else None

    if xmin is None:
        if c_ab is None or n_ab is None:
            print("[bake] ERROR: 지형도 없고 Cube/Cone 도 없음 — AABB 추정 불가")
            simulation_app.close()
            sys.exit(1)
        xmin = min(c_ab[0], n_ab[0]) - _PATROL_PAD
        xmax = max(c_ab[2], n_ab[2]) + _PATROL_PAD
        ymin = min(c_ab[1], n_ab[1]) - _PATROL_PAD
        ymax = max(c_ab[3], n_ab[3]) + _PATROL_PAD
        src = "cube_cone_pad"

    # 2. 지형이 너무 넓고 (>500m) Cube/Cone 좌표가 있으면 patrol 영역으로 클램프
    if (not args.no_clamp and src == "terrain"
            and c_ab is not None and n_ab is not None):
        if (xmax - xmin) > 500.0 or (ymax - ymin) > 500.0:
            px0 = min(c_ab[0], n_ab[0]) - _PATROL_PAD
            px1 = max(c_ab[2], n_ab[2]) + _PATROL_PAD
            py0 = min(c_ab[1], n_ab[1]) - _PATROL_PAD
            py1 = max(c_ab[3], n_ab[3]) + _PATROL_PAD
            xmin = max(xmin, px0)
            xmax = min(xmax, px1)
            ymin = max(ymin, py0)
            ymax = min(ymax, py1)
            src += "+patrol_clamp"

    res = float(args.res)
    W = int(np.ceil((xmax - xmin) / res))
    H = int(np.ceil((ymax - ymin) / res))
    if W <= 0 or H <= 0 or W * H > 4_000_000:
        print(f"[bake] ERROR: 비정상 그리드 크기 {W}x{H} — AABB/해상도 확인")
        simulation_app.close()
        sys.exit(2)

    print(f"[bake] AABB src={src} x=[{xmin:.2f},{xmax:.2f}] "
          f"y=[{ymin:.2f},{ymax:.2f}] -> {W}x{H} px @ {res} m/px")

    grid = np.full((H, W), 255, dtype=np.uint8)  # free
    nb = 0
    for path, x0, y0, x1, y1 in obstacles:
        ox0 = max(0, int(np.floor((x0 - xmin) / res)))
        ox1 = min(W, int(np.ceil((x1 - xmin) / res)))
        oy0 = max(0, int(np.floor((y0 - ymin) / res)))
        oy1 = min(H, int(np.ceil((y1 - ymin) / res)))
        if ox0 >= ox1 or oy0 >= oy1:
            continue
        # PGM y축 반전: world y_max 가 row 0
        ry0 = H - oy1
        ry1 = H - oy0
        grid[ry0:ry1, ox0:ox1] = 0
        nb += 1

    print(f"[bake] obstacles rasterized: {nb} / total CollisionAPI"
          f"(non-terrain non-marker) = {len(obstacles)}")

    # Cube/Cone 셀이 occupied 면 강제로 free 로 (마커가 fence 와 겹칠 때 보호)
    for ab in (c_ab, n_ab):
        if ab is None:
            continue
        cx = 0.5 * (ab[0] + ab[2])
        cy = 0.5 * (ab[1] + ab[3])
        if not (xmin <= cx < xmax and ymin <= cy < ymax):
            continue
        cix = int((cx - xmin) / res)
        ciy = H - 1 - int((cy - ymin) / res)
        r = max(1, int(0.4 / res))
        y0 = max(0, ciy - r)
        y1 = min(H, ciy + r + 1)
        x0 = max(0, cix - r)
        x1 = min(W, cix + r + 1)
        grid[y0:y1, x0:x1] = 255

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(PGM, "wb") as f:
        f.write(f"P5\n{W} {H}\n255\n".encode("ascii"))
        f.write(grid.tobytes())

    yaml_text = (
        f"image: gp_static.pgm\n"
        f"mode: trinary\n"
        f"resolution: {res}\n"
        f"origin: [{xmin}, {ymin}, 0.0]\n"
        f"negate: 0\n"
        f"occupied_thresh: 0.65\n"
        f"free_thresh: 0.25\n"
    )
    with open(YAML, "w") as f:
        f.write(yaml_text)

    with open("/tmp/gp_static_bake.txt", "w") as f:
        f.write(f"src={src}\n")
        f.write(f"aabb=[{xmin},{xmax},{ymin},{ymax}]\n")
        f.write(f"size={W}x{H} res={res}\n")
        f.write(f"obstacles={nb}/{len(obstacles)}\n")

    print(f"[bake] saved {PGM} ({W}x{H} uint8) + {YAML}")
    print(f"[bake] origin=[{xmin}, {ymin}, 0.0] resolution={res}")

    simulation_app.close()


if __name__ == "__main__":
    main()
