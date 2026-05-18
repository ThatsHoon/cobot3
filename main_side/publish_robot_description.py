#!/usr/bin/env python3
"""Publishes /robot_description (std_msgs/String, transient_local QoS)
so Foxglove/Lichtblick 3D panel can render the Spot mesh.

TF is already published by Isaac Sim (ROS2PublishTransformTree).
This node only handles the URDF → robot_description side.
"""
import os
import sys
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from std_msgs.msg import String

URDF_PATH = os.path.join(os.path.dirname(__file__), "spot_isaac.urdf")
DOMAIN = int(os.environ.get("ROS_DOMAIN_ID", "130"))


class RobotDescriptionPublisher(Node):
    def __init__(self, urdf_str: str):
        super().__init__("spot_robot_description_pub")
        qos = QoSProfile(
            depth=1,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            reliability=ReliabilityPolicy.RELIABLE,
        )
        self._pub = self.create_publisher(String, "/robot_description", qos)
        msg = String(data=urdf_str)
        self._pub.publish(msg)
        self.get_logger().info(f"/robot_description 발행 완료 ({len(urdf_str)} bytes)")
        # Re-publish every 5 s for late-joining subscribers
        self.create_timer(5.0, lambda: self._pub.publish(msg))


def main():
    if not os.path.exists(URDF_PATH):
        print(f"[robot_desc] URDF 없음: {URDF_PATH}", file=sys.stderr)
        sys.exit(1)
    with open(URDF_PATH) as f:
        urdf = f.read()
    rclpy.init()
    node = RobotDescriptionPublisher(urdf)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
