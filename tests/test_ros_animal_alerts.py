"""P3 ROS round-trip: /animal_alerts JSON + nav2_patrol ALERT_STOP 반응 검증."""
import json

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


def test_animal_alert_json_schema_round_trip():
    received = []

    class N(Node):
        def __init__(self):
            super().__init__("test_animal_alert_node")
            rel = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, depth=10)
            self.pub = self.create_publisher(String, "/animal_alerts", rel)
            self.create_subscription(String, "/animal_alerts",
                                     lambda m: received.append(m.data), rel)

    n = N()
    spin_for(n, 0.5)
    payload = {
        "level": "ALERT",
        "event": "animal_detected",
        "label": "bear",
        "confidence": 0.83,
        "bbox_xyxy": [10.0, 20.0, 110.0, 220.0],
        "count": 1,
        "action": "monitor",
    }
    m = String()
    m.data = json.dumps(payload)
    n.pub.publish(m)
    spin_for(n, 1.5, predicate=lambda: bool(received))
    n.destroy_node()
    assert received, "/animal_alerts 자기수신 실패"
    out = json.loads(received[0])
    for k in ("level", "event", "label", "confidence", "bbox_xyxy", "count"):
        assert k in out, f"animal alert 키 {k} 누락"
    assert out["event"] == "animal_detected"
    assert out["label"] == "bear"


def test_patrol_no_animal_alert_stop():
    """nav2_patrol 은 /alerts 구독만 함 (animal_alerts 는 별도 토픽).
    동물 감지 시 patrol 정지를 원하면 ros_bridge 가 /alerts 도 같이 발행해야
    함 — 본 테스트는 현재 정책상 patrol 가 /animal_alerts 단독에는 반응하지
    않음을 명시(설계 의도)."""
    received_states = []

    class N(Node):
        def __init__(self):
            super().__init__("test_patrol_no_animal_stop")
            rel = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, depth=10)
            self.animal_pub = self.create_publisher(String, "/animal_alerts", rel)
            self.create_subscription(String, "/patrol_state",
                                     lambda m: received_states.append(m.data),
                                     rel)

    with spawn_node("sub1_side/server/nav2_patrol.py"):
        n = N()
        spin_for(n, 3.0, predicate=lambda: len(received_states) > 0)
        prior_len = len(received_states)
        a = String()
        a.data = json.dumps({"level": "ALERT", "event": "animal_detected",
                             "label": "bear", "confidence": 0.85,
                             "bbox_xyxy": [0, 0, 50, 50], "count": 1})
        n.animal_pub.publish(a)
        # 2초 spin → ALERT_STOP 으로 전환되지 않아야 함 (animal_alerts 미구독)
        spin_for(n, 2.0)
        n.destroy_node()
        recent_modes = [json.loads(s).get("mode") for s in
                        received_states[prior_len:]]
        # 어느 시점이든 mode 가 IDLE 또는 PATROL/HOME 등 — ALERT_STOP 은 없어야
        assert "ALERT_STOP" not in recent_modes, (
            "/animal_alerts 단독으로 ALERT_STOP 전환됨 — 설계와 다름. "
            f"observed: {recent_modes}")
