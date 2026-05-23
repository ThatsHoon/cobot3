"""P2 단위: nav2_patrol._on_landmarks 의 zone 분기 (dmz vs cube)."""
import json
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def patrol():
    import rclpy  # noqa
    import nav2_patrol as mod

    inst = mod.Nav2PatrolController.__new__(mod.Nav2PatrolController)
    inst._mission_topic = "/mission_command"
    inst._home = (0.0, 0.0)
    inst._patrol_waypoints = [(0.0, 0.0), (1.0, 0.0)]
    inst._landmarks_received = False
    inst.get_logger = MagicMock(return_value=MagicMock())
    return inst, mod


def _mk(s):
    from std_msgs.msg import String
    m = String()
    m.data = s
    return m


def test_dmz_zone_uses_dmz_waypoints(patrol):
    inst, mod = patrol
    payload = {
        "zone": "dmz",
        "cube": {"x": -714, "y": 952, "z": 30},
        "cone": {"x": -937, "y": 938, "z": 0},
        "dmz_home": {"x": 0.0, "y": 0.0, "z": 0.0},
        "dmz_cone": {"x": 24.0, "y": -12.0, "z": 0.0},
        "dmz_patrol_w": {"x": -24.0, "y": -12.0, "z": 0.0},
        "dmz_fence": [{"x": -40, "y": 16, "z": 0}, {"x": 40, "y": 16, "z": 0}],
    }
    inst._on_landmarks(_mk(json.dumps(payload)))
    assert inst._home == (0.0, 0.0)
    assert (24.0, -12.0) in inst._patrol_waypoints
    assert (-24.0, -12.0) in inst._patrol_waypoints
    # gp_scene 의 cube/cone 좌표는 patrol 에 안 들어가야
    assert (-714.0, 952.0) not in inst._patrol_waypoints
    assert (-937.0, 938.0) not in inst._patrol_waypoints
    assert getattr(inst, "_zone", None) == "dmz"


def test_cube_zone_uses_cube_cone(patrol):
    inst, mod = patrol
    payload = {
        "zone": "cube",
        "cube": {"x": -714.32, "y": 952.93, "z": 30.57},
        "cone": {"x": -937.07, "y": 938.98, "z": 0.0},
        "dmz_home": {"x": 0.0, "y": 0.0, "z": 0.0},
        "dmz_cone": {"x": 24.0, "y": -12.0, "z": 0.0},
    }
    inst._on_landmarks(_mk(json.dumps(payload)))
    assert inst._home == (-714.32, 952.93)
    assert (-937.07, 938.98) in inst._patrol_waypoints
    # DMZ 좌표는 안 들어가야
    assert (24.0, -12.0) not in inst._patrol_waypoints
    assert getattr(inst, "_zone", None) == "cube"


def test_zone_missing_defaults_to_cube(patrol):
    """payload 에 zone 키 없으면 cube 폴백."""
    inst, mod = patrol
    payload = {
        "cube": {"x": -714, "y": 952, "z": 30},
        "cone": {"x": -937, "y": 938, "z": 0},
    }
    inst._on_landmarks(_mk(json.dumps(payload)))
    assert inst._home == (-714.0, 952.0)
    assert (-937.0, 938.0) in inst._patrol_waypoints
