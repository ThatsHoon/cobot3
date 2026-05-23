"""검사 카메라 명령 사이드카 — /robot/inspect/command (std_msgs/String JSON) 를
구독해 /tmp/cobot3_inspect_cmd.json 에 덮어쓴다. camera_publisher 가 그
파일의 mtime 변화를 폴링해 명령 적용.

Isaac 5.1 OG 에 ROS2SubscribeString 가 미등록이라 본 사이드카로 우회.
landmarks_pub 와 대칭 패턴 (file mailbox = 같은 PC IPC).

실행:
    python3 main_side/inspect_relay.py
"""
import json
from pathlib import Path

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

INSPECT_CMD_FILE = Path("/tmp/cobot3_inspect_cmd.json")


class InspectRelay(Node):
    def __init__(self):
        super().__init__("inspect_relay")
        rel = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, depth=10)
        self.create_subscription(String, "/robot/inspect/command",
                                 self._on_cmd, rel)
        self.get_logger().info(
            f"inspect_relay: /robot/inspect/command → {INSPECT_CMD_FILE}")

    def _on_cmd(self, msg: String):
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError as e:
            self.get_logger().warn(f"JSON 파싱 실패: {e}; data={msg.data[:80]!r}")
            return
        try:
            INSPECT_CMD_FILE.write_text(json.dumps(payload))
        except OSError as e:
            self.get_logger().warn(f"파일 쓰기 실패: {e}")
            return
        self.get_logger().info(f"inspect cmd 수신·dump: {payload}")


def main():
    rclpy.init()
    node = InspectRelay()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
