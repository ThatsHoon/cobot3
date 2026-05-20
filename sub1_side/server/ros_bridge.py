"""ROS 2 ↔ C2 브리지.

rclpy 노드를 별도 스레드(MultiThreadedExecutor)에서 spin 하고,
- 다운링크: state/gps/odom/joint/rosout/video 구독 → 공유 상태 + 이벤트 큐 + DB 적재
- 업링크: nav_goal 발행, speaker 발행, weapon/fire 서비스 호출
asyncio 와는 loop.call_soon_threadsafe 로 안전 연결 (server-bridge.md 패턴).
"""
import json
import logging
import math
import threading
import time
from datetime import datetime, timezone

import numpy as np

import config

log = logging.getLogger("c2.ros")

try:
    import rclpy
    from rclpy.node import Node
    from rclpy.executors import MultiThreadedExecutor
    from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
    from sensor_msgs.msg import NavSatFix, JointState, CompressedImage
    from nav_msgs.msg import Odometry
    from geometry_msgs.msg import PoseStamped, TransformStamped, Twist
    from tf2_msgs.msg import TFMessage
    from std_msgs.msg import String
    from rcl_interfaces.msg import Log
    from std_srvs.srv import Trigger
    import cv2
    RCLPY_OK = True
except Exception as e:  # rclpy 미설치 환경에서도 import 가능 (graceful)
    RCLPY_OK = False
    _IMPORT_ERR = e


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


SENSOR_QOS_DEPTH = 5
RELIABLE_QOS_DEPTH = 10


