"""static TF 보강 사이드카 (Nav2 + Lichtblick URDF 트리 정합).

2개 static TF 발행:
1. `world → odom` — odom frame 의 origin 을 Go2 spawn world 좌표로 align.
   WHY: IsaacComputeOdometry 가 /robot/odom 에 발행하는 (x,y,z) 는 spawn
   기준 누적 변위. 우리 Go2 spawn = (212.8, 890.53, 5.0). world→odom 가
   identity 면 odom 토픽 (0.29, 2.22, …) 가 그대로 world 좌표로 잘못 해석
   → Nav2 가 robot 위치를 (0.29, 2.22) 로 추정 → goal (287, 1129) 향해
   heading 정렬만 무한 (vx=0, wz=0.8) → 제자리 회전 무한 (2026-05-21 사용자
   보고). 해결: world→odom translate = spawn 좌표 → odom 누적 + offset 이
   world 좌표와 일치.
   env GP_GO2_SPAWN_X / Y / Z 로 override 가능 (camera_publisher 의 spawn
   과 일치시키기 위해).
2. `Go2 → base` (identity) — go2.urdf 의 root link "base" 와 Isaac OG TF
   frame "Go2" alias. Lichtblick URDF mesh lookup 위함.

향후 SLAM/AMCL 도입 시 1)은 비활성화 (map→odom 가 자동 발행됨).

실행:
    python3 main_side/world_odom_tf_pub.py
"""
import os

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import TransformStamped
from tf2_ros import StaticTransformBroadcaster


SPAWN_X = float(os.environ.get("GP_GO2_SPAWN_X", "212.8"))
SPAWN_Y = float(os.environ.get("GP_GO2_SPAWN_Y", "890.53"))
SPAWN_Z = float(os.environ.get("GP_GO2_SPAWN_Z", "5.0"))


def _tf(parent: str, child: str, stamp,
        tx: float = 0.0, ty: float = 0.0, tz: float = 0.0) -> TransformStamped:
    m = TransformStamped()
    m.header.stamp = stamp
    m.header.frame_id = parent
    m.child_frame_id = child
    m.transform.translation.x = tx
    m.transform.translation.y = ty
    m.transform.translation.z = tz
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
            # world→odom: spawn 위치만큼 offset (Nav2 robot pose 정합)
            _tf("world", "odom", stamp, SPAWN_X, SPAWN_Y, SPAWN_Z),
            # Go2→base: URDF alias (Lichtblick)
            _tf("Go2", "base", stamp),
        ])
        self.get_logger().info(
            f"static TF latched: world→odom ({SPAWN_X:.2f},{SPAWN_Y:.2f},"
            f"{SPAWN_Z:.2f}) + Go2→base (URDF alias)")


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
