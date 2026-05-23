"""NPC 소환 사이드카 — /robot/npc/spawn (std_msgs/String JSON) 구독 →
/tmp/cobot3_npc_cmd.json 에 덮어쓴다. camera_publisher 가 mtime 폴링 후
Go2 base pose 기준으로 사람 형체 NPC 를 procedural 합성·낙하.

Isaac 5.1 OG 에 ROS2SubscribeString 미등록이라 본 사이드카로 우회
(inspect_relay 와 동일 패턴).

실행: python3 main_side/npc_relay.py
"""
import json
from pathlib import Path

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

NPC_CMD_FILE = Path("/tmp/cobot3_npc_cmd.json")


class NpcRelay(Node):
    def __init__(self):
        super().__init__("npc_relay")
        rel = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, depth=10)
        self.create_subscription(String, "/robot/npc/spawn",
                                 self._on_cmd, rel)
        self.get_logger().info(
            f"npc_relay: /robot/npc/spawn → {NPC_CMD_FILE}")

    def _on_cmd(self, msg: String):
        try:
            payload = json.loads(msg.data) if msg.data.strip() else {}
        except json.JSONDecodeError as e:
            self.get_logger().warn(f"JSON 파싱 실패: {e}; data={msg.data[:80]!r}")
            return
        try:
            NPC_CMD_FILE.write_text(json.dumps(payload))
        except OSError as e:
            self.get_logger().warn(f"파일 쓰기 실패: {e}")
            return
        self.get_logger().info(f"npc spawn 수신·dump: {payload}")


def main():
    rclpy.init()
    node = NpcRelay()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
