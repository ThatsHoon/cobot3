"""Routing_Zones 링크 xlsx 로더.

scene/routing_zones_links.xlsx (사용자 수동 정의) → (edges, tp_zone_map).
- edges: zone_router.ZoneRouter(routing_edges=...) 형식
- tp_zone_map: {"TP_A": "Xform_09", ...} — TP 별 최종 목적 zone 강제 매핑

xlsx 없거나 비어 있으면 (None, {}) 반환 → 호출측이 기존 자동 로직으로 폴백.
"""
import math
import os
import re

try:
    import openpyxl  # type: ignore
except Exception:
    openpyxl = None

# Notes 컬럼에서 'XformXX는 TP_X 의 최종 목적 좌표' 패턴 추출 (사용자 표기 그대로).
_TP_NOTE_RE = re.compile(r"(Xform[_\d]*)\s*(?:는|은)?\s*(TP_[A-D])\s*의\s*최종")


def load_routing_links(xlsx_path: str):
    """xlsx 를 읽어 (edges, tp_zone_map) 반환. 파일/모듈 부재 시 (None, {})."""
    if openpyxl is None:
        return None, {}
    if not os.path.exists(xlsx_path):
        return None, {}
    try:
        wb = openpyxl.load_workbook(xlsx_path, data_only=False)
    except Exception:
        return None, {}

    # Zones 좌표 캐시 (StraightDist 자동 계산용 — xlsx 수식 결과 대신 직접 계산)
    zone_xy: dict[str, tuple[float, float]] = {}
    if "Zones" in wb.sheetnames:
        for row in wb["Zones"].iter_rows(min_row=2, values_only=True):
            if len(row) >= 5 and row[1] and row[2] is not None and row[3] is not None:
                zone_xy[str(row[1])] = (float(row[2]), float(row[3]))

    edges: list[dict] = []
    tp_zone_map: dict[str, str] = {}
    if "Links" not in wb.sheetnames:
        return edges, tp_zone_map

    for row in wb["Links"].iter_rows(min_row=2, values_only=True):
        frm = row[0] if len(row) > 0 else None
        to = row[1] if len(row) > 1 else None
        if not frm or not to:
            continue
        bi = (str(row[2]).strip().upper() if len(row) > 2 and row[2] else "Y") == "Y"
        en = (str(row[3]).strip().upper() if len(row) > 3 and row[3] else "Y") == "Y"
        notes = str(row[8]) if len(row) > 8 and row[8] else ""

        # Notes 에서 TP 매핑 추출 — From 또는 To 가 매핑 zone 이면 등록
        m = _TP_NOTE_RE.search(notes)
        if m:
            zone_name, tp_id = m.group(1), m.group(2)
            tp_zone_map[tp_id] = zone_name

        if not en:
            continue

        a, b = str(frm), str(to)
        # StraightDist (xlsx 수식 결과 신뢰 못함 — 직접 계산)
        pa = zone_xy.get(a)
        pb = zone_xy.get(b)
        dist = math.hypot(pa[0] - pb[0], pa[1] - pb[1]) if (pa and pb) else 0.0

        edges.append({"a": a, "b": b, "dist": dist, "valid": True})
        if bi:
            edges.append({"a": b, "b": a, "dist": dist, "valid": True})

    return edges, tp_zone_map
