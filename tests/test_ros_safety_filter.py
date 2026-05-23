"""T4 ROS round-trip: cmd_vel_safety_filter 노드와 통신해 동시 통과 검증."""
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


def test_linear_forwards():
    with spawn_node("main_side/cmd_vel_safety_filter.py"):
        client = FilterClient()
        assert _wait_pub_match(client, "/robot/cmd_vel", 1, 10.0), "discovery 실패"
        for _ in range(5):
            client.send(0.5, 0.0)
            spin_for(client, 0.1)
        assert client.received, "/robot/cmd_vel 미수신"
        out = client.received[-1]
        assert abs(out.linear.x - 0.5) < 1e-3
        assert out.angular.z == 0.0
        client.destroy_node()


def test_simultaneous_linear_and_angular_over_wire():
    """linear + angular 동시 발행 시 둘 다 통과해야 한다 (곡선 주행 지원)."""
    with spawn_node("main_side/cmd_vel_safety_filter.py"):
        client = FilterClient()
        assert _wait_pub_match(client, "/robot/cmd_vel", 1, 10.0)
        for _ in range(5):
            client.send(0.5, 0.5)
            spin_for(client, 0.1)
        assert client.received
        out = client.received[-1]
        assert abs(out.linear.x - 0.5) < 1e-3
        assert abs(out.angular.z - 0.5) < 1e-3
        client.destroy_node()


def test_max_linear_clamped_over_wire():
    with spawn_node("main_side/cmd_vel_safety_filter.py"):
        client = FilterClient()
        assert _wait_pub_match(client, "/robot/cmd_vel", 1, 10.0)
        for _ in range(5):
            client.send(10.0, 0.0)
            spin_for(client, 0.1)
        out = client.received[-1]
        assert abs(out.linear.x - 1.2) < 1e-3   # default max_linear_x=1.2
        client.destroy_node()
