"""T11 DB: alerts/patrol_state_log/intruder_states_log 컬럼 스키마 검증.

psycopg2 없는 환경 대비 psql CLI subprocess 사용. PostgreSQL 미가동 시 skip.
"""
import json
import subprocess

import pytest


def _psql(sql, db="cobot3"):
    r = subprocess.run(
        ["psql", "-d", db, "-At", "-F", "|", "-c", sql],
        capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        return None, r.stderr
    return r.stdout.strip(), None


@pytest.fixture(scope="module", autouse=True)
def _ensure_db():
    r = subprocess.run(["pg_isready", "-q"], timeout=3)
    if r.returncode != 0:
        pytest.skip("PostgreSQL 미가동 — pg_isready 실패")
    out, err = _psql("SELECT 1")
    if err:
        pytest.skip(f"cobot3 DB 접속 실패: {err}")


def _cols(table):
    out, err = _psql(
        f"SELECT column_name||':'||data_type FROM information_schema.columns "
        f"WHERE table_name='{table}' ORDER BY ordinal_position")
    assert err is None, err
    cols = {}
    for line in out.splitlines():
        if not line:
            continue
        k, t = line.split(":", 1)
        cols[k] = t
    return cols


def test_alerts_columns():
    cols = _cols("alerts")
    assert cols, "alerts 테이블 미생성 — psql -f sub1_side/db/schema.sql 실행 필요"
    expected = {
        "id": "bigint",
        "robot_id": "text",
        "ts": "timestamp with time zone",
        "level": "text",
        "event": "text",
        "confidence": "real",
        "bbox_xyxy": "jsonb",
        "count": "integer",
        "ack": "boolean",
    }
    for k, t in expected.items():
        assert k in cols, f"alerts.{k} 누락"
        assert cols[k] == t, f"alerts.{k} 타입 {cols[k]} ≠ {t}"


def test_patrol_state_log_columns():
    cols = _cols("patrol_state_log")
    assert cols, "patrol_state_log 미생성"
    expected = {
        "id": "bigint",
        "robot_id": "text",
        "ts": "timestamp with time zone",
        "mode": "text",
        "current_waypoint": "integer",
        "pose_x": "real",
        "pose_y": "real",
        "pose_yaw": "real",
    }
    for k, t in expected.items():
        assert k in cols, f"patrol_state_log.{k} 누락"
        assert cols[k] == t


def test_intruder_states_log_columns():
    cols = _cols("intruder_states_log")
    assert cols, "intruder_states_log 미생성"
    expected = {
        "id": "bigint",
        "ts": "timestamp with time zone",
        "intruder_id": "text",
        "x": "real",
        "y": "real",
        "z": "real",
        "label": "text",
    }
    for k, t in expected.items():
        assert k in cols, f"intruder_states_log.{k} 누락"
        assert cols[k] == t


def test_alerts_insert_select_roundtrip():
    bbox = json.dumps([1.0, 2.0, 3.0, 4.0])
    out, err = _psql(
        f"INSERT INTO alerts (robot_id, ts, level, event, confidence, "
        f"bbox_xyxy, count, ack) VALUES "
        f"('gp0', NOW(), 'ALERT', 'test_unit', 0.77, '{bbox}'::jsonb, "
        f"1, FALSE) RETURNING id")
    assert err is None, err
    # RETURNING 출력 + INSERT 메시지 — 첫 줄이 id
    new_id = int(out.strip().splitlines()[0])
    try:
        row, err = _psql(
            f"SELECT level||'|'||confidence::text||'|'||ack::text "
            f"FROM alerts WHERE id={new_id}")
        assert err is None
        assert row == "ALERT|0.77|false", f"row mismatch: {row}"
    finally:
        _psql(f"DELETE FROM alerts WHERE id={new_id}")


def test_cleanup_old_data_function_exists():
    out, err = _psql(
        "SELECT 1 FROM pg_proc WHERE proname='cleanup_old_data'")
    assert err is None
    assert out.strip() == "1", "cleanup_old_data() 함수 없음"
