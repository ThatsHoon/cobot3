"""static TF 보강 사이드카 (Nav2 + Lichtblick URDF 트리 정합).

2개 static TF 발행:
1. `world → odom` (identity) — camera_publisher OG 는 `world → Go2` 만 발행.
   Nav2 가 `global_frame=world` + `odom_topic=/robot/odom (frame_id=odom)`
   으로 동작하려면 `world → odom` 연결 필수.
2. `Go2 → base` (identity) — go2.urdf 의 root link 이름은 "base" 인데
   Isaac OG TF 는 "Go2" frame 만 발행. Lichtblick 3D!go2 패널이 URDF mesh
   를 "base" frame 에서 lookup 하므로 alias 가 필요. identity 정합.

향후 SLAM/AMCL 도입 시 1)은 비활성화, 2)는 유지.

실행:
    python3 main_side/world_odom_tf_pub.py
"""
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import TransformStamped
from tf2_ros import StaticTransformBroadcaster


def _identity_tf(parent: str, child: str, stamp) -> TransformStamped:
    m = TransformStamped()
    m.header.stamp = stamp
    m.header.frame_id = parent
    m.child_frame_id = child
    m.transform.translation.x = 0.0
    m.transform.translation.y = 0.0
    m.transform.translation.z = 0.0
    m.transform.rotation.x = 0.0
    m.transform.rotation.y = 0.0
    m.transform.rotation.z = 0.0
    m.transform.rotation.w = 1.0
    return m


class WorldOdomTfPub(Node):
    def __init__(self):
        super().__init__("world_odom_tf_pub")
        self._tf = StaticTransformBroadcaster(self)
        stamp = self.get_clock().now().to_msg()
        self._tf.sendTransform([
            _identity_tf("world", "odom", stamp),    # Nav2 TF 보강
            _identity_tf("Go2", "base", stamp),      # URDF alias (Lichtblick)
        ])
        self.get_logger().info(
            "static TF latched: world→odom + Go2→base (URDF alias)")


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