class RosBridge:
    """asyncio 쪽에서 사용하는 파사드. start(loop, db) 로 기동."""

    def __init__(self):
        self.latest = {              # REST GET 캐시
            "state": {}, "gps": {}, "odom": {},
            "leg_q": [],
            "intruders": [], "patrol_state": {}, "landmarks": {},
        }
        self._intr_last_log = 0.0   # /intruder_states DB 적재 다운샘플
        self._patrol_last_log = None
        self._video_lock = threading.Lock()
        # 2026-05-20: front 제거, inspect 추가
        self._video_rear:    np.ndarray | None = None  # BGR 후방(real) 카메라
        self._video_inspect: np.ndarray | None = None  # BGR 검사 카메라(짐벌)
        self._loop = None
        self._db = None
        self._ev_cb = None           # asyncio: 이벤트 브로드캐스트 콜백
        self._yolo = None            # yolo_infer.YoloInfer (선택)
        self._node = None
        self._exec = None
        self._thread = None
        self._js_last_log = 0.0      # joint_snapshots 10Hz 다운샘플 타이머

    # ---- 생명주기 -----------------------------------------------------
    def start(self, loop, db, event_cb, yolo=None):
        self._loop, self._db, self._ev_cb, self._yolo = loop, db, event_cb, yolo

        # 통신 설정 자가점검 (요청) — stdout + 브라우저 콘솔(WS)
        import os
        env = {k: os.environ.get(k, "<UNSET>") for k in
               ("ROS_DOMAIN_ID", "RMW_IMPLEMENTATION", "ROS_LOCALHOST_ONLY")}
        log.info("==== web_server ROS 설정 점검 ====")
        for k, v in env.items():
            log.info("  %s=%s", k, v)
        warns = []
        if env["ROS_DOMAIN_ID"] not in ("130", config.ROS_DOMAIN_ID):
            warns.append(f"ROS_DOMAIN_ID={env['ROS_DOMAIN_ID']} (기대 130)")
        if env["RMW_IMPLEMENTATION"] != "rmw_fastrtps_cpp":
            warns.append(f"RMW={env['RMW_IMPLEMENTATION']} (기대 rmw_fastrtps_cpp)")
        for w in warns:
            log.warning("  ⚠ %s — Isaac 토픽 디스커버리 실패 위험", w)
        log.info("==================================")
        self._emit({"type": "diag", "ts": _now_iso(), "src": "web_server",
                    "env": env, "warn": warns})

        if not RCLPY_OK:
            log.error("rclpy import 실패 — ROS 브리지 비활성: %s", _IMPORT_ERR)
            self._emit({"type": "diag", "ts": _now_iso(), "src": "web_server",
                        "fatal": f"rclpy import 실패: {_IMPORT_ERR}"})
            return
        rclpy.init()
        self._node = _C2Node(self)
        self._exec = MultiThreadedExecutor()
        self._exec.add_node(self._node)
        self._thread = threading.Thread(target=self._exec.spin, daemon=True)
        self._thread.start()
        log.info("RosBridge spinning (domain=%s rmw=%s)",
                 env["ROS_DOMAIN_ID"], env["RMW_IMPLEMENTATION"])

    def stop(self):
        if not RCLPY_OK:
            return
        try:
            self._exec.shutdown()
            self._node.destroy_node()
            rclpy.shutdown()
        except Exception:
            pass

    # ---- asyncio 로 이벤트 전달 (스레드 안전) --------------------------
    def _emit(self, event: dict):
        if self._loop and self._ev_cb:
            self._loop.call_soon_threadsafe(self._ev_cb, event)

    # ---- 영상 프레임 (WebRTC/MJPEG 가 읽음) ---------------------------
    # 2026-05-20: front 카메라 제거, inspect 추가. camera in {rear, inspect}.
    def get_video_frame(self, camera: str = "rear"):
        with self._video_lock:
            frame = self._video_inspect if camera == "inspect" else self._video_rear
            return None if frame is None else frame.copy()

    def _set_video_frame(self, bgr, camera: str = "rear"):
        with self._video_lock:
            if camera == "inspect":
                self._video_inspect = bgr
            else:
                self._video_rear = bgr

    # ---- 업링크 (C2 → 로봇) ------------------------------------------
    def pub_cmd_vel(self, lin: float, ang: float, vy: float = 0.0):
        if self._node:
            self._node.pub_cmd_vel(lin, ang, vy=vy)

    def publish_goal(self, x: float, y: float):
        if self._node:
            self._node.pub_goal(x, y)

    def send_speaker(self, payload: dict):
        if self._node:
            self._node.pub_speaker(json.dumps(payload))

    def pub_mission(self, command: str):
        if self._node:
            self._node.pub_mission(command)

    def pub_inspect_cmd(self, payload: dict):
        if self._node:
            self._node.pub_inspect_cmd(json.dumps(payload))

    def pub_npc_spawn(self, payload: dict):
        if self._node:
            self._node.pub_npc_spawn(json.dumps(payload))

    def fire(self, target_ref: str, operator: str):
        """weapon/fire 서비스 호출 → 결과를 fire_events 기록 + 이벤트 emit."""
        hit, dist = (False, None)
        if self._node:
            hit, dist = self._node.call_fire()
        ts = _now_iso()
        if self._db:
            self._db.put("fire_events",
                         (config.ROBOT_ID, ts, target_ref, hit, dist, operator))
        self._emit({"type": "fire", "ts": ts, "target": target_ref,
                    "hit": hit, "distance_m": dist, "operator": operator})
        return {"hit": hit, "distance_m": dist}


