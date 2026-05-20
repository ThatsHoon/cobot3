"""Nav2 cmd_vel 안전 필터 — cobot3 Go2 적용.

ANYmal/Go2 같은 사족 로봇은 회전 중 동시 선형 이동을 안정적으로 못하므로
DRIVE / TURN 두 모드로 갈라 한 번에 하나만 전달한다.

또한 /patrol_state mode 가 PAUSED/IDLE 일 때 입력을 무시하고 Twist(0) 을
강제 발행해 velocity_smoother 잔여 발행을 덮어쓴다 (stop 버튼이 즉시 멈추도록).
WHY: stop 후 nav2_patrol 의 1-shot Twist(0) 만으로는 velocity_smoother 의
20Hz 자율 디케이가 chain 끝까지 0 으로 떨어지기까지 시간이 걸려 로봇이
멈추지 않는 버그를 차단하기 위함.

I/O:
- 구독: /cmd_vel_nav2_raw (Twist), /patrol_state (String JSON)
- 발행: /robot/cmd_vel (Twist)
"""
import json
import math

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from rclpy.qos import (DurabilityPolicy, HistoryPolicy, QoSProfile,
                       ReliabilityPolicy)
from std_msgs.msg import String


MODE_DRIVE = "DRIVE"
MODE_TURN = "TURN"

# patrol mode 가 이 집합에 들면 Nav2 입력을 무시하고 Twist(0) 으로 강제 발행.
# 2026-05-20 fix: IDLE 제거 — 사용자 teleop(BaseMovement·DS) 가 IDLE 에서
# 자유 발행 가능해야 함. PAUSED 만 mute (정지 버튼 보호).
MUTE_MODES = {"PAUSED"}


class CmdVelSafetyFilter(Node):
    def __init__(self) -> None:
        super().__init__("cmd_vel_safety_filter")

        self.declare_parameter("input_topic", "/cmd_vel_nav2_raw")
        self.declare_parameter("output_topic", "/robot/cmd_vel")
        self.declare_parameter("patrol_state_topic", "/patrol_state")
        self.declare_parameter("max_linear_x", 1.2)
        self.declare_parameter("max_angular_z", 1.0)
        self.declare_parameter("turn_enter_angular", 0.32)
        self.declare_parameter("turn_exit_angular", 0.10)
        self.declare_parameter("min_drive_linear", 0.08)

        input_topic = self.get_parameter("input_topic").value
        output_topic = self.get_parameter("output_topic").value
        patrol_state_topic = self.get_parameter("patrol_state_topic").value
        self._max_linear_x = max(0.05, float(self.get_parameter("max_linear_x").value))
        self._max_angular_z = max(0.05, float(self.get_parameter("max_angular_z").value))
        self._turn_enter_angular = max(0.01,
            float(self.get_parameter("turn_enter_angular").value))
        self._turn_exit_angular = max(0.0,
            float(self.get_parameter("turn_exit_angular").value))
        self._min_drive_linear = max(0.0,
            float(self.get_parameter("min_drive_linear").value))
        self._mode = MODE_DRIVE
        self._muted = False
        self._patrol_mode = "IDLE"

        self._pub = self.create_publisher(Twist, output_topic, 10)
        self.create_subscription(Twist, input_topic, self._on_cmd_vel, 10)
        state_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
        )
        self.create_subscription(String, patrol_state_topic,
                                 self._on_patrol_state, state_qos)
        self.get_logger().info(
            f"safety filter: {input_topic} -> {output_topic}, "
            f"max_lx={self._max_linear_x:.2f} max_wz={self._max_angular_z:.2f} "
            f"mute_modes={MUTE_MODES}"
        )

    def _on_patrol_state(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            return
        mode = str(payload.get("mode", "IDLE")).upper()
        was_muted = self._muted
        self._patrol_mode = mode
        self._muted = mode in MUTE_MODES
        if self._muted and not was_muted:
            self.get_logger().info(f"MUTE on (patrol mode={mode}) — Nav2 입력 차단")
            self._pub.publish(Twist())   # 즉시 0 1회
        elif was_muted and not self._muted:
            self.get_logger().info(f"MUTE off (patrol mode={mode}) — Nav2 입력 재허용")

    def _on_cmd_vel(self, msg: Twist) -> None:
        if self._muted:
            # PAUSED/IDLE: Nav2 가 흘려도 무시하고 0 발행 (잔여 덮어쓰기)
            self._pub.publish(Twist())
            return
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
