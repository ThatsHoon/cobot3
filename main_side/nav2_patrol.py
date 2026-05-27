"""Nav2 patrol 컨트롤러 — Go2 정찰 단순화 사양 (2026-05-20).

지통실의 mission_command (sortie/home/stop/resume/idle/goto_tp:TP_X) 를 받아 Nav2
navigate_to_pose action 으로 전송. 도착 ±10m 사각 판정. stop → PAUSED 진입 +
stop_burst 타이머 (10Hz × 2s) Twist(0) 반복으로 cmd_vel chain 잔여 덮어쓰기.
resume → 보존된 mode + goal 재전송.
goto_tp:TP_X → ROUTING 모드 — ZoneRouter Dijkstra 경로 → zone 순차 경유 → TP 도착.

I/O:
- 구독: /mission_command (String), /robot/odom (Odometry),
        /scene/landmarks (latched String JSON), /robot/nav/goal (PoseStamped)
- 발행: /patrol_state (5Hz String JSON), /routing_state (String JSON), /robot/cmd_vel (Twist 정지용)
- Action: /navigate_to_pose (nav2_msgs/NavigateToPose)
"""
import json
import math
import sys
import os
import time
from enum import Enum

import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped, Quaternion, Twist
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import Odometry
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import (DurabilityPolicy, HistoryPolicy, QoSProfile,
                       ReliabilityPolicy)
from std_msgs.msg import String

# ZoneRouter — 같은 디렉토리에서 import (없으면 경고만, ROUTING 기능 비활성)
try:
    _this_dir = os.path.dirname(os.path.abspath(__file__))
    if _this_dir not in sys.path:
        sys.path.insert(0, _this_dir)
    from zone_router import ZoneRouter as _ZoneRouter
    _ZONE_ROUTER_AVAILABLE = True
except ImportError:
    _ZoneRouter = None
    _ZONE_ROUTER_AVAILABLE = False

# 사용자 사양 좌표 (2026-05-20)
DEFAULT_HOME = (212.8, 890.53)
DEFAULT_GOAL = (287.59, 1129.728)
ARRIVE_HALF = 10.0       # 도착 판정 ±10m 사각 box (PATROL/HOME)
ROUTING_ARRIVE = 3.0     # ROUTING 모드 zone 경유 도착 허용 오차 ±3m

NAV_GOAL_TOPIC = "/robot/nav/goal"   # web 맵 클릭 manual goal


class MissionMode(str, Enum):
    IDLE = "IDLE"
    PATROL = "PATROL"             # → goal (수색위치)
    HOME = "HOME"                 # → home
    PAUSED = "PAUSED"             # stop 명령 — mode·goal 보존
    WAITING_FOR_NAV2 = "WAITING_FOR_NAV2"
    ROUTING = "ROUTING"           # zone 경유 Tactical Point 이동
    AB_PATROL = "AB_PATROL"       # TP_A ↔ TP_B 무한 반복 순찰


def _yaw_from_quaternion(q) -> float:
    siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny_cosp, cosy_cosp)


def _quaternion_from_yaw(yaw: float) -> Quaternion:
    q = Quaternion()
    q.z = math.sin(yaw * 0.5)
    q.w = math.cos(yaw * 0.5)
    return q


