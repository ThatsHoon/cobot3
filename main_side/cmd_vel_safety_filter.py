"""Nav2 cmd_vel 안전 필터 — cobot3 Go2 적용.

linear.x 와 angular.z 를 동시에 통과시킨다 (Go2 는 곡선 주행 가능).
각 채널을 max_linear_x / max_angular_z 로 클램프하고, linear.x 가
min_drive_linear 미만이면 0 으로 눌러 noise 를 제거한다.

/patrol_state mode 가 PAUSED 일 때 입력을 무시하고 Twist(0) 을 강제 발행해
velocity_smoother 잔여 발행을 덮어쓴다 (stop 버튼이 즉시 멈추도록).
WHY: stop 후 nav2_patrol 의 1-shot Twist(0) 만으로는 velocity_smoother 의
20Hz 자율 디케이가 chain 끝까지 0 으로 떨어지기까지 시간이 걸려 로봇이
멈추지 않는 버그를 차단하기 위함.

Manual cmd_vel override (2026-05-26): /robot/cmd_vel_manual 추가 구독 →
time-based mux. C2 web manual cmd 수신 후 manual_override_s (1.0s) 동안
Nav2 cmd 를 skip 하고 manual 우선. 라우팅 중에도 manual joystick 잠시
적용 가능. spec: dev-docs/specs/2026-05-26-cmd-vel-manual-override.md.

I/O:
- 구독: /cmd_vel_nav2_raw (Twist, Nav2 chain), /robot/cmd_vel_manual
        (Twist, C2 manual), /patrol_state (String JSON)
- 발행: /robot/cmd_vel (Twist)
"""
import json
import math
import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from rclpy.qos import (DurabilityPolicy, HistoryPolicy, QoSProfile,
                       ReliabilityPolicy)
from std_msgs.msg import String


# patrol mode 가 이 집합에 들면 Nav2 입력을 무시하고 Twist(0) 으로 강제 발행.
# 2026-05-20 fix: IDLE 제거 — 사용자 teleop(BaseMovement·DS) 가 IDLE 에서
# 자유 발행 가능해야 함. PAUSED 만 mute (정지 버튼 보호).
MUTE_MODES = {"PAUSED"}


class CmdVelSafetyFilter(Node):
    def __init__(self) -> None:
        super().__init__("cmd_vel_safety_filter")

        self.declare_parameter("input_topic", "/cmd_vel_nav2_raw")
        self.declare_parameter("manual_topic", "/robot/cmd_vel_manual")
        self.declare_parameter("output_topic", "/robot/cmd_vel")
        self.declare_parameter("patrol_state_topic", "/patrol_state")
        self.declare_parameter("max_linear_x", 1.2)
        self.declare_parameter("max_angular_z", 1.0)
        self.declare_parameter("min_drive_linear", 0.08)
        self.declare_parameter("manual_override_s", 1.0)

        input_topic = self.get_parameter("input_topic").value
        manual_topic = self.get_parameter("manual_topic").value
        output_topic = self.get_parameter("output_topic").value
        patrol_state_topic = self.get_parameter("patrol_state_topic").value
        self._max_linear_x = max(0.05, float(self.get_parameter("max_linear_x").value))
        self._max_angular_z = max(0.05, float(self.get_parameter("max_angular_z").value))
        self._min_drive_linear = max(0.0,
            float(self.get_parameter("min_drive_linear").value))
        self._manual_override_s = max(0.1,
            float(self.get_parameter("manual_override_s").value))
        self._muted = False
        self._patrol_mode = "IDLE"
        self._last_manual_ts: float = 0.0

        self._pub = self.create_publisher(Twist, output_topic, 10)
        self.create_subscription(Twist, input_topic, self._on_cmd_vel, 10)
        self.create_subscription(Twist, manual_topic, self._on_manual_cmd, 10)
        state_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
        )
        self.create_subscription(String, patrol_state_topic,
                                 self._on_patrol_state, state_qos)
        self.get_logger().info(
            f"safety filter: nav={input_topic} manual={manual_topic} -> {output_topic}, "
            f"max_lx={self._max_linear_x:.2f} max_wz={self._max_angular_z:.2f} "
            f"min_drive={self._min_drive_linear:.3f} mute_modes={MUTE_MODES} "
            f"manual_override={self._manual_override_s:.1f}s"
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
            # PAUSED: Nav2 가 흘려도 무시하고 0 발행 (잔여 덮어쓰기)
            self._pub.publish(Twist())
            return
        # Manual override 우선 — 마지막 manual cmd 1s 안이면 Nav2 cmd skip
        # → ROUTING 중에도 manual joystick 잠시 적용 가능 (race 해결).
        if time.monotonic() - self._last_manual_ts < self._manual_override_s:
            return
        # NaN/Inf 안전 가드: clamp 가 NaN 을 silently bound 값으로 치환할 수
        # 있으므로(Python min/max NaN 처리가 정의되지 않음) clamp 전에 0 으로.
        lin_raw = msg.linear.x if math.isfinite(msg.linear.x) else 0.0
        ang_raw = msg.angular.z if math.isfinite(msg.angular.z) else 0.0
        linear = self._clamp(lin_raw, -self._max_linear_x, self._max_linear_x)
        angular = self._clamp(ang_raw, -self._max_angular_z, self._max_angular_z)

        filtered = Twist()
        filtered.linear.x = linear if abs(linear) >= self._min_drive_linear else 0.0
        filtered.angular.z = angular
        self._pub.publish(filtered)

    def _on_manual_cmd(self, msg: Twist) -> None:
        """C2 manual cmd 수신 — last_manual_ts 갱신 + 즉시 발행 (Nav2 ~50ms
        대기 불필요). PAUSED 면 mute 적용. clamp/NaN 가드는 _on_cmd_vel 와 동일."""
        if self._muted:
            self._pub.publish(Twist())
            return
        self._last_manual_ts = time.monotonic()
        lin_raw = msg.linear.x if math.isfinite(msg.linear.x) else 0.0
        ang_raw = msg.angular.z if math.isfinite(msg.angular.z) else 0.0
        linear = self._clamp(lin_raw, -self._max_linear_x, self._max_linear_x)
        angular = self._clamp(ang_raw, -self._max_angular_z, self._max_angular_z)
        out = Twist()
        out.linear.x = linear if abs(linear) >= self._min_drive_linear else 0.0
        out.angular.z = angular
        self._pub.publish(out)

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
