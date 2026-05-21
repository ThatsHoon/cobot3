"""weapon_relay — /robot/weapon/fire Trigger 서버 + IPC + /robot/weapon/state 발행.

Isaac standalone 안에서 직접 rclpy service server 를 운영하면 physics
callback 과 thread 충돌이 가능해 사이드카로 분리.

흐름:
  Client (C2 ros_bridge.fire)
    → /robot/weapon/fire (std_srvs/Trigger) call
  weapon_relay
    → fire_id 생성 → /tmp/cobot3_fire_cmd.json 쓰기
    → /tmp/cobot3_fire_result.json mtime 변화 polling (최대 3s)
    → Trigger.Response(success, message=f"{fire_id}|{state}")
  camera_publisher (in Isaac)
    → /tmp/cobot3_fire_cmd.json mtime poll → _fire_sequence() 실행
    → 완료 시 /tmp/cobot3_fire_result.json 작성

추가 발행: /robot/weapon/state (std_msgs/String JSON 1Hz latched)
    {state: IDLE|RAMPING_DOWN|FIRING|RAMPING_UP|COOLDOWN, fire_id, ts}
  camera_publisher 가 /tmp/cobot3_weapon_state.json 에 dump.
"""
import json
import os
import time
import uuid

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSProfile, QoSReliabilityPolicy, QoSDurabilityPolicy, QoSHistoryPolicy)
from std_msgs.msg import String
from std_srvs.srv import Trigger


CMD_FILE = "/tmp/cobot3_fire_cmd.json"
RESULT_FILE = "/tmp/cobot3_fire_result.json"
STATE_FILE = "/tmp/cobot3_weapon_state.json"
RESPONSE_TIMEOUT = 3.0
STATE_HZ = 1.0


class WeaponRelay(Node):
    def __init__(self):
        super().__init__("weapon_relay")
        rel_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            history=QoSHistoryPolicy.KEEP_LAST, depth=10)
        latched = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
            history=QoSHistoryPolicy.KEEP_LAST, depth=1)
        self._srv = self.create_service(
            Trigger, "/robot/weapon/fire", self._on_fire)
        self._state_pub = self.create_publisher(
            String, "/robot/weapon/state", latched)
        self._last_state_mtime = 0.0
        self._last_state_payload = {"state": "IDLE", "fire_id": None,
                                    "cooldown_remaining_s": 0.0,
                                    "ts": time.time()}
        self.create_timer(1.0 / STATE_HZ, self._publish_state)
        self.get_logger().info(
            "weapon_relay 시작 — Trigger /robot/weapon/fire, "
            "State /robot/weapon/state (1Hz latched)")

    def _on_fire(self, req: Trigger.Request,
                 res: Trigger.Response) -> Trigger.Response:
        fire_id = str(uuid.uuid4())
        # 명령 dump
        try:
            with open(CMD_FILE + ".tmp", "w") as f:
                json.dump({"fire_id": fire_id, "ts": time.time()}, f)
            os.replace(CMD_FILE + ".tmp", CMD_FILE)
        except Exception as e:
            res.success = False
            res.message = f"cmd dump fail: {e!r}"
            return res

        # 결과 대기 (mtime + fire_id 일치)
        deadline = time.time() + RESPONSE_TIMEOUT
        result = None
        while time.time() < deadline:
            try:
                with open(RESULT_FILE) as f:
                    d = json.load(f)
                if d.get("fire_id") == fire_id:
                    result = d
                    break
            except (FileNotFoundError, json.JSONDecodeError):
                pass
            time.sleep(0.05)

        if result is None:
            res.success = False
            res.message = f"{fire_id}|timeout"
            self.get_logger().warning(f"fire {fire_id} timeout")
        else:
            res.success = bool(result.get("ok", False))
            res.message = f"{fire_id}|{result.get('state', 'unknown')}"
            self.get_logger().info(f"fire {fire_id} → {res.message}")
        return res

    def _publish_state(self) -> None:
        # IPC 읽기 (있으면 갱신)
        try:
            st = os.stat(STATE_FILE)
            if st.st_mtime > self._last_state_mtime:
                with open(STATE_FILE) as f:
                    self._last_state_payload = json.load(f)
                self._last_state_mtime = st.st_mtime
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        msg = String()
        msg.data = json.dumps(self._last_state_payload)
        self._state_pub.publish(msg)


def main():
    rclpy.init()
    node = WeaponRelay()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
