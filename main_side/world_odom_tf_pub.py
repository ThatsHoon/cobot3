"""world → odom static TF 발행자 (Nav2 TF 트리 보강).

cobot3 의 camera_publisher OG 는 `odom → base_link` 만 발행한다. Nav2 가
`global_frame=world` 로 동작하려면 `world → odom` 연결이 필수. 본 노드는
identity transform 을 StaticTransformBroadcaster 로 latched 1회 발행.

향후 SLAM/AMCL 도입 시 본 노드는 비활성화하고 그쪽 발행에 맡긴다.

실행:
    ros2 run rclpy_executor world_odom_tf_pub  (불가 — standalone Python)
    python3 main_side/world_odom_tf_pub.py
"""
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import TransformStamped
from tf2_ros import StaticTransformBroadcaster


class WorldOdomTfPub(Node):
    def __init__(self):
        super().__init__("world_odom_tf_pub")
        self._tf = StaticTransformBroadcaster(self)
        msg = TransformStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "world"
        msg.child_frame_id = "odom"
        msg.transform.translation.x = 0.0
        msg.transform.translation.y = 0.0
        msg.transform.translation.z = 0.0
        msg.transform.rotation.x = 0.0
        msg.transform.rotation.y = 0.0
        msg.transform.rotation.z = 0.0
        msg.transform.rotation.w = 1.0
        self._tf.sendTransform(msg)
        self.get_logger().info("world → odom static TF (identity) latched")


def main():
    rclpy.init()
    node = WorldOdomTfPub()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
