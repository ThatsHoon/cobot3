"""/scene/landmarks 발행 사이드카 — camera_publisher.py 가 /tmp/cobot3_landmarks.json
에 dump 한 씬 좌표(cube/cone/fence)를 읽어 RELIABLE+TRANSIENT_LOCAL 로 latched.

C2 의 nav2_patrol.py 가 sortie 시 waypoint 구성에 사용.

I/O:
- 입력: /tmp/cobot3_landmarks.json (camera_publisher 가 쓴 JSON, 동일 PC)
- 발행: /scene/landmarks (String, RELIABLE+TRANSIENT_LOCAL, latched)

파일이 갱신되면 (mtime 변화) 다시 발행. 폴 간격 2초.

실행:
    python3 main_side/landmarks_pub.py
"""
import json
import os
from pathlib import Path

import rclpy
from rclpy.node import Node
from rclpy.qos import (DurabilityPolicy, HistoryPolicy, QoSProfile,
                       ReliabilityPolicy)
from std_msgs.msg import String

LM_FILE = Path("/tmp/cobot3_landmarks.json")


class LandmarksPub(Node):
    def __init__(self):
        super().__init__("landmarks_pub")
        latched = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self._pub = self.create_publisher(String, "/scene/landmarks", latched)
        self._mtime = 0.0
        self.create_timer(2.0, self._tick)
        self._tick()

    def _tick(self):
        if not LM_FILE.exists():
            return
        try:
            m = os.path.getmtime(LM_FILE)
            if m <= self._mtime:
                return
            payload = json.loads(LM_FILE.read_text())
        except Exception as e:
            self.get_logger().warn(f"{LM_FILE} 읽기 실패: {e!r}")
            return
        msg = String()
        msg.data = json.dumps(payload)
        self._pub.publish(msg)
        self._mtime = m
        self.get_logger().info(
            f"/scene/landmarks 발행 (mtime={m:.0f}, "
            f"len={len(msg.data)} bytes)")


def main():
    rclpy.init()
    node = LandmarksPub()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
