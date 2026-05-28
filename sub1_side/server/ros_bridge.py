"""ROS 2 ↔ C2 브리지.

rclpy 노드를 별도 스레드(MultiThreadedExecutor)에서 spin 하고,
- 다운링크: state/gps/odom/joint/rosout/video 구독 → 공유 상태 + 이벤트 큐 + DB 적재
- 업링크: nav_goal 발행, speaker 발행, weapon/fire 서비스 호출
asyncio 와는 loop.call_soon_threadsafe 로 안전 연결 (server-bridge.md 패턴).
"""
import asyncio
import concurrent.futures
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
    from geometry_msgs.msg import (
        PoseStamped, TransformStamped, Twist, Vector3Stamped)
    from std_srvs.srv import Trigger
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
        # 2026-05-20: front 제거, inspect 추가. overhead 추가 (TACTICAL MAP 배경).
        self._video_rear:     np.ndarray | None = None  # BGR 후방(real) 카메라
        self._video_inspect:  np.ndarray | None = None  # BGR 검사 카메라(짐벌)
        self._video_overhead: np.ndarray | None = None  # BGR 오버헤드 카메라
        # Tactical fixed cameras (TP_A ~ TP_D)
        self._video_tp_a: np.ndarray | None = None
        self._video_tp_b: np.ndarray | None = None
        self._video_tp_c: np.ndarray | None = None
        self._video_tp_d: np.ndarray | None = None
        self._depth_lock = threading.Lock()
        self._depth_tp_a: np.ndarray | None = None
        self._depth_tp_b: np.ndarray | None = None
        self._depth_tp_c: np.ndarray | None = None
        self._depth_tp_d: np.ndarray | None = None
        self._loop = None
        self._db = None
        self._ev_cb = None           # asyncio: 이벤트 브로드캐스트 콜백
        self._yolo = None            # yolo_infer.YoloInfer (선택)
        self._node = None
        self._exec = None
        self._thread = None
        self._js_last_log = 0.0      # joint_snapshots 10Hz 다운샘플 타이머
        # Main-side YOLO 결과 캐시 — bbox overlay용 (2026-05-27)
        self._last_dets: dict[str, list] = {}
        self._dets_lock = threading.Lock()
        # WHY: YOLO 추론(50-200ms)을 ROS callback thread 에서 분리.
        # max_workers=1 → 이전 추론이 끝나기 전에 새 프레임이 들어오면 drop(영상 연속성 보장).
        self._yolo_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._yolo_futures: dict[str, concurrent.futures.Future] = {}

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

        # YOLO 자동사격 콜백 주입 (Feature 3)
        if yolo and yolo.enabled:
            yolo.set_auto_fire_cb(self._on_auto_fire_detected)
            log.info("YOLO 자동사격 콜백 등록 완료")

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
    # 2026-05-20: front 제거. camera in {rear, inspect, overhead}.
    def get_video_frame(self, camera: str = "rear"):
        with self._video_lock:
            if camera == "inspect":
                frame = self._video_inspect
            elif camera == "overhead":
                frame = self._video_overhead
            elif camera == "tp_a":
                frame = self._video_tp_a
            elif camera == "tp_b":
                frame = self._video_tp_b
            elif camera == "tp_c":
                frame = self._video_tp_c
            elif camera == "tp_d":
                frame = self._video_tp_d
            else:
                frame = self._video_rear
            return None if frame is None else frame.copy()

    def _set_video_frame(self, bgr, camera: str = "rear"):
        with self._video_lock:
            if camera == "inspect":
                self._video_inspect = bgr
            elif camera == "overhead":
                self._video_overhead = bgr
            elif camera == "tp_a":
                self._video_tp_a = bgr
            elif camera == "tp_b":
                self._video_tp_b = bgr
            elif camera == "tp_c":
                self._video_tp_c = bgr
            elif camera == "tp_d":
                self._video_tp_d = bgr
            else:
                self._video_rear = bgr

    def _get_depth_frame(self, camera: str):
        with self._depth_lock:
            return getattr(self, f"_depth_{camera}", None)

    def _set_depth_frame(self, camera: str, arr: np.ndarray):
        with self._depth_lock:
            attr = f"_depth_{camera}"
            if hasattr(self, attr):
                setattr(self, attr, arr)

    # ---- 업링크 (C2 → 로봇) ------------------------------------------
    def pub_cmd_vel(self, lin: float, ang: float, vy: float = 0.0):
        # 2026-05-20 fix: 정지(PAUSED) 시 teleop 발행 차단 — safety_filter 의
        # mute Twist(0) 와 race 제거. BaseMovement·DS·TeleopPad 모두 차단.
        mode = str((self.latest.get("patrol_state") or {}).get("mode", "")).upper()
        if mode == "PAUSED":
            return
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

    def pub_soldier_spawn(self, payload: dict):
        """군인 소환 — 동일 IPC(/robot/npc/spawn + /tmp/cobot3_npc_cmd.json) 재사용."""
        if self._node:
            self._node.pub_npc_spawn(json.dumps(payload))

    def pub_animal_spawn(self, payload: dict):
        """동물/드론 소환 — 동일 /robot/npc/spawn 토픽, kind 필드로 라우팅.
        npc_relay 가 kind 유무로 /tmp/cobot3_animal_cmd.json 에 분기 기록.
        """
        if self._node:
            self._node.pub_npc_spawn(json.dumps(payload))

    def fire(self, target_ref: str, operator: str,
             target_alert_id: int | None = None):
        """weapon/fire 서비스 호출 (HITL 흐름, 2026-05-21):
        - 사격 시퀀스 트리거 → fire_id 받음
        - hit/miss 는 인간이 별도 record_fire_result() 로 입력 (이때 DB)
        - 임시 row 는 hit=None 으로 즉시 적재 (UI 가 추적용)."""
        success, fire_id, state = (False, None, "no_service")
        if self._node:
            success, fire_id, state = self._node.call_fire()
        ts = _now_iso()
        if self._db and fire_id:
            # 사격 시점 row — hit/distance 는 NULL (인간 판정 대기)
            self._db.put("fire_events",
                         (config.ROBOT_ID, ts, target_ref, None, None,
                          operator, fire_id, target_alert_id))
        self._emit({"type": "fire", "ts": ts, "target": target_ref,
                    "hit": None, "distance_m": None, "operator": operator,
                    "fire_id": fire_id, "state": state, "success": success})
        return {"success": success, "fire_id": fire_id, "state": state}

    def record_fire_result(self, fire_id: str, hit: bool,
                           miss_reason: str | None = None):
        """운용자가 inspect 영상 보고 판정 결과 입력. DB UPDATE + WS emit."""
        ts = _now_iso()
        if self._db and self._loop:
            asyncio.run_coroutine_threadsafe(
                self._db.update_fire_result(fire_id, hit, miss_reason),
                self._loop)
        self._emit({"type": "fire_result", "ts": ts, "fire_id": fire_id,
                    "hit": bool(hit), "miss_reason": miss_reason})
        return {"ok": True, "fire_id": fire_id, "hit": hit}

    def pub_weather_cmd(self, payload: dict):
        if self._node:
            self._node.pub_weather_cmd(json.dumps(payload))

    # ---- YOLO 자동사격 (Feature 3) ------------------------------------

    def _on_auto_fire_detected(self, label: str,
                                bbox_cx: float, bbox_cy: float):
        """YOLO 안정 감지 콜백. ROS 스레드 → asyncio 루프에 코루틴 예약."""
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(
            self._auto_fire_async(label, bbox_cx, bbox_cy), self._loop)

    async def _auto_fire_async(self, label: str,
                                cx: float, cy: float):
        """자동사격 시퀀스 (asyncio 코루틴).

        soldier/person/drone 모두 bbox 중심 정밀 조준 후 실사격.
        사격 전후 patrol PAUSE / inspect 방향 고정.
        """
        ts = _now_iso()
        log.info("자동사격 시퀀스 시작: label=%s cx=%.1f cy=%.1f", label, cx, cy)

        # 1. Patrol 일시정지
        self.pub_mission("stop")

        # 정밀 조준: bbox 중심으로 inspect 카메라 회전 (soldier/person/drone 동일)
        self.pub_inspect_cmd({"look_at_pixel": [cx, cy], "absolute": False})
        await asyncio.sleep(0.5)

        # 2. 사격
        loop = asyncio.get_event_loop()
        success, fire_id, state = await loop.run_in_executor(
            None, self._node.call_fire if self._node else lambda: (False, None, "no_node"))

        self._emit({
            "type": "auto_fire", "ts": ts,
            "label": label, "bbox_cx": cx, "bbox_cy": cy,
            "success": success, "fire_id": fire_id, "state": state,
        })
        log.info("자동사격 완료: label=%s success=%s fire_id=%s state=%s",
                 label, success, fire_id, state)


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
            # 2026-05-20: front 제거. rear + inspect + overhead 구독
            self.create_subscription(CompressedImage, T["video_rear"],
                                     lambda m: self._on_video(m, "rear"), sensor_qos)
            self.create_subscription(CompressedImage, T["video_inspect"],
                                     lambda m: self._on_video(m, "inspect"), sensor_qos)
            self.create_subscription(CompressedImage, T["video_overhead"],
                                     lambda m: self._on_video(m, "overhead"), sensor_qos)
            # ---- Tactical Fixed Cameras TP_A ~ TP_D ----
            # depth 는 2026-05-24 부터 PNG 압축본 (CompressedImage 16UC1 320×180) 사용.
            if "video_tp_a" in T:
                for _tp in ("tp_a", "tp_b", "tp_c", "tp_d"):
                    _tp_local = _tp
                    self.create_subscription(
                        CompressedImage, T[f"video_{_tp_local}"],
                        lambda m, cam=_tp_local: self._on_video(m, cam), sensor_qos)
                    self.create_subscription(
                        CompressedImage, T[f"depth_{_tp_local}"],
                        lambda m, cam=_tp_local: self._on_depth(m, cam), sensor_qos)
            self.create_subscription(Log, T["rosout"], self._on_rosout, rel_qos)
            # ---- DMZ Sentry M5/M7 신규 다운링크 ----
            self.create_subscription(String, T["intruders"],
                                     self._on_intruders, rel_qos)
            self.create_subscription(String, T["patrol_state"],
                                     self._on_patrol_state, rel_qos)
            self.create_subscription(String, T["landmarks"],
                                     self._on_landmarks, latched_qos)
            # ---- FALL 감지 (2026-05-21) ----
            self.create_subscription(String, T["fall_alert"],
                                     self._on_fall_alert, rel_qos)
            self.create_subscription(String, T["fall_state"],
                                     self._on_fall_state, rel_qos)
            # ---- Wind / Weapon (2026-05-21) ----
            self.create_subscription(Vector3Stamped, T["wind_state"],
                                     self._on_wind_state, rel_qos)
            self.create_subscription(String, T["weapon_state"],
                                     self._on_weapon_state, latched_qos)
            # ---- Zone 기반 라우팅 (2026-05-22) ----
            self.create_subscription(String, T["routing_state"],
                                     self._on_routing_state, rel_qos)
            # Main-side YOLO 검출 결과 구독 (2026-05-27)
            if "yolo_main_dets" in T:
                self.create_subscription(
                    String, T["yolo_main_dets"],
                    self._on_yolo_main_dets, rel_qos)
            self._weather_pub = self.create_publisher(
                String, T["weather_cmd"], rel_qos)
            # ---- 업링크 발행/클라이언트 ----
            # cmd_vel_manual 로 발행 — safety_filter 가 manual override mux 처리
            # (Nav2 ~20Hz 와 race 방지, manual cmd 1s 우선). 2026-05-26.
            self._cmd_pub  = self.create_publisher(Twist, T["cmd_vel_manual"], rel_qos)
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
                        "video_rear": 0, "video_inspect": 0, "video_overhead": 0,
                        "video_tp_a": 0, "video_tp_b": 0,
                        "video_tp_c": 0, "video_tp_d": 0,
                        "depth_tp_a": 0, "depth_tp_b": 0,
                        "depth_tp_c": 0, "depth_tp_d": 0,
                        "leg": 0, "rosout": 0,
                        "intruders": 0, "patrol_state": 0, "landmarks": 0,
                        "fall_alert": 0, "fall_state": 0,
                        "wind_state": 0, "weapon_state": 0,
                        "routing_state": 0}
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
            # 2026-05-24: gps_track 에 yaw 합류 (D4 — odom 캐시에서 가져옴)
            _odom = self.br.latest.get("odom") or {}
            self.br._db and self.br._db.put("gps_track", (
                config.ROBOT_ID, ts, msg.latitude, msg.longitude,
                float(msg.altitude), _odom.get("x"), _odom.get("y"),
                _odom.get("yaw")))
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
            # WHY: Isaac OG ROS2PublishJointState 는 USD articulation 알파벳 순으로
            # 발행(FL_calf/FL_hip/FL_thigh/…)하지만 웹·URDF 렌더·DiagnosticsStrip 은
            # policy 순(FL_hip/FL_thigh/FL_calf/FR_…)을 기대한다. msg.name 으로 재정렬.
            _POLICY_ORDER = [
                "FL_hip_joint", "FL_thigh_joint", "FL_calf_joint",
                "FR_hip_joint", "FR_thigh_joint", "FR_calf_joint",
                "RL_hip_joint", "RL_thigh_joint", "RL_calf_joint",
                "RR_hip_joint", "RR_thigh_joint", "RR_calf_joint",
            ]
            names = list(msg.name)
            positions = list(msg.position)
            if names and len(names) == len(positions):
                name_idx = {n: i for i, n in enumerate(names)}
                reordered = [
                    positions[name_idx[jn]]
                    if jn in name_idx else 0.0
                    for jn in _POLICY_ORDER
                ]
                self.br.latest["leg_q"] = reordered
            else:
                self.br.latest["leg_q"] = positions
            now = time.monotonic()
            if now - self.br._js_last_log >= 0.1:   # 10 Hz 다운샘플
                self.br._js_last_log = now
                self.br._db and self.br._db.put("joint_snapshots", (
                    config.ROBOT_ID, _now_iso(),
                    [], self.br.latest["leg_q"]))

        def _on_yolo_main_dets(self, msg):
            """Main-side yolo_node 검출 결과 수신 (2026-05-27).

            WHY: YOLO 추론을 Main PC 에서 수행 → C2 CPU 부하 절감.
            결과를 받아 stable-tracker(auto-fire), WebSocket, DB, /alerts 에 전달.
            """
            try:
                data = json.loads(msg.data)
            except Exception:
                return
            camera = data.get("camera", "inspect")
            dets   = data.get("dets", [])
            ts     = data.get("stamp") or _now_iso()

            # bbox overlay 캐시 갱신 (video callback 에서 사용)
            with self.br._dets_lock:
                self.br._last_dets[camera] = dets

            # stable-tracker → auto-fire 콜백
            if self.br._yolo is not None:
                self.br._yolo._update_stable(dets)

            # WebSocket detection 이벤트 + /detections_text 발행
            if dets:
                self.br._emit({"type": "detection", "ts": ts, "items": dets})
                det_msg = String()
                det_msg.data = json.dumps({
                    "stamp": ts, "frame_id": f"camera_{camera}",
                    "detections": dets})
                self._det_pub.publish(det_msg)
                for d in dets:
                    x, y, w, h = d["bbox"]
                    self.br._db and self.br._db.put("detection_events", (
                        ts, config.ROBOT_ID, f"camera_{camera}", "detection",
                        d["class_name"], d["conf"],
                        json.dumps({"x": x, "y": y, "w": w, "h": h}),
                        None, None, None, None, None))

            # intruder alert
            alert = data.get("person_alert")
            if alert:
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
                    f"ALERT intruder={alert['label']} conf={alert['confidence']:.2f}")

            # animal alert
            animal_alert = data.get("animal_alert")
            if animal_alert:
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
                    f"conf={animal_alert['confidence']:.2f}")

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

            # --- 수신 타이밍 로그 (FRAME_TIMING=1 일 때만) ---
            import os as _os
            if _os.environ.get("FRAME_TIMING") == "1" and camera == "inspect":
                _recv_ns = time.time_ns()
                _pub_s   = msg.header.stamp.sec
                _pub_ns_val = msg.header.stamp.nanosec
                _pub_total_ns = _pub_s * 1_000_000_000 + _pub_ns_val
                _net_ms  = (_recv_ns - _pub_total_ns) / 1e6 if _pub_s > 0 else -1
                _prev_recv = getattr(self, "_ft_prev_recv", 0)
                _recv_gap = (_recv_ns / 1e9 - _prev_recv) * 1000 if _prev_recv else 0
                self._ft_prev_recv = _recv_ns / 1e9
                _yolo_busy = (
                    "inspect" in self.br._yolo_futures
                    and not self.br._yolo_futures["inspect"].done()
                )
                _flag = ""
                if _recv_gap > 300 and _prev_recv:
                    _flag += f"  ← recv_gap {_recv_gap:.0f}ms !!!"
                if _net_ms > 200:
                    _flag += f"  ← net {_net_ms:.0f}ms !!!"
                self.get_logger().info(
                    f"[FT] RECV #{self._rx[key]:05d} "
                    f"recv_gap={_recv_gap:.0f}ms net={_net_ms:.1f}ms "
                    f"yolo_busy={_yolo_busy}{_flag}")

            arr = np.frombuffer(bytes(msg.data), dtype=np.uint8)
            bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if bgr is None:
                return

            # WHY: 캐시된 이전 프레임 탐지 결과로 bbox 오버레이 후 즉시 프레임 저장.
            # YOLO 추론(50-200ms) 전에 _set_video_frame 을 호출해야 MJPEG 폴러가
            # 200ms 주기 안에 최신 프레임을 획득할 수 있다.
            # bbox lag: 최대 1프레임(200ms @ 5fps) — 운용상 허용.
            if camera == "inspect":
                with self.br._dets_lock:
                    _cached = list(self.br._last_dets.get("inspect") or [])
                for _d in _cached:
                    _x, _y, _w, _h = _d["bbox"]
                    cv2.rectangle(bgr, (int(_x), int(_y)),
                                  (int(_x + _w), int(_y + _h)), (0, 0, 255), 2)
                    cv2.putText(bgr, f'{_d["class_name"]} {_d["conf"]:.2f}',
                                (int(_x), int(_y) - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
            self.br._set_video_frame(bgr, camera)

            # inspect 카메라: C2 로컬 YOLO 추론 (config.YOLO_CAMERAS 로 채널 제한)
            # WHY: 추론을 ThreadPoolExecutor(max_workers=1)에 submit해 ROS callback thread
            # 를 즉시 반환. 이전 추론이 아직 실행 중이면 이번 프레임은 drop(추론 병목 방지).
            if (self.br._yolo is not None and camera == "inspect"
                    and "inspect" in config.YOLO_CAMERAS):
                prev = self.br._yolo_futures.get("inspect")
                if prev is None or prev.done():
                    node_ref = self   # closure
                    frame_copy = bgr.copy()

                    def _run_yolo_inspect(br=self.br, node=node_ref,
                                         frame=frame_copy):
                        try:
                            dets, alert, animal_alert = br._yolo.infer_with_alerts(frame)
                        except Exception as _e:
                            log.warning("YOLO inspect 추론 실패: %r", _e)
                            return
                        with br._dets_lock:
                            br._last_dets["inspect"] = dets
                        if dets:
                            ts = _now_iso()
                            frame_id = "camera_inspect"
                            for d in dets:
                                br._db and br._db.put("detection_events", (
                                    ts, config.ROBOT_ID, frame_id, "detection",
                                    d["class_name"], d["conf"],
                                    json.dumps({"x": d["bbox"][0], "y": d["bbox"][1],
                                                "w": d["bbox"][2], "h": d["bbox"][3]}),
                                    None, None, None, None, None))
                            br._emit({"type": "detection", "ts": ts, "items": dets})
                            det_msg = String()
                            det_msg.data = json.dumps({"stamp": ts,
                                                       "frame_id": frame_id,
                                                       "detections": dets})
                            node._det_pub.publish(det_msg)
                        if alert:
                            ts = ts if dets else _now_iso()
                            a_msg = String(); a_msg.data = json.dumps(alert)
                            node._alerts_pub.publish(a_msg)
                            x1, y1, x2, y2 = alert["bbox_xyxy"]
                            br._db and br._db.put("alerts", (
                                config.ROBOT_ID, ts, alert["level"], alert["event"],
                                float(alert["confidence"]),
                                json.dumps([x1, y1, x2, y2]),
                                int(alert["count"]), False))
                            br._emit({"type": "alert", "ts": ts, "data": alert})
                        if animal_alert:
                            ts = ts if dets else _now_iso()
                            aa_msg = String(); aa_msg.data = json.dumps(animal_alert)
                            node._animal_pub.publish(aa_msg)
                            x1, y1, x2, y2 = animal_alert["bbox_xyxy"]
                            br._db and br._db.put("alerts", (
                                config.ROBOT_ID, ts, animal_alert["level"],
                                animal_alert["event"],
                                float(animal_alert["confidence"]),
                                json.dumps([x1, y1, x2, y2]),
                                int(animal_alert["count"]), False))
                            br._emit({"type": "animal_alert", "ts": ts,
                                      "data": animal_alert})

                    self.br._yolo_futures["inspect"] = \
                        self.br._yolo_executor.submit(_run_yolo_inspect)
            # TP cameras: run YOLO + 3D projection (config.YOLO_CAMERAS 로 채널 제한)
            _tp_cameras = {"tp_a", "tp_b", "tp_c", "tp_d"}
            if (self.br._yolo is not None and camera in _tp_cameras
                    and camera in config.YOLO_CAMERAS):
                dets, alert, animal_alert = self.br._yolo.infer_with_alerts(bgr)
                if dets:
                    ts = _now_iso()
                    frame_id = f"camera_{camera}"
                    for d in dets:
                        d["camera"] = camera
                        d["frame_id"] = frame_id
                        d["risk"] = "danger" if d.get("class_name", "").lower() in ("person", "soldier") else "caution"
                        map_pos = self._project_detection_to_map(camera, d, bgr.shape)
                        if map_pos is not None:
                            d["map"] = map_pos
                        x, y, w, h = d["bbox"]
                        cv2.rectangle(bgr, (int(x), int(y)),
                                      (int(x+w), int(y+h)), (0, 0, 255), 2)
                        label = f'{d["class_name"]} {d["conf"]:.2f}'
                        if "map" in d and d["map"].get("range_m") is not None:
                            label += f' {d["map"]["range_m"]:.1f}m'
                        cv2.putText(bgr, label, (int(x), int(y)-5),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
                        # 2026-05-24: detection_events 통합 + world 좌표 포함
                        _map = d.get("map") or {}
                        self.br._db and self.br._db.put("detection_events", (
                            ts, config.ROBOT_ID, frame_id, "detection",
                            d["class_name"], d["conf"],
                            json.dumps({"x": x, "y": y, "w": w, "h": h}),
                            _map.get("x"), _map.get("y"), _map.get("z"),
                            None, None))
                    self.br._emit({"type": "detection", "ts": ts, "items": dets})
                    det_msg = String()
                    det_msg.data = json.dumps({"stamp": ts, "frame_id": frame_id,
                                               "detections": dets})
                    self._det_pub.publish(det_msg)

        def _decode_depth(self, msg):
            """2026-05-24: CompressedImage(PNG 16UC1 mm) 디코드 →
            meter 단위 float32 ndarray. 구 raw Image 도 호환 (격리 전환기).
            """
            # NEW: CompressedImage 경로 (Main 측 depth_degrade_node 가 보내는 PNG)
            fmt = getattr(msg, "format", "")
            if fmt:
                buf = np.frombuffer(bytes(msg.data), dtype=np.uint8)
                # cv2.imdecode IMREAD_UNCHANGED 로 16UC1 PNG 보존
                arr = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
                if arr is None:
                    return None
                if arr.dtype == np.uint16:
                    return (arr.astype(np.float32) / 1000.0)
                return arr.astype(np.float32, copy=False)

            # LEGACY: 구 sensor_msgs/Image raw 경로 (이미 unsubscribe 예정)
            h, w = int(msg.height), int(msg.width)
            enc = (msg.encoding or "").lower()
            raw = bytes(msg.data)
            if enc in ("32fc1", "float32"):
                arr = np.frombuffer(raw, dtype=np.float32).reshape(h, -1)[:, :w]
            elif enc in ("16uc1", "mono16"):
                arr = (np.frombuffer(raw, dtype=np.uint16).reshape(h, -1)[:, :w]
                       .astype(np.float32) / 1000.0)
            elif enc in ("8uc1", "mono8"):
                arr = np.frombuffer(raw, dtype=np.uint8).reshape(h, -1)[:, :w].astype(np.float32)
            else:
                return None
            return arr.astype(np.float32, copy=False)

        def _on_depth(self, msg, camera: str):
            key = f"depth_{camera}"
            self._rx[key] = self._rx.get(key, 0) + 1
            arr = self._decode_depth(msg)
            if arr is None:
                if self._rx[key] == 1:
                    self.get_logger().warn(
                        f"{camera} depth encoding 미지원: {msg.encoding}")
                return
            self.br._set_depth_frame(camera, arr)

        def _sample_depth(self, camera: str, det: dict,
                          image_shape: tuple):
            depth = self.br._get_depth_frame(camera)
            if depth is None:
                return None
            ih, iw = image_shape[:2]
            dh, dw = depth.shape[:2]
            x, y, w, h = det["bbox"]
            label = str(det.get("class_name", "")).lower()
            if label in ("person", "soldier"):
                cx, cy = x + w*0.5, y + h*0.30
                rw, rh = max(4.0, w*0.18), max(4.0, h*0.18)
            else:
                cx, cy = x + w*0.5, y + h*0.5
                rw, rh = max(4.0, w*0.25), max(4.0, h*0.25)
            sx, sy = dw/max(float(iw), 1.0), dh/max(float(ih), 1.0)
            x0 = max(0, int((cx-rw)*sx));  x1 = min(dw, int((cx+rw)*sx)+1)
            y0 = max(0, int((cy-rh)*sy));  y1 = min(dh, int((cy+rh)*sy)+1)
            if x1 <= x0 or y1 <= y0:
                return None
            roi = depth[y0:y1, x0:x1]
            vals = roi[np.isfinite(roi)]
            vals = vals[(vals > 0.2) & (vals < 350.0)]
            if vals.size == 0:
                return None
            return {"depth_m": float(np.median(vals)), "u": float(cx), "v": float(cy)}

        @staticmethod
        def _norm3(v):
            n = math.sqrt(float(v[0])**2 + float(v[1])**2 + float(v[2])**2)
            if n < 1e-6:
                return (0.0, 1.0, 0.0)
            return (float(v[0])/n, float(v[1])/n, float(v[2])/n)

        def _project_detection_to_map(self, camera: str, det: dict,
                                      image_shape: tuple):
            if camera not in config.TACTICAL_CAMERA_FORWARDS:
                return None
            lm = self.br.latest.get("landmarks") or {}
            if not lm.get("tactical_points"):
                try:
                    with open("/tmp/cobot3_landmarks.json", "r") as f:
                        lm = json.load(f)
                    self.br.latest["landmarks"] = lm
                    self.br._emit({"type": "landmarks", "ts": _now_iso(), "data": lm})
                except Exception:
                    pass
            tps = lm.get("tactical_points") or {}
            tp = tps.get(camera.upper())
            if not tp:
                return None
            ih, iw = image_shape[:2]
            depth_sample = self._sample_depth(camera, det, image_shape)
            source = "depth" if depth_sample is not None else "ray_guess"
            if depth_sample is None:
                depth_m = config.TACTICAL_DEFAULT_RANGE_M
                x, y, w, h = det["bbox"]
                sample_u, sample_v = x + w*0.5, y + h*0.30
            else:
                depth_m = float(depth_sample["depth_m"])
                sample_u, sample_v = float(depth_sample["u"]), float(depth_sample["v"])

            fwd = self._norm3(config.TACTICAL_CAMERA_FORWARDS[camera])
            rx, ry = fwd[1], -fwd[0]
            rn = math.sqrt(rx*rx + ry*ry)
            if rn > 1e-6:
                rx, ry = rx/rn, ry/rn
            fx_px = (float(iw) / config.TACTICAL_CAMERA_APERTURE * config.TACTICAL_CAMERA_FOCAL)
            x_norm = (sample_u - iw*0.5) / max(fx_px, 1.0)
            y_norm = (sample_v - ih*0.5) / max(fx_px, 1.0)
            ux = ry * fwd[2];  uy = -rx * fwd[2]
            cam_z = (float(tp.get("z", 0.0)) + config.TACTICAL_CAMERA_HEIGHT
                     + config.TACTICAL_CAMERA_HEIGHT_OFFSETS.get(camera, 0.0))
            world_x = float(tp["x"]) + depth_m*(fwd[0] + rx*x_norm - ux*y_norm)
            world_y = float(tp["y"]) + depth_m*(fwd[1] + ry*x_norm - uy*y_norm)
            world_z = cam_z + depth_m*(fwd[2] - (rx*fwd[1]-ry*fwd[0])*y_norm)
            home = lm.get("home") or {}
            origin_x = float(home.get("x", 0.0))
            origin_y = float(home.get("y", 0.0))
            origin_z = float(home.get("z", 0.0))
            ground_range_m = math.hypot(world_x - float(tp["x"]), world_y - float(tp["y"]))
            return {
                "x": world_x - origin_x, "y": world_y - origin_y, "z": world_z - origin_z,
                "world_x": world_x, "world_y": world_y, "world_z": world_z,
                "range_m": depth_m, "ground_range_m": ground_range_m,
                "depth_camera": camera, "source": source,
            }

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
                    # 2026-05-24: detection_events 통합 (kind='gt_state')
                    self.br._db and self.br._db.put("detection_events", (
                        ts, config.ROBOT_ID, "ground_truth", "gt_state",
                        str(it.get("label", "")) or None,
                        None,    # confidence (GT는 None)
                        None,    # bbox_pixel
                        float(it.get("x", 0.0)),
                        float(it.get("y", 0.0)),
                        float(it.get("z", 0.0)),
                        None,    # beyond_fence
                        str(it.get("id", "?"))))

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

        def _on_fall_alert(self, msg):
            self._rx["fall_alert"] += 1
            try:
                d = json.loads(msg.data)
            except Exception:
                return
            self.br.latest["fall_alert"] = d
            ts = _now_iso()
            self.br._emit({"type": "fall_alert", "ts": ts, "data": d})
            # DB alerts 테이블 재사용 — level=ALERT 일 때만 영구 저장 (FALLEN edge)
            if str(d.get("level", "")).upper() == "ALERT" and self.br._db:
                self.br._db.put("alerts", (
                    config.ROBOT_ID, ts,
                    "ALERT", str(d.get("event", "robot_fall_detected")),
                    1.0,
                    json.dumps([]),  # bbox_xyxy 없음
                    1, False))

        def _on_fall_state(self, msg):
            self._rx["fall_state"] += 1
            try:
                d = json.loads(msg.data)
            except Exception:
                return
            self.br.latest["fall_state"] = d

        def _on_wind_state(self, msg):
            self._rx["wind_state"] += 1
            d = {"vx": msg.vector.x, "vy": msg.vector.y, "vz": msg.vector.z}
            # 풍속·풍향 derivation
            import math as _math
            spd = (d["vx"] ** 2 + d["vy"] ** 2) ** 0.5
            dir_deg = _math.degrees(_math.atan2(d["vy"], d["vx"]))
            d["speed"] = spd
            d["dir_deg"] = (dir_deg + 360.0) % 360.0
            self.br.latest["wind_state"] = d
            # 5Hz throttle for WS (20Hz raw → 4 중 1만 emit)
            n = getattr(self, "_wind_throttle", 0) + 1
            self._wind_throttle = n
            if n % 4 == 0:
                self.br._emit({"type": "wind_state", "ts": _now_iso(),
                               "data": d})

        def _on_weapon_state(self, msg):
            self._rx["weapon_state"] += 1
            try:
                d = json.loads(msg.data)
            except Exception:
                return
            prev = self.br.latest.get("weapon_state") or {}
            self.br.latest["weapon_state"] = d
            # 상태 전이만 WS emit
            if prev.get("state") != d.get("state"):
                self.br._emit({"type": "weapon_state", "ts": _now_iso(),
                               "data": d})

        def _on_routing_state(self, msg):
            try:
                d = json.loads(msg.data)
            except Exception:
                return
            self.br._emit({"type": "routing_state", "ts": _now_iso(), "data": d})

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
            """weapon_relay Trigger 호출. 새 규약 (2026-05-21):
            success = 사격 시퀀스 완료 여부 (hit/miss 는 인간 판정)
            message = '{fire_id}|{state}' — completed|timeout|...
            반환: (success: bool, fire_id: str|None, state: str)"""
            if not self._fire_cli.wait_for_service(timeout_sec=1.0):
                self.get_logger().warning("weapon/fire 서비스 없음")
                return False, None, "no_service"
            fut = self._fire_cli.call_async(Trigger.Request())
            t0 = time.monotonic()
            while not fut.done() and time.monotonic() - t0 < 4.0:
                time.sleep(0.02)
            if fut.done() and fut.result() is not None:
                res = fut.result()
                fire_id, state = None, "unknown"
                try:
                    parts = res.message.split("|", 1)
                    fire_id = parts[0] or None
                    state = parts[1] if len(parts) > 1 else "unknown"
                except Exception:
                    pass
                return bool(res.success), fire_id, state
            return False, None, "timeout"

        def pub_weather_cmd(self, payload_json: str):
            m = String()
            m.data = payload_json
            self._weather_pub.publish(m)