class Nav2PatrolController(Node):
    def __init__(self) -> None:
        super().__init__("nav2_patrol_controller")

        self.declare_parameter("mission_topic", "/mission_command")
        self.declare_parameter("odom_topic", "/robot/odom")
        self.declare_parameter("state_topic", "/patrol_state")
        self.declare_parameter("cmd_vel_topic", "/robot/cmd_vel")
        self.declare_parameter("landmarks_topic", "/scene/landmarks")
        self.declare_parameter("action_name", "navigate_to_pose")
        self.declare_parameter("global_frame", "world")
        self.declare_parameter("home_x", DEFAULT_HOME[0])
        self.declare_parameter("home_y", DEFAULT_HOME[1])
        self.declare_parameter("goal_x", DEFAULT_GOAL[0])
        self.declare_parameter("goal_y", DEFAULT_GOAL[1])
        self.declare_parameter("arrive_half", ARRIVE_HALF)
        self.declare_parameter("status_hz", 5.0)
        self.declare_parameter("stop_burst_seconds", 2.0)
        self.declare_parameter("stop_burst_hz", 10.0)

        self._mission_topic = self.get_parameter("mission_topic").value
        self._odom_topic = self.get_parameter("odom_topic").value
        self._state_topic = self.get_parameter("state_topic").value
        self._cmd_vel_topic = self.get_parameter("cmd_vel_topic").value
        self._landmarks_topic = self.get_parameter("landmarks_topic").value
        self._action_name = self.get_parameter("action_name").value
        self._global_frame = self.get_parameter("global_frame").value
        self._home = (float(self.get_parameter("home_x").value),
                      float(self.get_parameter("home_y").value))
        self._goal = (float(self.get_parameter("goal_x").value),
                      float(self.get_parameter("goal_y").value))
        self._arrive_half = float(self.get_parameter("arrive_half").value)
        status_hz = max(1.0, float(self.get_parameter("status_hz").value))
        self._stop_burst_seconds = max(0.0,
            float(self.get_parameter("stop_burst_seconds").value))
        self._stop_burst_hz = max(1.0,
            float(self.get_parameter("stop_burst_hz").value))

        self._mode = MissionMode.IDLE
        # PAUSED 진입 전 보존 (resume 용)
        self._paused_from_mode = MissionMode.PATROL
        self._paused_goal = None
        self._pose = None
        self._current_goal = None
        self._goal_handle = None
        self._landmarks_received = False
        self._stop_burst_until = 0.0
        self._goal_arrived = False
        self._pending_target = None    # cancel done → 이 target 으로 dispatch
        self._diag_ctr = 0             # 5Hz tick 안 5초 주기 lifecycle 진단

        # ROUTING / AB_PATROL 모드 상태
        self._router = None            # ZoneRouter 인스턴스 (landmarks 수신 후 초기화)
        self._sp_world = None          # StartingPoint world (x,y) — odom→world 변환용
        self._route: list = []         # [(x,y), ...] 순차 웨이포인트
        self._route_idx: int = 0       # 현재 목표 웨이포인트 인덱스
        self._route_tp_id: str = ""    # 목표 Tactical Point ID
        self._ab_next_tp: str = "TP_A" # AB_PATROL: 다음에 이동할 TP

        latched = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )

        self._nav_client = ActionClient(self, NavigateToPose, self._action_name)
        self._cmd_pub = self.create_publisher(Twist, self._cmd_vel_topic, 10)
        self._state_pub = self.create_publisher(String, self._state_topic, 10)
        self._routing_state_pub = self.create_publisher(String, "/routing_state", 10)
        self.create_subscription(String, self._mission_topic, self._on_mission, 10)
        self.create_subscription(Odometry, self._odom_topic, self._on_odom, 20)
        self.create_subscription(String, self._landmarks_topic,
                                 self._on_landmarks, latched)
        self.create_subscription(PoseStamped, NAV_GOAL_TOPIC,
                                 self._on_nav_goal, 10)
        self.create_timer(1.0 / status_hz, self._tick)
        # stop_burst 타이머 (PAUSED 진입 시 활성, _stop_burst_until 까지 발행)
        self.create_timer(1.0 / self._stop_burst_hz, self._tick_stop_burst)

        self.get_logger().info(
            f"patrol ready: mission={self._mission_topic} action={self._action_name} "
            f"home=({self._home[0]:.1f},{self._home[1]:.1f}) "
            f"goal=({self._goal[0]:.1f},{self._goal[1]:.1f}) arrive=±{self._arrive_half}m")

    # ── landmarks ──────────────────────────────────────────────────────
    def _on_landmarks(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError as e:
            self.get_logger().warn(f"landmarks JSON parse error: {e}")
            return
        # 사용자 사양: payload.home / payload.goal 우선 (있으면 덮어쓰기)
        h = payload.get("home")
        g = payload.get("goal") or payload.get("cone")
        if h and "x" in h and "y" in h:
            self._home = (float(h["x"]), float(h["y"]))
        if g and "x" in g and "y" in g:
            self._goal = (float(g["x"]), float(g["y"]))
        self._landmarks_received = True
        self.get_logger().info(
            f"landmarks 수신: home=({self._home[0]:.1f},{self._home[1]:.1f}) "
            f"goal=({self._goal[0]:.1f},{self._goal[1]:.1f})")
        # ZoneRouter 초기화 (routing_zones + tactical_points 포함 시).
        # 2026-05-24 라우팅 정확도 개선: StartingPoint world 좌표 캐시 — odom→world 변환 키.
        zones = payload.get("routing_zones", [])
        tps = payload.get("tactical_points", {})
        sp = next((z for z in zones if z["name"] == "StartingPoint"), None)
        if sp:
            self._sp_world = (float(sp["x"]), float(sp["y"]))
        if zones and tps and _ZONE_ROUTER_AVAILABLE:
            edges = payload.get("routing_edges") or None
            tp_zone_map = payload.get("tp_zone_map") or None
            self._router = _ZoneRouter(zones, tps,
                                       routing_edges=edges,
                                       tp_zone_map=tp_zone_map)
            self.get_logger().info(
                f"ZoneRouter 빌드: {self._router.zone_count}개 zone, "
                f"TPs={self._router.available_tps()}, "
                f"edges={len(edges) if edges else 'auto'}, "
                f"tp_zone_map={tp_zone_map or {}}, "
                f"sp_world={self._sp_world}")
        elif zones and tps and not _ZONE_ROUTER_AVAILABLE:
            self.get_logger().warn("zone_router.py import 실패 — ROUTING 기능 비활성")

    # ── manual nav goal (web map 더블클릭) ─────────────────────────────
    def _on_nav_goal(self, msg: PoseStamped) -> None:
        x = float(msg.pose.position.x)
        y = float(msg.pose.position.y)
        self.get_logger().info(
            f"manual nav goal: ({x:.1f}, {y:.1f}) → PATROL")
        # ROUTING 중이었다면 stale route 잔여로 _advance_routing 오작동 방지.
        # paused_goal 도 무효화 — 이전 ROUTING waypoint 로 잘못 복귀 차단.
        self._enter_active_mode_cleanup()
        self._mode = MissionMode.PATROL
        self._goal = (x, y)
        self._cancel_current_goal()
        self._goal_arrived = False
        self._send_goal_now(self._goal)

    def _enter_active_mode_cleanup(self) -> None:
        """새 active 명령(sortie/home/goto_tp/nav_goal/resume) 진입 시 공통 정리.
        - stop_burst 잔여 Twist(0) 발행 즉시 중단 (cmd_vel 충돌 해결)
        - stale ROUTING 상태(route/idx/tp_id) 클리어 — _on_goal_result 의
          _advance_routing 분기에서 엉뚱한 인덱스 점프 방지
        - paused 보존값 무효화 — resume 으로 잘못된 stale goal 복귀 차단
        resume 자체는 본인이 직접 paused_goal/from_mode 사용하므로,
        이 함수 호출 전에 캐쉬해야 함.
        """
        self._stop_burst_until = 0.0
        self._route = []
        self._route_idx = 0
        self._route_tp_id = ""
        self._paused_from_mode = MissionMode.IDLE
        self._paused_goal = None

    # ── odom ───────────────────────────────────────────────────────────
    def _on_odom(self, msg: Odometry) -> None:
        position = msg.pose.pose.position
        yaw = _yaw_from_quaternion(msg.pose.pose.orientation)
        # 2026-05-24: /robot/odom 은 IsaacComputeOdometry 누적 변위 (spawn=0,0 기준 odom 좌표).
        # self._home/_goal/route_waypoints 가 모두 world 좌표라 일관성 위해
        # spawn world (=StartingPoint) 오프셋 적용해 self._pose 를 world 좌표로 저장.
        # _sp_world 미수신 시(landmarks 늦은 join) 임시로 odom 값 유지 — 다음 callback 에서 정상화.
        ox, oy = float(position.x), float(position.y)
        if self._sp_world is not None:
            wx = self._sp_world[0] + ox
            wy = self._sp_world[1] + oy
        else:
            wx, wy = ox, oy
        self._pose = (wx, wy, float(yaw))
        # 도착 사각 박스 판정 (PATROL/HOME 진행 중)
        if self._mode in (MissionMode.PATROL, MissionMode.HOME):
            tgt = self._goal if self._mode == MissionMode.PATROL else self._home
            dx = abs(self._pose[0] - tgt[0])
            dy = abs(self._pose[1] - tgt[1])
            if dx < self._arrive_half and dy < self._arrive_half:
                if not self._goal_arrived:
                    self._goal_arrived = True
                    self._cancel_current_goal()
                    self._publish_stop()
                    self.get_logger().info(
                        f"{self._mode.value} 도착 (사각 ±{self._arrive_half}m) → IDLE 제자리 사수")
                    self._mode = MissionMode.IDLE


    # ── mission_command ───────────────────────────────────────────────
    def _on_mission(self, msg: String) -> None:
        command = msg.data.strip().lower()
        if command in ("start", "start_patrol", "launch", "sortie"):
            # WHY: 자동사격(YOLO)으로 PAUSED된 경우 "출격" = resume(이전 임무 재개).
            # 새 sortie가 아니라 중단점 복귀가 운용 흐름상 자연스럽다.
            if self._mode == MissionMode.PAUSED and self._paused_from_mode is not None:
                self.get_logger().info(
                    "mission: sortie while PAUSED → resume (이전 임무 재개)")
                self._on_mission(type("_M", (), {"data": "resume"})())
                return
            self._enter_active_mode_cleanup()
            self._mode = MissionMode.PATROL
            self._goal_arrived = False
            self._send_goal_now(self._goal)
            self.get_logger().info(f"mission: sortie → goal={self._goal}")
        elif command in ("home", "go_home", "return_home", "rtb"):
            self._enter_active_mode_cleanup()
            self._mode = MissionMode.HOME
            self._goal_arrived = False
            self._send_goal_now(self._home)
            self.get_logger().info(f"mission: home → {self._home}")
        elif command in ("stop", "halt", "pause"):
            # mode 보존
            if self._mode in (MissionMode.PATROL, MissionMode.HOME,
                              MissionMode.ROUTING, MissionMode.AB_PATROL):
                # WHY: AB_PATROL 도 stop 보존 대상 — 빠지면 resume 시 _paused_from_mode=IDLE
                # 로 남아 "저장 goal 없음" 으로 무시되어 순찰 재개 불가.
                self._paused_from_mode = self._mode
                self._paused_goal = (self._goal if self._mode == MissionMode.PATROL
                                     else self._home if self._mode == MissionMode.HOME
                                     else (self._route[self._route_idx]
                                           if self._route else self._home))
            self._mode = MissionMode.PAUSED
            self._cancel_current_goal()
            self._publish_stop()
            self._stop_burst_until = time.monotonic() + self._stop_burst_seconds
            self.get_logger().info(
                f"mission: stop → PAUSED (보존={self._paused_from_mode.value}, "
                f"goal={self._paused_goal}, stop_burst {self._stop_burst_seconds}s)")
        elif command in ("resume", "continue"):
            if self._mode == MissionMode.PAUSED and self._paused_from_mode is not None:
                _resume_mode = self._paused_from_mode
                _resume_goal = self._paused_goal
                self._enter_active_mode_cleanup()
                if _resume_mode == MissionMode.AB_PATROL:
                    # WHY: AB_PATROL resume은 _paused_goal 복원이 아니라
                    # _ab_next_tp 방향으로 라우팅 재시작이 올바른 재개 방식.
                    self._mode = MissionMode.AB_PATROL
                    self._goal_arrived = False
                    self.get_logger().info(
                        f"mission: resume AB_PATROL → {self._ab_next_tp} 재출발")
                    self._start_routing(self._ab_next_tp)
                elif _resume_goal:
                    self._mode = _resume_mode
                    self._goal_arrived = False
                    self._send_goal_now(_resume_goal)
                    self.get_logger().info(
                        f"mission: resume → {self._mode.value} goal={_resume_goal}")
                else:
                    self.get_logger().info("resume 무시 (저장 goal 없음)")
            else:
                self.get_logger().info("resume 무시 (PAUSED 아님)")
        elif command in ("idle", "standby"):
            self._mode = MissionMode.IDLE
            self._cancel_current_goal()
            self._publish_stop()
            self.get_logger().info("mission: idle")
        elif command in ("ab_patrol", "start_ab_patrol"):
            # WHY: 이미 AB_PATROL 진행 중이면 중복 재시작 무시 — 버튼 연타 방지.
            if self._mode == MissionMode.AB_PATROL:
                self.get_logger().info("mission: AB_PATROL 이미 진행 중 — 무시")
                return
            self._ab_next_tp = "TP_A"
            self._enter_active_mode_cleanup()
            self._mode = MissionMode.AB_PATROL
            self._goal_arrived = False
            self.get_logger().info("mission: AB_PATROL → TP_A → TP_B 무한 순찰 시작")
            self._start_routing("TP_A")
        elif command.startswith("goto_tp:"):
            tp_id = command[8:].upper().strip()
            self._start_routing(tp_id)
        else:
            self.get_logger().warn(f"unknown mission command: {msg.data}")

    # ── action client ─────────────────────────────────────────────────
    def _send_goal_now(self, point) -> None:
        """Mode 전환 시 호출. 진행 중 goal 가 있으면 cancel 의 done callback
        에서 dispatch — cancel→send race 제거 (2026-05-20 fix: 복귀/재할당
        명령 무시 증상).
        """
        if not self._nav_client.server_is_ready():
            if not self._nav_client.wait_for_server(timeout_sec=2.0):
                self._mode = MissionMode.WAITING_FOR_NAV2
                self.get_logger().warn(
                    "navigate_to_pose action 미준비 (2s wait 실패)")
                return
        target = (float(point[0]), float(point[1]))
        if self._goal_handle is not None:
            gh = self._goal_handle
            self._goal_handle = None
            self._pending_target = target
            self.get_logger().info(
                f"이전 goal cancel → done callback 안에서 새 goal({target}) 전송")
            fut = gh.cancel_goal_async()
            fut.add_done_callback(self._on_cancel_done)
        else:
            self._dispatch_goal(target)

    def _on_cancel_done(self, future) -> None:
        try:
            future.result()
        except Exception as e:
            self.get_logger().warn(f"cancel 응답 처리 예외: {e!r}")
        tgt = self._pending_target
        self._pending_target = None
        if tgt is not None:
            self._dispatch_goal(tgt)

    def _dispatch_goal(self, point) -> None:
        self._current_goal = point
        goal = NavigateToPose.Goal()
        goal.pose = self._make_pose(self._current_goal)
        self.get_logger().info(
            f"action goal: x={point[0]:.1f} y={point[1]:.1f}")
        send_future = self._nav_client.send_goal_async(goal)
        send_future.add_done_callback(self._on_goal_response)

    def _make_pose(self, point) -> PoseStamped:
        pose = PoseStamped()
        pose.header.frame_id = self._global_frame
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.position.x = float(point[0])
        pose.pose.position.y = float(point[1])
        pose.pose.orientation = _quaternion_from_yaw(0.0)
        return pose

    def _on_goal_response(self, future) -> None:
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().warn("goal 거부됨")
            self._goal_handle = None
            return
        self._goal_handle = goal_handle
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self._on_goal_result)

    def _on_goal_result(self, future) -> None:
        self._goal_handle = None
        status = future.result().status
        if self._mode in (MissionMode.PAUSED, MissionMode.IDLE):
            return
        # WHY: AB_PATROL 도 ROUTING 과 동일하게 waypoint 진행 처리해야 한다.
        # 기존 ROUTING 만 체크하면 AB_PATROL 에서 _advance_routing 이 호출되지 않아
        # 첫 waypoint 후 로봇이 영구 정지하는 버그 발생.
        if self._mode in (MissionMode.ROUTING, MissionMode.AB_PATROL) \
                and status == GoalStatus.STATUS_SUCCEEDED:
            self._advance_routing()
        elif status != GoalStatus.STATUS_SUCCEEDED:
            self.get_logger().warn(f"Nav2 goal 종료 status={status}")
            if self._mode in (MissionMode.ROUTING, MissionMode.AB_PATROL) \
                    and self._route:
                # WHY: Nav2 가 ABORT(status=6) 등을 반환해도 ROUTING/AB_PATROL 을 이어가야 한다.
                # 현재 waypoint 를 그대로 재시도 — 장애물 일시적 막힘·controller
                # timeout 등 일과성 실패에서 스스로 회복.
                # _pending_target 이 있으면 새 goal 이 이미 발송 대기 중이므로 재시도 불필요.
                if self._pending_target is None and self._goal_handle is None:
                    next_wp = self._route[self._route_idx]
                    self.get_logger().info(
                        f"ROUTING ABORT 재시도 [{self._route_idx}/{len(self._route)}]: "
                        f"({next_wp[0]:.1f},{next_wp[1]:.1f})")
                    self._send_goal_now(next_wp)

    def _advance_routing(self) -> None:
        self._route_idx += 1
        if self._route_idx >= len(self._route):
            if self._mode == MissionMode.AB_PATROL:
                # WHY: AB_PATROL은 TP_A/TP_B 완료 즉시 반대 TP로 재출발.
                # _enter_active_mode_cleanup 을 거치지 않아 AB_PATROL mode를 유지.
                prev_tp = self._route_tp_id
                self._ab_next_tp = "TP_B" if self._ab_next_tp == "TP_A" else "TP_A"
                self._route = []
                self._route_idx = 0
                self._route_tp_id = ""
                self.get_logger().info(
                    f"AB_PATROL: {prev_tp} 도착 → 다음 {self._ab_next_tp} 출발")
                self._publish_routing_state(completed=True)
                self._start_routing(self._ab_next_tp)
            else:
                self._mode = MissionMode.IDLE
                self._publish_stop()
                self.get_logger().info(
                    f"ROUTING 완료: {self._route_tp_id} 도착")
                self._publish_routing_state(completed=True)
        else:
            next_wp = self._route[self._route_idx]
            self.get_logger().info(
                f"ROUTING zone 통과 [{self._route_idx}/{len(self._route)}] "
                f"→ 다음 ({next_wp[0]:.1f},{next_wp[1]:.1f})")
            self._send_goal_now(next_wp)
            self._publish_routing_state()

    def _cancel_current_goal(self) -> None:
        if self._goal_handle is not None:
            self._goal_handle.cancel_goal_async()
            self._goal_handle = None

    # ── routing ───────────────────────────────────────────────────────
    def _start_routing(self, tp_id: str) -> None:
        if not _ZONE_ROUTER_AVAILABLE:
            self.get_logger().error("ZoneRouter 미사용 — zone_router.py import 실패")
            return
        if self._router is None:
            self.get_logger().warn(
                "goto_tp: ZoneRouter 미초기화 (landmarks 미수신). sortie 전 landmarks 확인 필요.")
            return
        if self._pose is None:
            self.get_logger().warn("goto_tp: odom 미수신 — 로봇 위치 불명")
            return
        waypoints = self._router.plan(self._pose[:2], tp_id)
        if not waypoints:
            self.get_logger().warn(
                f"goto_tp: {tp_id} 경로 없음 (TP 미존재 또는 zone 그래프 단절)")
            return
        # WHY: AB_PATROL 재진입 시 mode를 보존해야 _advance_routing이 루프를 유지.
        # 일반 goto_tp 는 ROUTING으로 전환.
        _preserve_ab = self._mode == MissionMode.AB_PATROL
        self._enter_active_mode_cleanup()
        self._mode = MissionMode.AB_PATROL if _preserve_ab else MissionMode.ROUTING
        self._route = waypoints
        self._route_idx = 0
        self._route_tp_id = tp_id
        self._goal_arrived = False
        # WHY: _cancel_current_goal() 별도 호출 제거 — _send_goal_now 가 기존 goal 을
        # cancel 후 _pending_target 에 저장하고 _on_cancel_done 에서 안전하게 dispatch.
        # 별도 cancel 후 즉시 dispatch 시 cancel 결과 콜백(_on_goal_result)이 새 goal
        # handle 을 None 으로 덮어쓰는 race condition 발생 가능.
        self.get_logger().info(
            f"ROUTING 시작: tp={tp_id} 총 {len(waypoints)}개 waypoint "
            f"첫 목표=({waypoints[0][0]:.1f},{waypoints[0][1]:.1f})")
        self._send_goal_now(self._route[0])
        self._publish_routing_state()

    def _publish_routing_state(self, completed: bool = False) -> None:
        payload = {
            "tp_id": self._route_tp_id,
            "route": [{"x": p[0], "y": p[1]} for p in self._route],
            "current_idx": self._route_idx,
            "total": len(self._route),
            "completed": completed,
            "pose": (
                {"x": self._pose[0], "y": self._pose[1], "yaw": self._pose[2]}
                if self._pose else None
            ),
        }
        msg = String()
        msg.data = json.dumps(payload)
        self._routing_state_pub.publish(msg)

    # ── stop publish ──────────────────────────────────────────────────
    def _publish_stop(self) -> None:
        self._cmd_pub.publish(Twist())

    def _tick_stop_burst(self) -> None:
        """PAUSED/IDLE 진입 후 stop_burst_seconds 동안 Twist(0) 반복.
        velocity_smoother 잔여 발행을 덮어쓰기 위한 burst."""
        now = time.monotonic()
        if now < self._stop_burst_until:
            self._publish_stop()

    def _tick(self) -> None:
        # WAITING_FOR_NAV2 에서 server ready 시 자동 재전송 (마지막 모드의 goal)
        if (self._mode == MissionMode.WAITING_FOR_NAV2
                and self._nav_client.server_is_ready()):
            self.get_logger().info("nav2 ready → goal 재전송")
            self._mode = MissionMode.PATROL
            self._goal_arrived = False
            self._send_goal_now(self._goal)
        # 5Hz tick 안 5초 주기 lifecycle 진단 (action server_ready + 핸들 상태)
        self._diag_ctr += 1
        if self._diag_ctr >= 25:
            self._diag_ctr = 0
            self.get_logger().info(
                f"[diag] mode={self._mode.value} "
                f"nav_ready={self._nav_client.server_is_ready()} "
                f"goal_handle={'O' if self._goal_handle else 'X'} "
                f"pending={self._pending_target} arrived={self._goal_arrived}")
        self._publish_state()

    def _publish_state(self) -> None:
        payload = {
            "mode": self._mode.value,
            "waypoint": (
                {"x": self._current_goal[0], "y": self._current_goal[1]}
                if self._current_goal else None),
            "home": {"x": self._home[0], "y": self._home[1]},
            "goal": {"x": self._goal[0], "y": self._goal[1]},
            "arrive_half": self._arrive_half,
            "goal_arrived": self._goal_arrived,
            "pose": (
                {"x": self._pose[0], "y": self._pose[1], "yaw": self._pose[2]}
                if self._pose else None),
            "landmarks_received": self._landmarks_received,
            "routing": (
                {"tp_id": self._route_tp_id,
                 "idx": self._route_idx,
                 "total": len(self._route)}
                if self._mode in (MissionMode.ROUTING, MissionMode.AB_PATROL) else None
            ),
        }
        msg = String()
        msg.data = json.dumps(payload)
        self._state_pub.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = Nav2PatrolController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
