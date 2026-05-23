"""T2 ROS round-trip: /alerts JSON 형식 + nav2_patrol ALERT_STOP 반응."""
import json
import time

import pytest
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

from _ros_helpers import setup_test_env, spawn_node, spin_for


@pytest.fixture(scope="module", autouse=True)
def _rclpy_ctx():
    setup_test_env()
    rclpy.init()
    yield
    rclpy.shutdown()


def test_alert_json_schema_round_trip():
    """직접 publisher/subscriber 로 /alerts JSON 표준 키 round-trip 확인."""
    received = []

    class N(Node):
        def __init__(self):
            super().__init__("test_alert_node")
            rel = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, depth=10)
            self.pub = self.create_publisher(String, "/alerts", rel)
            self.create_subscription(String, "/alerts",
                                     lambda m: received.append(m.data), rel)

    n = N()
    spin_for(n, 0.5)        # discovery
    payload = {
        "level": "ALERT",
        "event": "person_detected_near_fence",
        "confidence": 0.78,
        "bbox_xyxy": [10.0, 20.0, 110.0, 220.0],
        "count": 1,
        "action": "report_and_track",
    }
    m = String()
    m.data = json.dumps(payload)
    n.pub.publish(m)
    spin_for(n, 1.5, predicate=lambda: bool(received))
    n.destroy_node()
    assert received, "/alerts 자기수신 실패"
    out = json.loads(received[0])
    for k in ("level", "event", "confidence", "bbox_xyxy", "count"):
        assert k in out, f"alert 키 {k} 누락"
    assert out["confidence"] == 0.78
    assert out["bbox_xyxy"][2] == 110.0


def test_patrol_enters_alert_stop_on_alert():
    """nav2_patrol 노드를 subprocess 로 띄우고 /alerts 발행 → /patrol_state
    mode 가 ALERT_STOP 으로 전환되는지 확인."""
    received_states = []

    class N(Node):
        def __init__(self):
            super().__init__("test_patrol_alert_obs")
            rel = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, depth=10)
            self.alert_pub = self.create_publisher(String, "/alerts", rel)
            self.mission_pub = self.create_publisher(String,
                                                     "/mission_command", rel)
            self.create_subscription(String, "/patrol_state",
                                     lambda m: received_states.append(m.data),
                                     rel)

    with spawn_node("sub1_side/server/nav2_patrol.py"):
        n = N()
        # 노드가 publisher 등록할 시간 (≥1s) — patrol 5Hz 발행
        spin_for(n, 3.0, predicate=lambda: len(received_states) > 0)
        assert received_states, "/patrol_state 초기 수신 실패"

        # 1) 먼저 sortie 로 PATROL 모드 진입 시도
        m = String(); m.data = "sortie"
        n.mission_pub.publish(m)
        # PATROL 또는 WAITING_FOR_NAV2 (Nav2 미가동) 어느 쪽이든 IDLE 이 아니어야 함
        spin_for(n, 2.0, predicate=lambda: any(
            json.loads(s).get("mode") in ("PATROL", "WAITING_FOR_NAV2", "HOME")
            for s in received_states[-10:]))

        # 2) alert 발행 → ALERT_STOP 전환 기대
        prior_len = len(received_states)
        a = String()
        a.data = json.dumps({"level": "ALERT", "event": "person_detected_near_fence",
                             "confidence": 0.85, "bbox_xyxy": [0, 0, 50, 50],
                             "count": 1})
        n.alert_pub.publish(a)
        ok = spin_for(n, 3.0, predicate=lambda: any(
            json.loads(s).get("mode") == "ALERT_STOP"
            for s in received_states[prior_len:]))
        n.destroy_node()
        assert ok, ("/patrol_state mode=ALERT_STOP 미관측 — 최근 5개: " +
                    str([json.loads(s).get("mode") for s in received_states[-5:]]))
