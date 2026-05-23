"""T10 ROS round-trip: world→odom static TF 발행 확인."""
import pytest
import rclpy
from rclpy.node import Node
from rclpy.qos import (DurabilityPolicy, HistoryPolicy, QoSProfile,
                       ReliabilityPolicy)
from tf2_msgs.msg import TFMessage

from _ros_helpers import setup_test_env, spawn_node, spin_for


@pytest.fixture(scope="module", autouse=True)
def _rclpy_ctx():
    setup_test_env()
    rclpy.init()
    yield
    rclpy.shutdown()


def test_world_odom_static_tf_published():
    received = []

    class TFSub(Node):
        def __init__(self):
            super().__init__("test_tf_sub")
            qos = QoSProfile(
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
                history=HistoryPolicy.KEEP_LAST, depth=10)
            self.create_subscription(TFMessage, "/tf_static", self._cb, qos)

        def _cb(self, msg):
            received.extend(msg.transforms)

    with spawn_node("main_side/world_odom_tf_pub.py"):
        sub = TFSub()
        spin_for(sub, 5.0,
                 predicate=lambda: any(t.header.frame_id == "world"
                                       and t.child_frame_id == "odom"
                                       for t in received))
        sub.destroy_node()

    matches = [t for t in received
               if t.header.frame_id == "world" and t.child_frame_id == "odom"]
    assert matches, f"world→odom transform 미수신 (총 {len(received)} TF)"
    t = matches[-1]
    # identity transform 검증
    assert abs(t.transform.translation.x) < 1e-6
    assert abs(t.transform.translation.y) < 1e-6
    assert abs(t.transform.translation.z) < 1e-6
    assert abs(t.transform.rotation.w - 1.0) < 1e-6
