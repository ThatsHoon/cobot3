"""fall_relay — Isaac standalone(camera_publisher) → ROS 2 ALERT 브리지.

go2_controller._tick_fall_recover() 가 상태 변화 시 /tmp/cobot3_fall_state.json
을 갱신한다. 이 사이드카는:
  - mtime 폴(0.2s) 로 파일 변화 감지 → state 전이 시 /robot/fall_alert 발행 (edge)
  - 2Hz 주기 /robot/fall_state 발행 (latest snapshot, 미존재면 UPRIGHT)

발행 토픽 (모두 std_msgs/String JSON):
  /robot/fall_alert  (RELIABLE depth=10) — 상태 전이 1회 (level/event 포함)
  /robot/fall_state  (RELIABLE depth=10) — 2Hz 스냅샷

Isaac 사이드와 같은 ROS_DOMAIN_ID·FASTDDS profile 환경에서 기동.
"""
import json
import os
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy
from std_msgs.msg import String


IPC_PATH = "/tmp/cobot3_fall_state.json"
POLL_DT = 0.2     # 200ms — 상태 전이는 즉각 알람으로 가야 함
STATE_HZ = 2.0    # /robot/fall_state 주기


class FallRelay(Node):
    def __init__(self):
        super().__init__("fall_relay")
        qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10,
        )
        self._alert_pub = self.create_publisher(String, "/robot/fall_alert", qos)
        self._state_pub = self.create_publisher(String, "/robot/fall_state", qos)

        self._last_mtime = 0.0
        self._last_state = "UPRIGHT"
        self._latest_payload = {
            "ts": time.time(), "state": "UPRIGHT", "up_z": 1.0,
            "stage": None, "pose": {"x": 0.0, "y": 0.0, "z": 0.0},
        }

        self.create_timer(POLL_DT, self._poll_ipc)
        self.create_timer(1.0 / STATE_HZ, self._publish_state)
        self.get_logger().info("fall_relay 시작 — /robot/fall_alert, /robot/fall_state")

    def _poll_ipc(self) -> None:
        try:
            st = os.stat(IPC_PATH)
        except FileNotFoundError:
            return
        if st.st_mtime <= self._last_mtime:
            return
        self._last_mtime = st.st_mtime
        try:
            with open(IPC_PATH, "r") as f:
                payload = json.load(f)
        except Exception as exc:
            self.get_logger().warning(f"IPC parse err: {exc!r}")
            return
        self._latest_payload = payload
        state = str(payload.get("state", ""))
        # 상태 전이 시 alert 발행 (FALLEN/RECOVERING/RECOVERED 모두 edge)
        if state and state != self._last_state:
            self._last_state = state
            self._emit_alert(payload)

    def _emit_alert(self, payload: dict) -> None:
        state = payload.get("state", "")
        # WHY level 매핑: FALLEN=ALERT(빨강) / RECOVERING=WARN / RECOVERED=INFO
        level = {
            "FALLEN":     "ALERT",
            "RECOVERING": "WARN",
            "RECOVERED":      "INFO",
            "UPRIGHT":        "INFO",
            "OOB_EXPLOSION":  "ALERT",
            "OOB_VERTICAL":   "ALERT",
        }.get(state, "INFO")
        event = {
            "FALLEN":         "robot_fall_detected",
            "RECOVERING":     "robot_recovery_in_progress",
            "RECOVERED":      "robot_recovery_done",
            "UPRIGHT":        "robot_upright",
            "OOB_EXPLOSION":  "robot_oob_explosion",
            "OOB_VERTICAL":   "robot_oob_vertical",
        }.get(state, "robot_state")
        reason = str(payload.get("reason", ""))
        msg = String()
        msg.data = json.dumps({
            "level": level,
            "event": event,
            "state": state,
            "reason": reason,
            "up_z": float(payload.get("up_z", 0.0)),
            "stage": payload.get("stage"),
            "pose": payload.get("pose"),
            "ts": payload.get("ts", time.time()),
        })
        self._alert_pub.publish(msg)
        # OOB 류는 /rosout warn 으로도 발행 → C2 ros_bridge 가 type='log' 로
        # event WebSocket 에 자동 emit (디버그 페이지 EventLog 의 off 모드에서도
        # 표시됨). 2026-05-26 사용자 요청.
        if state.startswith("OOB_"):
            pos = payload.get("pose") or {}
            self.get_logger().warn(
                f"OOB rollback [{state}] {reason} → home teleport "
                f"@ pos=({pos.get('x',0):.1f},{pos.get('y',0):.1f},{pos.get('z',0):.1f})")
        else:
            self.get_logger().info(f"[alert] {state} up_z={payload.get('up_z', 0):.2f}")

    def _publish_state(self) -> None:
        msg = String()
        msg.data = json.dumps(self._latest_payload)
        self._state_pub.publish(msg)


def main():
    rclpy.init()
    node = FallRelay()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
