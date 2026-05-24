"""Zone 그래프 기반 경로 계획기.

/scene/landmarks 의 routing_zones 목록으로 인접 그래프를 구성하고
Dijkstra 로 최단 경로를 계산한다.

2026-05-24: 스캔 범위(max_edge_m) 디폴트만 50→10m 로 축소. 알고리즘은 기존
Dijkstra 최단 경로 그대로. env C2_ZONE_MAX_EDGE_M 로 override 가능.

사용법:
    router = ZoneRouter(zones_list, tactical_points_dict)
    waypoints = router.plan((robot_x, robot_y), "TP_A")
    # → [(x1,y1), (x2,y2), ..., (tp_x, tp_y)]
"""
import heapq
import math
import os


DEFAULT_MAX_EDGE_M = float(os.environ.get("C2_ZONE_MAX_EDGE_M", "10.0"))


def _dist2d(a: tuple, b: tuple) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


class ZoneRouter:
    def __init__(
        self,
        zones: list[dict],
        tactical_points: dict[str, dict],
        max_edge_m: float | None = None,
        routing_edges: list[dict] | None = None,
    ) -> None:
        # zones: [{"name": str, "x": float, "y": float, "z": float}, ...]
        # tactical_points: {"TP_A": {"x": float, "y": float, "z": float}, ...}
        # routing_edges: [{"a": str, "b": str, "dist": float, "valid": bool}, ...]
        #   None → 거리 기반 자동 생성 (폴백)
        eff_max = max_edge_m if max_edge_m is not None else DEFAULT_MAX_EDGE_M
        self._zones: dict[str, tuple[float, float]] = {
            z["name"]: (z["x"], z["y"]) for z in zones
        }
        self._tps: dict[str, tuple[float, float]] = {
            k: (v["x"], v["y"]) for k, v in tactical_points.items()
        }
        if routing_edges is not None:
            self._graph = self._build_from_edges(routing_edges, eff_max)
        else:
            self._graph = self._build(eff_max)

    def _build_from_edges(
        self, routing_edges: list[dict], max_edge_m: float
    ) -> dict[str, list[tuple[float, str]]]:
        g: dict[str, list] = {n: [] for n in self._zones}
        for e in routing_edges:
            if not e.get("valid", True):
                continue
            a, b, d = e["a"], e["b"], float(e["dist"])
            if a in g and b in g:
                g[a].append((d, b))
                g[b].append((d, a))
        # 폴백: 검증된 엣지가 아예 없으면 거리 기반으로 생성
        if all(len(v) == 0 for v in g.values()):
            return self._build(max_edge_m)
        return g

    def _build(self, max_edge_m: float) -> dict[str, list[tuple[float, str]]]:
        g: dict[str, list] = {n: [] for n in self._zones}
        names = list(self._zones)
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                d = _dist2d(self._zones[a], self._zones[b])
                if d <= max_edge_m:
                    g[a].append((d, b))
                    g[b].append((d, a))
        return g

    def _dijkstra(self, start: str, end: str) -> list[str]:
        if start == end:
            return [start]
        dist: dict[str, float] = {n: float("inf") for n in self._zones}
        dist[start] = 0.0
        prev: dict[str, str] = {}
        heap: list[tuple[float, str]] = [(0.0, start)]
        while heap:
            d, u = heapq.heappop(heap)
            if d > dist[u]:
                continue
            if u == end:
                break
            for w, v in self._graph.get(u, []):
                nd = d + w
                if nd < dist[v]:
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(heap, (nd, v))
        if end not in prev:
            return []
        path: list[str] = []
        cur = end
        while cur in prev:
            path.append(cur)
            cur = prev[cur]
        path.append(start)
        return list(reversed(path))

    def plan(self, robot_xy: tuple[float, float], tp_id: str) -> list[tuple[float, float]]:
        """robot_xy 에서 tp_id 까지의 (x,y) 웨이포인트 목록을 반환한다.

        반환: [nearest_zone_pos, ..., end_zone_pos, tp_pos] 순서.
        ZoneRouter 가 미초기화거나 tp_id 가 없으면 [] 반환.
        """
        tp = self._tps.get(tp_id)
        if tp is None or not self._zones:
            return []

        start_zone = min(self._zones, key=lambda n: _dist2d(robot_xy, self._zones[n]))
        end_zone = min(self._zones, key=lambda n: _dist2d(tp, self._zones[n]))

        zone_path = self._dijkstra(start_zone, end_zone)
        if not zone_path:
            # 연결 경로 없음 → start/end 직결
            zone_path = [start_zone, end_zone]

        waypoints = [self._zones[n] for n in zone_path]

        # end_zone 과 TP 가 2m 이상 떨어진 경우에만 TP 를 별도 최종 목표로 추가
        if _dist2d(waypoints[-1], tp) > 2.0:
            waypoints.append(tp)

        return waypoints

    def available_tps(self) -> list[str]:
        return list(self._tps.keys())

    def tp_position(self, tp_id: str) -> tuple[float, float] | None:
        return self._tps.get(tp_id)

    @property
    def zone_count(self) -> int:
        return len(self._zones)
