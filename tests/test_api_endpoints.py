"""T11 API: FastAPI 신규 엔드포인트 — POST/GET 동작.

sub1_side/server/.venv 에서 실행. ros_bridge 와 db_writer 는 mock 으로 교체.

실행:
  ./sub1_side/server/.venv/bin/python -m pytest tests/test_api_endpoints.py -v
"""
import os
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_REPO = Path(__file__).resolve().parents[1]
_SERVER = _REPO / "sub1_side" / "server"
if str(_SERVER) not in sys.path:
    sys.path.insert(0, str(_SERVER))


@pytest.fixture
def client(monkeypatch):
    """app.app 의 lifespan 이 실제 DB·ROS 를 띄우지 않도록 mock."""
    # ros_bridge / db_writer 모듈 단의 클래스를 mock 으로 교체
    import ros_bridge as rb_mod
    import db_writer as db_mod

    fake_ros = MagicMock(name="ros_facade")
    fake_ros.latest = {"state": {}, "gps": {}, "odom": {}, "leg_q": [],
                       "intruders": [], "patrol_state": {}, "landmarks": {}}
    fake_ros.start = MagicMock()
    fake_ros.stop = MagicMock()
    fake_ros.pub_mission = MagicMock()
    fake_ros.pub_inspect_cmd = MagicMock()
    fake_ros.fire = MagicMock(return_value={"hit": True, "distance_m": 12.3})
    fake_ros.pub_cmd_vel = MagicMock()

    fake_db = MagicMock(name="db_facade")
    fake_db.start = AsyncMock()
    fake_db.stop = AsyncMock()
    fake_db.put = MagicMock()
    fake_db._pool = None    # /alerts/ack 등 DB 의존 경로는 503

    monkeypatch.setattr(rb_mod, "RosBridge", lambda: fake_ros)
    monkeypatch.setattr(db_mod, "DBWriter", lambda: fake_db)

    # YoloInfer 는 무관 — graceful 비활성
    # app 모듈 재로드 (전역 db/ros 인스턴스 재바인딩)
    if "app" in sys.modules:
        del sys.modules["app"]
    import app as app_mod

    # API_KEY 비우기 → require_key 통과
    monkeypatch.setattr(app_mod.config, "API_KEY", "")

    from fastapi.testclient import TestClient
    with TestClient(app_mod.app) as c:
        c.fake_ros = fake_ros
        c.fake_db = fake_db
        yield c


def test_mission_command_valid(client):
    r = client.post("/missions/command", json={"command": "sortie"})
    assert r.status_code == 200
    assert r.json()["command"] == "sortie"
    client.fake_ros.pub_mission.assert_called_with("sortie")


def test_mission_command_invalid(client):
    r = client.post("/missions/command", json={"command": "nonsense"})
    assert r.status_code == 400


def test_mission_command_aliases(client):
    """start/halt/continue/rtb 같은 별칭도 통과."""
    for cmd in ("start", "halt", "continue", "rtb", "standby"):
        r = client.post("/missions/command", json={"command": cmd})
        assert r.status_code == 200, f"{cmd} 실패: {r.text}"


def test_inspect_cmd_pan(client):
    r = client.post("/robots/gp0/inspect",
                    json={"pan": 0.5, "absolute": True})
    assert r.status_code == 200
    body = r.json()
    assert body["payload"]["pan"] == 0.5
    client.fake_ros.pub_inspect_cmd.assert_called()


def test_inspect_cmd_empty_rejected(client):
    r = client.post("/robots/gp0/inspect", json={"foo": 1})
    assert r.status_code == 400


def test_inspect_cmd_look_at(client):
    r = client.post("/robots/gp0/inspect",
                    json={"look_at": [-937.0, 939.0, 1.0]})
    assert r.status_code == 200
    assert r.json()["payload"]["look_at"] == [-937.0, 939.0, 1.0]


def test_missions_state(client):
    """ros.latest 의 patrol_state/intruders/landmarks 가 JSON 으로 노출."""
    client.fake_ros.latest["patrol_state"] = {"mode": "PATROL"}
    client.fake_ros.latest["intruders"] = [{"id": "x", "x": 1, "y": 2}]
    client.fake_ros.latest["landmarks"] = {"cube": {"x": 0, "y": 0, "z": 0}}
    r = client.get("/missions/state")
    assert r.status_code == 200
    body = r.json()
    assert body["patrol_state"]["mode"] == "PATROL"
    assert body["intruders"][0]["id"] == "x"
    assert body["landmarks"]["cube"]["y"] == 0


def test_alert_ack_db_unavailable(client):
    """db._pool is None → 503 (가용 시 별도 통합 테스트로 검증)."""
    r = client.post("/alerts/1/ack")
    assert r.status_code == 503


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "ok"
