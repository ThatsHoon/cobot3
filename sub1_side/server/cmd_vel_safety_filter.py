"""Nav2 cmd_vel 안전 필터 — cobot3 Go2 적용 (DMZ Sentry 원본 골격).

ANYmal/Go2 같은 사족 로봇은 회전 중 동시 선형 이동을 안정적으로 못하므로
DRIVE / TURN 두 모드로 갈라 한 번에 하나만 전달한다.

I/O:
- 구독: /cmd_vel_nav2_raw (Twist)  — Nav2 velocity_smoother 출력
- 발행: /robot/cmd_vel (Twist)     — Go2 WTW 정책 입력 (camera_publisher OG)

실행:
    python3 sub1_side/server/cmd_vel_safety_filter.py
"""
import math

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node


MODE_DRIVE = "DRIVE"
MODE_TURN = "TURN"


class CmdVelSafetyFilter(Node):
    def __init__(self) -> None:
        super().__init__("cmd_vel_safety_filter")

        self.declare_parameter("input_topic", "/cmd_vel_nav2_raw")
        self.declare_parameter("output_topic", "/robot/cmd_vel")
        self.declare_parameter("max_linear_x", 0.8)
        self.declare_parameter("max_angular_z", 0.85)
        self.declare_parameter("turn_enter_angular", 0.32)
        self.declare_parameter("turn_exit_angular", 0.10)
        self.declare_parameter("min_drive_linear", 0.08)

        input_topic = self.get_parameter("input_topic").value
        output_topic = self.get_parameter("output_topic").value
        self._max_linear_x = max(0.05, float(self.get_parameter("max_linear_x").value))
        self._max_angular_z = max(0.05, float(self.get_parameter("max_angular_z").value))
        self._turn_enter_angular = max(0.01,
            float(self.get_parameter("turn_enter_angular").value))
        self._turn_exit_angular = max(0.0,
            float(self.get_parameter("turn_exit_angular").value))
        self._min_drive_linear = max(0.0,
            float(self.get_parameter("min_drive_linear").value))
        self._mode = MODE_DRIVE

        self._pub = self.create_publisher(Twist, output_topic, 10)
        self.create_subscription(Twist, input_topic, self._on_cmd_vel, 10)
        self.get_logger().info(
            f"safety filter: {input_topic} -> {output_topic}, "
            f"max_lx={self._max_linear_x:.2f} max_wz={self._max_angular_z:.2f} "
            f"turn_in={self._turn_enter_angular:.2f} "
            f"turn_out={self._turn_exit_angular:.2f}"
        )

    def _on_cmd_vel(self, msg: Twist) -> None:
        filtered = Twist()
        # NaN/Inf 안전 가드: clamp 가 NaN 을 silently bound 값으로 치환할 수
        # 있으므로(Python min/max NaN 처리가 정의되지 않음) clamp 전에 0 으로.
        lin_raw = msg.linear.x if math.isfinite(msg.linear.x) else 0.0
        ang_raw = msg.angular.z if math.isfinite(msg.angular.z) else 0.0
        angular = self._clamp(ang_raw,
                              -self._max_angular_z, self._max_angular_z)
        linear = self._clamp(lin_raw,
                             -self._max_linear_x, self._max_linear_x)

        if self._mode == MODE_DRIVE and abs(angular) >= self._turn_enter_angular:
            self._mode = MODE_TURN
        elif self._mode == MODE_TURN and abs(angular) <= self._turn_exit_angular:
            self._mode = MODE_DRIVE

        if self._mode == MODE_TURN:
            filtered.angular.z = angular
        else:
            filtered.linear.x = (linear if abs(linear) >= self._min_drive_linear
                                 else 0.0)

        self._pub.publish(filtered)

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return float(max(low, min(high, value)))


def main(args=None) -> None:
    rclpy.init(args=args)
    node = CmdVelSafetyFilter()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
