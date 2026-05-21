-- ============================================================================
-- GP 경계근무 4족보행 로봇 — 지휘통제실(C2) 로컬 PostgreSQL 스키마
-- 설계 문서 §13 "저장 정책": 영상 프레임 제외 전 데이터를 psql 에 저장.
-- 적용: psql -d cobot3 -f sub1_side/db/schema.sql
-- (기존 cobot_ws/db/migrations/0001,0002 의 구조를 GP 용으로 적응)
-- ============================================================================

-- robots --------------------------------------------------------------
CREATE TABLE IF NOT EXISTS robots (
    robot_id     TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    installed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO robots (robot_id, name) VALUES
    ('gp0', 'ANYmal-C + m0609 GP patrol')
ON CONFLICT (robot_id) DO NOTHING;

-- intruder_detections  (← detections) : C2 서버측 YOLO 결과 메타데이터 ----
CREATE TABLE IF NOT EXISTS intruder_detections (
    id            BIGSERIAL PRIMARY KEY,
    robot_id      TEXT NOT NULL REFERENCES robots(robot_id),
    ts            TIMESTAMPTZ NOT NULL,
    class_name    TEXT NOT NULL,          -- person / animal / ...
    confidence    REAL NOT NULL,
    bbox_x        REAL NOT NULL,
    bbox_y        REAL NOT NULL,
    bbox_w        REAL NOT NULL,
    bbox_h        REAL NOT NULL,
    world_x       REAL,
    world_y       REAL,
    world_z       REAL,
    beyond_fence  BOOLEAN,                -- 철조망 너머 판정
    camera_frame  TEXT
);
CREATE INDEX IF NOT EXISTS idx_intr_robot_ts ON intruder_detections (robot_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_intr_class    ON intruder_detections (class_name);

-- patrol_runs  (← cycles) : 순찰 주행 단위 -----------------------------
CREATE TABLE IF NOT EXISTS patrol_runs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    robot_id    TEXT NOT NULL REFERENCES robots(robot_id),
    start_ts    TIMESTAMPTZ NOT NULL,
    end_ts      TIMESTAMPTZ,
    route_id    TEXT,
    success     BOOLEAN,
    dist_m      REAL,
    duration_ms INT GENERATED ALWAYS AS (
        EXTRACT(EPOCH FROM (end_ts - start_ts)) * 1000
    ) STORED
);
CREATE INDEX IF NOT EXISTS idx_runs_robot_start ON patrol_runs (robot_id, start_ts DESC);

-- patrol_events  (← cycle_events) -------------------------------------
CREATE TABLE IF NOT EXISTS patrol_events (
    id          BIGSERIAL PRIMARY KEY,
    run_id      UUID REFERENCES patrol_runs(id),
    robot_id    TEXT NOT NULL REFERENCES robots(robot_id),
    ts          TIMESTAMPTZ NOT NULL,
    event_type  TEXT NOT NULL,           -- START|WAYPOINT|ARRIVE|AIM|FIRE|RETURN
    metadata    JSONB
);
CREATE INDEX IF NOT EXISTS idx_pev_run_ts ON patrol_events (run_id, ts);

-- gps_track  (신규) : sim-GPS 궤적 ------------------------------------
CREATE TABLE IF NOT EXISTS gps_track (
    id        BIGSERIAL PRIMARY KEY,
    robot_id  TEXT NOT NULL REFERENCES robots(robot_id),
    ts        TIMESTAMPTZ NOT NULL,
    lat       DOUBLE PRECISION NOT NULL,
    lon       DOUBLE PRECISION NOT NULL,
    alt       REAL,
    x         REAL,                       -- sim 원점기준 로컬 ENU
    y         REAL
);
CREATE INDEX IF NOT EXISTS idx_gps_robot_ts_brin
    ON gps_track USING BRIN (robot_id, ts);

-- fire_events  (신규) : 시뮬 사격 이벤트 ------------------------------
CREATE TABLE IF NOT EXISTS fire_events (
    id              BIGSERIAL PRIMARY KEY,
    robot_id        TEXT NOT NULL REFERENCES robots(robot_id),
    ts              TIMESTAMPTZ NOT NULL,
    target_ref      TEXT,
    hit             BOOLEAN,              -- NULL=인간 판정 대기 (HITL)
    distance_m      REAL,                 -- NULL=raycast 없음 (HITL 흐름)
    operator        TEXT,
    fire_id         UUID,                 -- 2026-05-21: weapon_relay 가 발급
    target_alert_id BIGINT,               -- 관련 YOLO alert (없으면 NULL)
    miss_reason     TEXT,
    result_set_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_fire_robot_ts ON fire_events (robot_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_fire_fire_id  ON fire_events (fire_id);

-- 기존 배포 호환 (멱등 ALTER) — 2026-05-21
DO $$ BEGIN
    ALTER TABLE fire_events ADD COLUMN IF NOT EXISTS fire_id UUID;
    ALTER TABLE fire_events ADD COLUMN IF NOT EXISTS target_alert_id BIGINT;
    ALTER TABLE fire_events ADD COLUMN IF NOT EXISTS miss_reason TEXT;
    ALTER TABLE fire_events ADD COLUMN IF NOT EXISTS result_set_at TIMESTAMPTZ;
END $$;

-- rosout_warn  (신규) : rosout level>=30(WARN) 중계 로그 --------------
CREATE TABLE IF NOT EXISTS rosout_warn (
    id          BIGSERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL,
    level       SMALLINT NOT NULL,        -- 30=WARN 40=ERROR 50=FATAL
    node_name   TEXT,
    msg         TEXT
);
CREATE INDEX IF NOT EXISTS idx_rosout_ts ON rosout_warn (ts DESC);

-- joint_snapshots (재사용) : Spot arm0 + 다리 관절, 10Hz 다운샘플 ---------
CREATE TABLE IF NOT EXISTS joint_snapshots (
    id        BIGSERIAL PRIMARY KEY,
    robot_id  TEXT NOT NULL REFERENCES robots(robot_id),
    ts        TIMESTAMPTZ NOT NULL,
    arm_q     REAL[],                     -- Spot arm0 (/dsr01/joint_states)
    leg_q     REAL[]                      -- Spot 다리 (/robot/leg_joint_states)
);
CREATE INDEX IF NOT EXISTS idx_js_robot_ts_brin
    ON joint_snapshots USING BRIN (robot_id, ts);

-- ── 스키마 마이그레이션: 구 배포 드리프트 자가치유 (멱등) ─────────────────
-- 과거 joint_snapshots 컬럼은 q/qd 였음. `CREATE TABLE IF NOT EXISTS` 는
-- 기존 테이블을 변경하지 않으므로 구 DB 에서는 db_writer(arm_q/leg_q)와
-- 불일치 → "column arm_q does not exist" 로 flush 실패. 이 블록이
-- schema.sql 재실행 시(restart_full/start 가 매번 적용) 자동 정합한다.
-- 신규 DB 에서는 전부 no-op(멱등).
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name = 'joint_snapshots' AND column_name = 'q') THEN
    ALTER TABLE joint_snapshots RENAME COLUMN q TO arm_q;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name = 'joint_snapshots' AND column_name = 'qd') THEN
    ALTER TABLE joint_snapshots RENAME COLUMN qd TO leg_q;
  END IF;
END $$;
ALTER TABLE joint_snapshots ADD COLUMN IF NOT EXISTS arm_q REAL[];
ALTER TABLE joint_snapshots ADD COLUMN IF NOT EXISTS leg_q REAL[];

-- robot_state_log  (신규) : 모드/배터리/보행상태 스냅샷 ----------------
CREATE TABLE IF NOT EXISTS robot_state_log (
    id        BIGSERIAL PRIMARY KEY,
    robot_id  TEXT NOT NULL REFERENCES robots(robot_id),
    ts        TIMESTAMPTZ NOT NULL,
    mode      TEXT,                       -- IDLE|PATROL|AIM|FIRE
    gait      TEXT,
    battery   REAL,
    waypoint  INT,
    extra     JSONB
);
CREATE INDEX IF NOT EXISTS idx_rsl_robot_ts ON robot_state_log (robot_id, ts DESC);

-- ============================================================================
-- DMZ Sentry 통합 (2026-05-20) — alerts / patrol_state_log / intruder_states_log
-- ============================================================================

-- alerts : YOLO 정책(alert_conf + cooldown) 통과 사람 감지 -------------
CREATE TABLE IF NOT EXISTS alerts (
    id          BIGSERIAL PRIMARY KEY,
    robot_id    TEXT NOT NULL REFERENCES robots(robot_id),
    ts          TIMESTAMPTZ NOT NULL,
    level       TEXT NOT NULL,           -- ALERT|WARN|INFO
    event       TEXT NOT NULL,           -- person_detected_near_fence …
    confidence  REAL NOT NULL,
    bbox_xyxy   JSONB,                   -- [x1,y1,x2,y2]
    count       INT NOT NULL DEFAULT 1,
    ack         BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_alerts_robot_ts ON alerts (robot_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_ack      ON alerts (ack) WHERE ack = FALSE;

-- patrol_state_log : nav2_patrol 상태머신 변경 시 1행 ------------------
CREATE TABLE IF NOT EXISTS patrol_state_log (
    id                BIGSERIAL PRIMARY KEY,
    robot_id          TEXT NOT NULL REFERENCES robots(robot_id),
    ts                TIMESTAMPTZ NOT NULL,
    mode              TEXT NOT NULL,     -- IDLE|PATROL|HOME|ALERT_STOP|STOPPED
    current_waypoint  INT,
    pose_x            REAL,
    pose_y            REAL,
    pose_yaw          REAL
);
CREATE INDEX IF NOT EXISTS idx_psl_robot_ts ON patrol_state_log (robot_id, ts DESC);

-- intruder_states_log : 침입자 ground-truth 1Hz 다운샘플 --------------
CREATE TABLE IF NOT EXISTS intruder_states_log (
    id           BIGSERIAL PRIMARY KEY,
    ts           TIMESTAMPTZ NOT NULL,
    intruder_id  TEXT NOT NULL,
    x            REAL NOT NULL,
    y            REAL NOT NULL,
    z            REAL,
    label        TEXT
);
CREATE INDEX IF NOT EXISTS idx_isl_ts ON intruder_states_log USING BRIN (ts);

-- ============================================================================
-- 보관 정책 (← 0002_retention_policy.sql 적응)
-- ============================================================================
DROP FUNCTION IF EXISTS cleanup_old_data();
CREATE OR REPLACE FUNCTION cleanup_old_data() RETURNS void AS $$
BEGIN
    DELETE FROM gps_track             WHERE ts < now() - INTERVAL '14 days';
    DELETE FROM joint_snapshots       WHERE ts < now() - INTERVAL '14 days';
    DELETE FROM rosout_warn           WHERE ts < now() - INTERVAL '30 days';
    DELETE FROM intruder_detections   WHERE ts < now() - INTERVAL '30 days';
    DELETE FROM robot_state_log       WHERE ts < now() - INTERVAL '30 days';
    DELETE FROM patrol_state_log      WHERE ts < now() - INTERVAL '30 days';
    DELETE FROM intruder_states_log   WHERE ts < now() - INTERVAL '14 days';
    DELETE FROM alerts                WHERE ts < now() - INTERVAL '60 days' AND ack = TRUE;
    -- patrol_runs / patrol_events / fire_events : 1년 보관 (삭제 안 함)
END;
$$ LANGUAGE plpgsql;

-- 분석 뷰: 순찰 요약
CREATE OR REPLACE VIEW v_patrol_summary AS
SELECT r.id, r.robot_id, r.start_ts, r.end_ts, r.duration_ms, r.success, r.dist_m,
       (SELECT count(*) FROM patrol_events e WHERE e.run_id = r.id)        AS event_count,
       (SELECT count(*) FROM fire_events f WHERE f.ts BETWEEN r.start_ts
            AND COALESCE(r.end_ts, now()) AND f.robot_id = r.robot_id)     AS fire_count
FROM patrol_runs r;
