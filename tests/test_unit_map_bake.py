"""T1 단위: gp_static.pgm/yaml 산출물 검증."""
import os
import re

import pytest


@pytest.fixture
def map_files(repo_root):
    pgm = os.path.join(repo_root, "main_side", "scene", "maps", "gp_static.pgm")
    yaml = os.path.join(repo_root, "main_side", "scene", "maps", "gp_static.yaml")
    if not (os.path.exists(pgm) and os.path.exists(yaml)):
        pytest.skip("gp_static.{pgm,yaml} 미생성 — bake_gp_static_map.py 실행 필요")
    return pgm, yaml


def test_pgm_header_valid(map_files):
    pgm, _ = map_files
    with open(pgm, "rb") as f:
        head = b""
        while head.count(b"\n") < 3:
            head += f.read(1)
    lines = head.decode("ascii").strip().split("\n")
    assert lines[0] == "P5", "PGM magic 가 P5 (binary) 가 아님"
    w, h = map(int, lines[1].split())
    assert w > 0 and h > 0
    assert int(lines[2]) == 255


def test_yaml_required_fields(map_files):
    _, yaml = map_files
    txt = open(yaml).read()
    for key in ("image:", "resolution:", "origin:", "mode:",
                "occupied_thresh:", "free_thresh:"):
        assert key in txt, f"{key} 없음"
    # origin 3-tuple
    m = re.search(r"origin:\s*\[([\-\d.]+),\s*([\-\d.]+),\s*([\-\d.]+)\]", txt)
    assert m, "origin 포맷 깨짐"
    ox, oy, oz = (float(v) for v in m.groups())
    assert oz == 0.0


def test_map_covers_cube_and_cone(map_files):
    """gp_scene 의 Cube ≈ (-714, 952), Cone ≈ (-937, 939) 좌표가 맵 영역 안에
    포함되며 occupied(0) 가 아니어야 한다 (Go2 가 그 위에서 출발/도착)."""
    import numpy as np
    pgm, yaml = map_files
    # 헤더 파싱
    with open(pgm, "rb") as f:
        head = b""
        while head.count(b"\n") < 3:
            head += f.read(1)
        W, H = map(int, head.decode("ascii").strip().split("\n")[1].split())
        data = np.frombuffer(f.read(), dtype=np.uint8).reshape(H, W)
    txt = open(yaml).read()
    res = float(re.search(r"resolution:\s*([\d.]+)", txt).group(1))
    ox, oy = (float(v) for v in
              re.search(r"origin:\s*\[([\-\d.]+),\s*([\-\d.]+),", txt).groups())
    xmax = ox + W * res
    ymax = oy + H * res

    def world_to_cell(x, y):
        ix = int((x - ox) / res)
        iy = H - 1 - int((y - oy) / res)
        return ix, iy

    for label, (x, y) in (("Cube", (-714.32, 952.93)),
                          ("Cone", (-937.07, 938.98))):
        assert ox <= x < xmax, f"{label} x={x} 범위 밖 ([{ox},{xmax}))"
        assert oy <= y < ymax, f"{label} y={y} 범위 밖 ([{oy},{ymax}))"
        ix, iy = world_to_cell(x, y)
        # 근처 3x3 평균이 free (>= 128) — Cube/Cone 셀이 정확히 fence 옆이면
        # 약간 어두울 수 있으므로 3x3 윈도 평균.
        win = data[max(0, iy - 1):iy + 2, max(0, ix - 1):ix + 2]
        assert win.mean() >= 100, (
            f"{label} 셀({ix},{iy}) 근방 mean={win.mean():.1f} — fence 와 겹침")


def test_occupancy_reasonable(map_files):
    """전체 occupied 비율이 ~0~10% 이내 (실내 미로면 더 많아도 OK)."""
    import numpy as np
    pgm, _ = map_files
    with open(pgm, "rb") as f:
        head = b""
        while head.count(b"\n") < 3:
            head += f.read(1)
        data = np.frombuffer(f.read(), dtype=np.uint8)
    occ_ratio = (data == 0).mean()
    assert 0.0 < occ_ratio < 0.50, (
        f"occupied 비율 {occ_ratio:.3f} 비정상 — 0 이면 베이크 실패, "
        ">=50% 면 obstacle 과대")
