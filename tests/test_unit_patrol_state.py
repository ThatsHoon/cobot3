"""T3 단위: nav2_patrol.Nav2PatrolController 상태머신.

rclpy 의존부(create_publisher/create_subscription/create_timer 등) 는
__new__ 로 우회한 인스턴스에 mock 주입해 단위 검증.
"""
import json
import time
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def patrol():
    import rclpy  # noqa
    import nav2_patrol as mod

    inst = mod.Nav2PatrolController.__new__(mod.Nav2PatrolController)
    inst._mission_topic = "/mission_command"
    inst._alerts_topic = "/alerts"
    inst._odom_topic = "/robot/odom"
    inst._state_topic = "/patrol_state"
    inst._cmd_vel_topic = "/robot/cmd_vel"
    inst._landmarks_topic = "/scene/landmarks"
    inst._action_name = "navigate_to_pose"
    inst._global_frame = "world"
    inst._home = (-714.32, 952.93)
    inst._patrol_waypoints = [inst._home, (-937.07, 938.98)]
    inst._alert_hold_seconds = 6.0
    inst._mode = mod.MissionMode.IDLE
    inst._resume_mode = mod.MissionMode.PATROL
    inst._pose = None
    inst._current_goal = None
    inst._route_queue = []
    inst._next_patrol_index = 1
    inst._goal_handle = None
    inst._last_alert_time = 0.0
    inst._landmarks_received = False
    inst._nav_client = MagicMock()
    inst._nav_client.server_is_ready.return_value = True   # happy path
    # send_goal_async 는 add_done_callback 가능한 future-like 객체 필요
    fut = MagicMock()
    fut.add_done_callback = MagicMock()
    inst._nav_client.send_goal_async.return_value = fut
    inst._cmd_pub = MagicMock()
    inst._state_pub = MagicMock()
    # get_logger / get_clock 호출 대비
    inst.get_logger = MagicMock(return_value=MagicMock())
    # PoseStamped.header.stamp 는 builtin_interfaces/Time 타입 검증을 받으므로
    # 진짜 Time 인스턴스를 반환해야 한다.
    from builtin_interfaces.msg import Time
    _t = Time()
    inst.get_clock = MagicMock(return_value=MagicMock(
        now=MagicMock(return_value=MagicMock(to_msg=MagicMock(return_value=_t)))))
    return inst, mod


def _mk(data: str):
    from std_msgs.msg import String
    m = String()
    m.data = data
    return m


def test_sortie_transitions_to_patrol(patrol):
    inst, mod = patrol
    inst._on_mission(_mk("sortie"))
    assert inst._mode == mod.MissionMode.PATROL
    assert inst._resume_mode == mod.MissionMode.PATROL
    # _send_next_goal 이 큐에서 1개 pop → _current_goal 채워짐
    assert inst._current_goal is not None
    inst._nav_client.send_goal_async.assert_called()


def test_home_transitions(patrol):
    inst, mod = patrol
    inst._on_mission(_mk("home"))
    assert inst._mode == mod.MissionMode.HOME
    assert inst._current_goal == inst._home
    inst._nav_client.send_goal_async.assert_called()


def test_stop_clears_route(patrol):
    inst, mod = patrol
    inst._route_queue = [(-1.0, -1.0)]
    inst._on_mission(_mk("stop"))
    assert inst._mode == mod.MissionMode.STOPPED
    assert inst._route_queue == []
    inst._cmd_pub.publish.assert_called()    # stop twist


def test_idle_clears_route(patrol):
    inst, mod = patrol
    inst._route_queue = [(-1.0, -1.0)]
    inst._on_mission(_mk("idle"))
    assert inst._mode == mod.MissionMode.IDLE
    assert inst._route_queue == []


def test_unknown_command_warns(patrol):
    inst, mod = patrol
    inst._on_mission(_mk("nonsense"))
    inst.get_logger().warn.assert_called()
    assert inst._mode == mod.MissionMode.IDLE