if RCLPY_OK:
    class _C2Node(Node):
        def __init__(self, br: "RosBridge"):
            super().__init__("c2_web_server")
            self.br = br
            sensor_qos = QoSProfile(
                reliability=ReliabilityPolicy.BEST_EFFORT,
                history=HistoryPolicy.KEEP_LAST, depth=SENSOR_QOS_DEPTH)
            rel_qos = QoSProfile(
                reliability=ReliabilityPolicy.RELIABLE,
                history=HistoryPolicy.KEEP_LAST, depth=RELIABLE_QOS_DEPTH)
            latched_qos = QoSProfile(
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
                history=HistoryPolicy.KEEP_LAST, depth=1)
            T = config.TOPICS
            # ---- 다운링크 구독 (항상 활성 — 정공 단일 경로) ----
            self.create_subscription(String, T["state"], self._on_state, rel_qos)
            self.create_subscription(NavSatFix, T["gps"], self._on_gps, rel_qos)
            self.create_subscription(Odometry, T["odom"], self._on_odom, rel_qos)
            self.create_subscription(JointState, T["leg_joint"], self._on_leg, rel_qos)
            # 2026-05-20: front 제거, rear+inspect 만 구독
            self.create_subscription(CompressedImage, T["video_rear"],
                                     lambda m: self._on_video(m, "rear"), sensor_qos)
            self.create_subscription(CompressedImage, T["video_inspect"],
                                     lambda m: self._on_video(m, "inspect"), sensor_qos)
            self.create_subscription(Log, T["rosout"], self._on_rosout, rel_qos)
            # ---- DMZ Sentry M5/M7 신규 다운링크 ----
            self.create_subscription(String, T["intruders"],
                                     self._on_intruders, rel_qos)
            self.create_subscription(String, T["patrol_state"],
                                     self._on_patrol_state, rel_qos)
            self.create_subscription(String, T["landmarks"],
                                     self._on_landmarks, latched_qos)
            # ---- 업링크 발행/클라이언트 ----
            self._cmd_pub  = self.create_publisher(Twist, T["cmd_vel"], rel_qos)
            self._goal_pub = self.create_publisher(PoseStamped, T["nav_goal"], rel_qos)
            self._spk_pub  = self.create_publisher(String, T["speaker"], rel_qos)
            self._fire_cli = self.create_client(Trigger, T["fire_srv"])
            # ---- DMZ Sentry M5/M7 신규 업링크 ----
            self._mission_pub = self.create_publisher(String, T["mission_cmd"], rel_qos)
            self._inspect_pub = self.create_publisher(String, T["inspect_cmd"], rel_qos)
            self._npc_pub = self.create_publisher(String, T["npc_spawn"], rel_qos)
            self._alerts_pub = self.create_publisher(String, T["alerts"], rel_qos)
            self._animal_pub = self.create_publisher(String, T["animal_alerts"], rel_qos)
            self._det_pub = self.create_publisher(String, T["detections"], rel_qos)
            # ---- 진단 카운터 + 주기 헬스 ----
            self._rx = {"state": 0, "gps": 0,
                        "video_rear": 0, "video_inspect": 0,
                        "leg": 0, "rosout": 0,
                        "intruders": 0, "patrol_state": 0, "landmarks": 0}
            self.create_timer(5.0, self._health)
            self.get_logger().info(
                "구독: state/gps/odom/leg/rosout/video_rear/video_inspect/"
                "intruders/patrol_state/landmarks — "
                "업링크: cmd_vel/nav_goal/speaker/fire/mission/inspect/alerts/npc")

        def _health(self):
            T = config.TOPICS
            pubs = {
                "video_rear":    self.count_publishers(T["video_rear"]),
                "video_inspect": self.count_publishers(T["video_inspect"]),
                "state":         self.count_publishers(T["state"]),
            }
            L = self.get_logger()
            L.info(f"HEALTH rx={self._rx} | publishers={pubs}")
            hint = None
            if self._rx["video_rear"] == 0:
                hint = (f"{T['video_rear']} 수신 0 — "
                        + ("publisher 0: degrade/Isaac 미발행"
                           if pubs["video_rear"] == 0
                           else "publisher 있음: QoS/RMW 불일치 의심"))
                L.warn("  ⚠ " + hint)
            self.br._emit({"type": "diag", "ts": _now_iso(),
                           "src": "ros_bridge", "rx": dict(self._rx),
                           "publishers": pubs, "hint": hint})

        # ---- 콜백 ----
        def _on_state(self, msg):
            self._rx["state"] += 1
            try:
                d = json.loads(msg.data)
            except Exception:
                d = {"raw": msg.data}
            self.br.latest["state"] = d
            ts = _now_iso()
            wp = d.get("waypoint")
            self.br._db and self.br._db.put("robot_state_log", (
                config.ROBOT_ID, ts, d.get("mode"), d.get("gait"),
                d.get("battery"), wp if isinstance(wp, int) else None,
                json.dumps(d.get("extra", {}))))
            self.br._emit({"type": "state", "ts": ts, "data": d})

        def _on_gps(self, msg):
            self._rx["gps"] += 1
            d = {"lat": msg.latitude, "lon": msg.longitude, "alt": msg.altitude}
            self.br.latest["gps"] = d
            ts = _now_iso()
            self.br._db and self.br._db.put("gps_track", (
                config.ROBOT_ID, ts, msg.latitude, msg.longitude,
                float(msg.altitude), None, None))
            self.br._emit({"type": "gps", "ts": ts, "data": d})

        def _on_odom(self, msg):
            p = msg.pose.pose.position
            q = msg.pose.pose.orientation
            siny = 2.0 * (q.w * q.z + q.x * q.y)
            cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
            yaw = math.atan2(siny, cosy)
            self.br.latest["odom"] = {"x": p.x, "y": p.y, "z": p.z, "yaw": yaw}

        def _on_leg(self, msg):
            self._rx["leg"] += 1
            self.br.latest["leg_q"] = list(msg.position)
            now = time.monotonic()
            if now - self.br._js_last_log >= 0.1:   # 10 Hz 다운샘플
                self.br._js_last_log = now
                self.br._db and self.br._db.put("joint_snapshots", (
                    config.ROBOT_ID, _now_iso(),
                    [], self.br.latest["leg_q"]))

        def _on_rosout(self, msg):
            self._rx["rosout"] += 1
            if msg.level < config.ROSOUT_WARN_LEVEL:   # WARN 이상만
                return
            ts = _now_iso()
            self.br._db and self.br._db.put("rosout_warn", (
                ts, int(msg.level), msg.name, msg.msg))
            self.br._emit({"type": "log", "ts": ts, "level": int(msg.level),
                           "name": msg.name, "msg": msg.msg})

        def _on_video(self, msg, camera: str = "rear"):
            # 2026-05-20: front 제거 → YOLO 는 inspect 카메라 frame 에 적용.
            key = f"video_{camera}"
            self._rx[key] = self._rx.get(key, 0) + 1
            if self._rx[key] == 1:
                self.get_logger().info(
                    f"✓ 첫 {camera} 영상 프레임 수신({len(msg.data)}B) — "
                    f"degrade↔web_server 통신 OK")
            arr = np.frombuffer(bytes(msg.data), dtype=np.uint8)
            bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if bgr is None:
                return
            if self.br._yolo is not None and camera == "inspect":
                dets, alert, animal_alert = self.br._yolo.infer_with_alerts(bgr)
                if dets:
                    ts = _now_iso()
                    for d in dets:
                        x, y, w, h = d["bbox"]
                        cv2.rectangle(bgr, (int(x), int(y)),
                                      (int(x + w), int(y + h)), (0, 0, 255), 2)
                        cv2.putText(bgr, f'{d["class_name"]} {d["conf"]:.2f}',
                                    (int(x), int(y) - 5),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
                        self.br._db and self.br._db.put("intruder_detections", (
                            config.ROBOT_ID, ts, d["class_name"], d["conf"],
                            x, y, w, h, None, None, None, None, "camera_inspect"))
                    self.br._emit({"type": "detection", "ts": ts, "items": dets})
                    det_msg = String()
                    det_msg.data = json.dumps({
                        "stamp": ts, "frame_id": "camera_inspect",
                        "detections": dets})
                    self._det_pub.publish(det_msg)
                if alert is not None:
                    ts = _now_iso()
                    a_msg = String()
                    a_msg.data = json.dumps(alert)
                    self._alerts_pub.publish(a_msg)
                    x1, y1, x2, y2 = alert["bbox_xyxy"]
                    self.br._db and self.br._db.put("alerts", (
                        config.ROBOT_ID, ts, alert["level"], alert["event"],
                        float(alert["confidence"]),
                        json.dumps([x1, y1, x2, y2]),
                        int(alert["count"]), False))
                    self.br._emit({"type": "alert", "ts": ts, "data": alert})
                    self.get_logger().warn(
                        f"ALERT person conf={alert['confidence']:.2f} → /alerts")
                if animal_alert is not None:
                    ts = _now_iso()
                    aa_msg = String()
                    aa_msg.data = json.dumps(animal_alert)
                    self._animal_pub.publish(aa_msg)
                    x1, y1, x2, y2 = animal_alert["bbox_xyxy"]
                    self.br._db and self.br._db.put("alerts", (
                        config.ROBOT_ID, ts, animal_alert["level"],
                        animal_alert["event"],
                        float(animal_alert["confidence"]),
                        json.dumps([x1, y1, x2, y2]),
                        int(animal_alert["count"]), False))
                    self.br._emit({"type": "animal_alert", "ts": ts,
                                   "data": animal_alert})
                    self.get_logger().warn(
                        f"ANIMAL_ALERT {animal_alert['label']} "
                        f"conf={animal_alert['confidence']:.2f} → /animal_alerts")
            self.br._set_video_frame(bgr, camera)

        def _on_intruders(self, msg):
            self._rx["intruders"] += 1
            try:
                d = json.loads(msg.data)
            except Exception:
                return
            ts = _now_iso()
            self.br.latest["intruders"] = d
            self.br._emit({"type": "intruder_state", "ts": ts, "data": d})
            # 1Hz 다운샘플로 DB 적재 (intruder_states_log)
            now = time.monotonic()
            last = getattr(self.br, "_intr_last_log", 0.0)
            if now - last >= 1.0:
                self.br._intr_last_log = now
                items = d if isinstance(d, list) else d.get("items", [])
                for it in items:
                    self.br._db and self.br._db.put("intruder_states_log", (
                        ts, str(it.get("id", "?")),
                        float(it.get("x", 0.0)),
                        float(it.get("y", 0.0)),
                        float(it.get("z", 0.0)),
                        str(it.get("label", ""))))

        def _on_patrol_state(self, msg):
            self._rx["patrol_state"] += 1
            try:
                d = json.loads(msg.data)
            except Exception:
                return
            self.br.latest["patrol_state"] = d
            ts = _now_iso()
            self.br._emit({"type": "patrol_state", "ts": ts, "data": d})
            # 패트롤 모드/waypoint 변화시만 DB 적재
            last = getattr(self.br, "_patrol_last_log", None)
            sig = (d.get("mode"), (d.get("waypoint") or {}).get("x"))
            if sig != last:
                self.br._patrol_last_log = sig
                pose = d.get("pose") or {}
                wp = d.get("waypoint") or {}
                self.br._db and self.br._db.put("patrol_state_log", (
                    config.ROBOT_ID, ts, str(d.get("mode", "")),
                    None,  # current_waypoint idx — 미사용
                    float(pose.get("x", 0.0)) if pose else None,
                    float(pose.get("y", 0.0)) if pose else None,
                    float(pose.get("yaw", 0.0)) if pose else None))

        def _on_landmarks(self, msg):
            self._rx["landmarks"] += 1
            try:
                d = json.loads(msg.data)
            except Exception:
                return
            self.br.latest["landmarks"] = d
            self.br._emit({"type": "landmarks", "ts": _now_iso(), "data": d})

        # ---- 업링크 ----
        def pub_cmd_vel(self, lin: float, ang: float, vy: float = 0.0):
            m = Twist()
            m.linear.x = float(lin)
            m.linear.y = float(vy)
            m.angular.z = float(ang)
            self._cmd_pub.publish(m)

        def pub_goal(self, x, y):
            m = PoseStamped()
            m.header.stamp = self.get_clock().now().to_msg()
            m.header.frame_id = "map"
            m.pose.position.x = float(x)
            m.pose.position.y = float(y)
            m.pose.orientation.w = 1.0
            self._goal_pub.publish(m)

        def pub_speaker(self, data: str):
            m = String()
            m.data = data
            self._spk_pub.publish(m)

        def pub_mission(self, command: str):
            m = String()
            m.data = command
            self._mission_pub.publish(m)

        def pub_inspect_cmd(self, payload_json: str):
            m = String()
            m.data = payload_json
            self._inspect_pub.publish(m)

        def pub_npc_spawn(self, payload_json: str):
            m = String()
            m.data = payload_json
            self._npc_pub.publish(m)

        def call_fire(self):
            if not self._fire_cli.wait_for_service(timeout_sec=1.0):
                self.get_logger().warning("weapon/fire 서비스 없음")
                return False, None
            fut = self._fire_cli.call_async(Trigger.Request())
            t0 = time.monotonic()
            while not fut.done() and time.monotonic() - t0 < 2.0:
                time.sleep(0.02)
            if fut.done() and fut.result() is not None:
                res = fut.result()
                # message 에 "hit;distance" 규약 (Main PC c2_command_node 와 합의)
                hit = res.success
                dist = None
                try:
                    dist = float(res.message.split(";")[1])
                except Exception:
                    pass
                return hit, dist
            return False, None
