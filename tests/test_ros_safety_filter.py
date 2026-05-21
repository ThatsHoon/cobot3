"""T4 ROS round-trip: cmd_vel_safety_filter 노드와 통신해 drive/turn 모드 검증."""
import pytest
import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy

from _ros_helpers import setup_test_env, spawn_node, spin_for


@pytest.fixture(scope="module", autouse=True)
def _rclpy_ctx():
    setup_test_env()
    rclpy.init()
    yield
    rclpy.shutdown()


class FilterClient(Node):
    def __init__(self):
        super().__init__("test_safety_filter_client")
        rel = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, depth=10)
        self.pub = self.create_publisher(Twist, "/cmd_vel_nav2_raw", rel)
        self.received = []
        self.create_subscription(Twist, "/robot/cmd_vel",
                                 lambda m: self.received.append(m), rel)

    def send(self, lin, ang):
        t = Twist()
        t.linear.x = float(lin)
        t.angular.z = float(ang)
        self.pub.publish(t)


def _wait_pub_match(node, topic, count=1, timeout=8.0):
    """publisher 가 등록될 때까지 대기 (discovery)."""
    return spin_for(
        node, timeout,
        predicate=lambda: node.count_publishers(topic) >= count)


def test_drive_mode_forwards_linear():
    with spawn_node("sub1_side/server/cmd_vel_safety_filter.py"):
        client = FilterClient()
        # discovery 대기 — /robot/cmd_vel publisher 등장까지
        assert _wait_pub_match(client, "/robot/cmd_vel", 1, 10.0), "discovery 실패"
        for _ in range(5):                # publish/sub 안정화
            client.send(0.5, 0.0)
            spin_for(client, 0.1)
        assert client.received, "/robot/cmd_vel 미수신"
        out = client.received[-1]
        assert abs(out.linear.x - 0.5) < 1e-3
        assert out.angular.z == 0.0
        client.destroy_node()


def test_turn_mode_zeros_linear():
    with spawn_node("sub1_side/server/cmd_vel_safety_filter.py"):
        client = FilterClient()
        assert _wait_pub_match(client, "/robot/cmd_vel", 1, 10.0)
        for _ in range(5):
            client.send(0.5, 0.5)         # angular ≥ 0.32 → TURN
            spin_for(client, 0.1)
        assert client.received
        out = client.received[-1]
        assert out.linear.x == 0.0
        assert abs(out.angular.z - 0.5) < 1e-3
        client.destroy_node()


def test_max_linear_clamped_over_wire():
    with spawn_node("sub1_side/server/cmd_vel_safety_filter.py"):
        client = FilterClient()
        assert _wait_pub_match(client, "/robot/cmd_vel", 1, 10.0)
        for _ in range(5):
            client.send(10.0, 0.0)
            spin_for(client, 0.1)
        out = client.received[-1]
        assert abs(out.linear.x - 0.8) < 1e-3
        client.destroy_node()
