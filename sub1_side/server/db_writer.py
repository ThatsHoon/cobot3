"""asyncpg COPY 배치 적재기 (telemetry-supabase.md 패턴).

ROS 콜백/추론 결과를 큐에 넣으면 백그라운드 태스크가 1초 배치로
`copy_records_to_table` 한다. 영상 프레임은 절대 넣지 않는다(설계 §13).
"""
import asyncio
import logging
from collections import defaultdict

import asyncpg

import config

log = logging.getLogger("c2.db")

# 테이블별 (컬럼 순서) — schema.sql 과 일치
COLUMNS = {
    "intruder_detections": ["robot_id", "ts", "class_name", "confidence",
                            "bbox_x", "bbox_y", "bbox_w", "bbox_h",
                            "world_x", "world_y", "world_z",
                            "beyond_fence", "camera_frame"],
    "gps_track":        ["robot_id", "ts", "lat", "lon", "alt", "x", "y"],
    "fire_events":      ["robot_id", "ts", "target_ref", "hit",
                         "distance_m", "operator"],
    "rosout_warn":      ["ts", "level", "node_name", "msg"],
    "joint_snapshots":  ["robot_id", "ts", "arm_q", "leg_q"],
    "robot_state_log":  ["robot_id", "ts", "mode", "gait",
                         "battery", "waypoint", "extra"],
}


class DBWriter:
    def __init__(self):
        self._pool: asyncpg.Pool | None = None
        self._q: asyncio.Queue = asyncio.Queue(maxsize=config.DB_QUEUE_MAX)
        self._task: asyncio.Task | None = None

    async def start(self):
        self._pool = await asyncpg.create_pool(config.DB_URL, min_size=1, max_size=4)
        self._task = asyncio.create_task(self._flush_loop())
        log.info("DBWriter started (%s)", config.DB_URL)

    async def stop(self):
        if self._task:
            self._task.cancel()
        if self._pool:
            await self._pool.close()

    def put(self, table: str, record: tuple):
        """비차단 enqueue. 큐가 가득 차면 가장 오래된 것을 버린다(텔레메트리는 손실 허용)."""
        try:
            self._q.put_nowait((table, record))
        except asyncio.QueueFull:
            try:
                self._q.get_nowait()
                self._q.put_nowait((table, record))
            except Exception:
                pass

    async def _flush_loop(self):
        while True:
            await asyncio.sleep(config.DB_FLUSH_SEC)
            batch: dict[str, list] = defaultdict(list)
            while not self._q.empty():
                table, rec = self._q.get_nowait()
                batch[table].append(rec)
            if not batch or self._pool is None:
                continue
            try:
                async with self._pool.acquire() as conn:
                    for table, rows in batch.items():
                        await conn.copy_records_to_table(
                            table, records=rows, columns=COLUMNS[table]
                        )
            except Exception as e:  # 적재 실패는 서버를 죽이지 않음(다음 주기 재시도 X — 손실 허용)
                log.warning("DB flush failed: %s", e)
