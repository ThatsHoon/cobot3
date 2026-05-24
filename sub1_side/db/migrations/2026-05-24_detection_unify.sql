-- 2026-05-24: 통신/구조 효율화 마이그레이션 (Tier 3)
-- 1) intruder_detections (픽셀 bbox) + intruder_states_log (world GT) → detection_events 통합
-- 2) gps_track 에 yaw 컬럼 추가 (/robot/odom 와 합류)
--
-- 적용:  psql -d cobot3 -f 2026-05-24_detection_unify.sql
-- 백업 (필수, 사전):
--   pg_dump -Fc -d cobot3 -f /home/hoon/cobot3_backup_$(date +%Y%m%d_%H%M).dump
-- 롤백:
--   psql -d cobot3 -c "DROP TABLE detection_events;
--     ALTER TABLE _deprecated_intruder_detections RENAME TO intruder_detections;
--     ALTER TABLE _deprecated_intruder_states_log RENAME TO intruder_states_log;
--     ALTER TABLE gps_track DROP COLUMN yaw;"

BEGIN;

-- 1) 통합 테이블
CREATE TABLE IF NOT EXISTS detection_events (
    id           BIGSERIAL PRIMARY KEY,
    ts           TIMESTAMPTZ NOT NULL,
    robot_id     TEXT REFERENCES robots(robot_id),
    source       TEXT NOT NULL,    -- camera_inspect|camera_tp_a..|ground_truth
    kind         TEXT NOT NULL,    -- 'detection' (YOLO bbox) | 'gt_state' (intruder GT)
    class_name   TEXT,
    confidence   REAL,
    bbox_pixel   JSONB,            -- {x,y,w,h} | NULL
    world_x      REAL,
    world_y      REAL,
    world_z      REAL,
    beyond_fence BOOLEAN,
    intruder_id  TEXT,             -- gt_state 일 때만 (NPC id)
    ack          BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_detev_robot_ts ON detection_events (robot_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_detev_kind     ON detection_events (kind, ts DESC);
CREATE INDEX IF NOT EXISTS idx_detev_ack      ON detection_events (ack) WHERE ack = FALSE;
CREATE INDEX IF NOT EXISTS idx_detev_ts_brin  ON detection_events USING BRIN (ts);

-- 2) gps_track 에 yaw 컬럼 (D4 합류 — /robot/odom 의 yaw 를 gps_track 에 통합)
ALTER TABLE gps_track ADD COLUMN IF NOT EXISTS yaw REAL;

-- 3) 데이터 이관 (구 테이블 존재 시만)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_name = 'intruder_detections') THEN
        INSERT INTO detection_events
            (ts, robot_id, source, kind, class_name, confidence,
             bbox_pixel, world_x, world_y, world_z, beyond_fence)
        SELECT ts, robot_id, COALESCE(camera_frame, 'unknown'), 'detection',
               class_name, confidence,
               jsonb_build_object('x', bbox_x, 'y', bbox_y,
                                  'w', bbox_w, 'h', bbox_h),
               world_x, world_y, world_z, beyond_fence
        FROM intruder_detections;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_name = 'intruder_states_log') THEN
        INSERT INTO detection_events
            (ts, robot_id, source, kind, intruder_id,
             world_x, world_y, world_z, class_name)
        SELECT ts, 'gp0', 'ground_truth', 'gt_state', intruder_id,
               x, y, z, label
        FROM intruder_states_log;
    END IF;
END $$;

-- 4) 구 테이블 deprecated prefix (1주 후 별도 마이그레이션으로 DROP)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_name = 'intruder_detections') THEN
        ALTER TABLE intruder_detections RENAME TO _deprecated_intruder_detections;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_name = 'intruder_states_log') THEN
        ALTER TABLE intruder_states_log RENAME TO _deprecated_intruder_states_log;
    END IF;
END $$;

COMMIT;

-- 검증:
--   SELECT kind, count(*) FROM detection_events GROUP BY kind;
--   \dt _deprecated_*
--   \d gps_track   (yaw real 확인)