def test_alert_stops_patrol_and_saves_resume_mode(patrol):
    inst, mod = patrol
    inst._mode = mod.MissionMode.PATROL
    inst._on_alert(_mk(json.dumps({"confidence": 0.78})))
    assert inst._mode == mod.MissionMode.ALERT_STOP
    assert inst._resume_mode == mod.MissionMode.PATROL
    inst._cmd_pub.publish.assert_called()    # stop


def test_alert_during_alert_does_not_overwrite_resume(patrol):
    inst, mod = patrol
    inst._mode = mod.MissionMode.PATROL
    inst._on_alert(_mk(json.dumps({"confidence": 0.7})))
    inst._on_alert(_mk(json.dumps({"confidence": 0.9})))
    assert inst._resume_mode == mod.MissionMode.PATROL  # IDLE 로 덮이지 않음


def test_resume_during_alert_returns_to_saved_mode(patrol):
    inst, mod = patrol
    inst._mode = mod.MissionMode.PATROL
    inst._on_alert(_mk(json.dumps({"confidence": 0.7})))
    assert inst._mode == mod.MissionMode.ALERT_STOP
    inst._on_mission(_mk("resume"))
    assert inst._mode == mod.MissionMode.PATROL


def test_landmarks_update_home_and_waypoints(patrol):
    """B5 수정 후: fence 좌표는 patrol_waypoints 에 포함 안 함 (gp_scene 의
    /World/Fence/* prim 이 비실용 좌표를 잡는 문제 회피). cube↔cone 만."""
    inst, mod = patrol
    payload = {
        "cube": {"x": 100.0, "y": 200.0, "z": 0.0},
        "cone": {"x": 110.0, "y": 220.0, "z": 0.0},
        "fence": [{"x": 105.0, "y": 210.0, "z": 0.0}],
    }
    inst._on_landmarks(_mk(json.dumps(payload)))
    assert inst._landmarks_received is True
    assert abs(inst._home[0] - 100.0) < 1e-6
    assert abs(inst._home[1] - 200.0) < 1e-6
    assert (110.0, 220.0) in inst._patrol_waypoints
    # fence 좌표는 무시되어야 함
    assert (105.0, 210.0) not in inst._patrol_waypoints
    # patrol_waypoints = [home, cone] 만
    assert inst._patrol_waypoints == [(100.0, 200.0), (110.0, 220.0)]


def test_landmarks_invalid_json_safe(patrol):
    inst, mod = patrol
    inst._on_landmarks(_mk("not-json-{{"))
    assert inst._landmarks_received is False    # 무영향
    inst.get_logger().warn.assert_called()


def test_set_patrol_route_picks_nearest(patrol):
    inst, mod = patrol
    inst._patrol_waypoints = [inst._home, (10.0, 10.0), (-10.0, -10.0)]
    inst._pose = (-9.0, -9.0, 0.0)
    inst._set_patrol_route()
    # 가장 가까운 (-10,-10) 가 첫 타겟
    assert inst._route_queue[0] == (-10.0, -10.0)


def test_waiting_for_nav2_when_server_not_ready(patrol):
    inst, mod = patrol
    inst._nav_client.server_is_ready.return_value = False
    inst._on_mission(_mk("sortie"))
    # 초기 mode 는 PATROL 로 들어가지만 _send_next_goal 에서 미준비 감지 → WAITING
    assert inst._mode == mod.MissionMode.WAITING_FOR_NAV2


def test_publish_state_format(patrol):
    inst, mod = patrol
    inst._mode = mod.MissionMode.PATROL
    inst._pose = (1.0, 2.0, 0.5)
    inst._current_goal = (3.0, 4.0)
    inst._publish_state()
    msg = inst._state_pub.publish.call_args.args[0]
    payload = json.loads(msg.data)
    assert payload["mode"] == "PATROL"
    assert payload["pose"]["x"] == 1.0 and payload["pose"]["yaw"] == 0.5
    assert payload["waypoint"] == {"x": 3.0, "y": 4.0}
    assert "home" in payload and "route" in payload
