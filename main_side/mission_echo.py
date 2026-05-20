"""mission_echo — /mission_command 구독 → stdout (Isaac console echo).

WHY: 사용자 사양 #7 — 지통실에서의 명령 수신 시 Isaac Sim 내부 콘솔에
디버그용 출력. Isaac 5.1 OG 에 ROS2SubscribeString 미등록 → camera_publisher
프로세스에서 직접 구독 불가. rclpy 사이드카로 분리 (process 격리, OG 영향 X).

실행: ros2 run python3 main_side/mission_echo.py
또는: cobot3-start_all 의 MAIN 분기에서 백그라운드 launch.

I/O:
- 구독: /mission_command (std_msgs/String) — RELIABLE depth 10
- 발행: stdout (print) — Isaac console.log 가 stdout 을 캡처해 GUI 콘솔 표시
"""
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class MissionEcho(Node):
    def __init__(self) -> None:
        super().__init__("mission_echo")
        self._rx = 0
        self.create_subscription(String, "/mission_command", self._on_cmd, 10)
        self.get_logger().info("mission_echo listening /mission_command")
        print("[mission_echo] ready — listening /mission_command", flush=True)

    def _on_cmd(self, msg: String) -> None:
        self._rx += 1
        ts = time.strftime("%H:%M:%S")
        line = f"[mission] {ts} #{self._rx} received: {msg.data.strip()!r}"
        print(line, flush=True)
        self.get_logger().info(line)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = MissionEcho()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
