"""Nav2 patrol 컨트롤러 — Go2 정찰 단순화 사양 (2026-05-20).

지통실의 mission_command (sortie/home/stop/resume/idle) 를 받아 Nav2
navigate_to_pose action 으로 전송. 도착 ±10m 사각 판정. stop → PAUSED 진입 +
stop_burst 타이머 (10Hz × 2s) Twist(0) 반복으로 cmd_vel chain 잔여 덮어쓰기.
resume → 보존된 mode + goal 재전송.

I/O:
- 구독: /mission_command (String), /robot/odom (Odometry),
        /scene/landmarks (latched String JSON), /robot/nav/goal (PoseStamped)
- 발행: /patrol_state (5Hz String JSON), /robot/cmd_vel (Twist 정지용)
- Action: /navigate_to_pose (nav2_msgs/NavigateToPose)
"""
import json
import math
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

# 사용자 사양 좌표 (2026-05-20)
DEFAULT_HOME = (212.8, 890.53)
DEFAULT_GOAL = (620.36, 499.72)
ARRIVE_HALF = 10.0   # 도착 판정 ±10m 사각 box

NAV_GOAL_TOPIC = "/robot/nav/goal"   # web 맵 클릭 manual goal


class MissionMode(str, Enum):
    IDLE = "IDLE"
    PATROL = "PATROL"       # → goal (수색위치)
    HOME = "HOME"           # → home
    PAUSED = "PAUSED"       # stop 명령 — mode·goal 보존
    WAITING_FOR_NAV2 = "WAITING_FOR_NAV2"


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

        latched = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )

        self._nav_client = ActionClient(self, NavigateToPose, self._action_name)
        self._cmd_pub = self.create_publisher(Twist, self._cmd_vel_topic, 10)
        self._state_pub = self.create_publisher(String, self._state_topic, 10)
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

    # ── manual nav goal (web map 더블클릭) ─────────────────────────────
    def _on_nav_goal(self, msg: PoseStamped) -> None:
        x = float(msg.pose.position.x)
        y = float(msg.pose.position.y)
        self.get_logger().info(
            f"manual nav goal: ({x:.1f}, {y:.1f}) → PATROL")
        self._mode = MissionMode.PATROL
        self._goal = (x, y)
        self._cancel_current_goal()
        self._goal_arrived = False
        self._send_goal_now(self._goal)

    # ── odom ───────────────────────────────────────────────────────────
    def _on_odom(self, msg: Odometry) -> None:
        position = msg.pose.pose.position
        yaw = _yaw_from_quaternion(msg.pose.pose.orientation)
        self._pose = (float(position.x), float(position.y), float(yaw))
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
            self._mode = MissionMode.PATROL
            self._goal_arrived = False
            self._send_goal_now(self._goal)
            self.get_logger().info(f"mission: sortie → goal={self._goal}")
        elif command in ("home", "go_home", "return_home", "rtb"):
            self._mode = MissionMode.HOME
            self._goal_arrived = False
            self._send_goal_now(self._home)
            self.get_logger().info(f"mission: home → {self._home}")
        elif command in ("stop", "halt", "pause"):
            # mode 보존
            if self._mode in (MissionMode.PATROL, MissionMode.HOME):
                self._paused_from_mode = self._mode
                self._paused_goal = (self._goal if self._mode == MissionMode.PATROL
                                     else self._home)
            self._mode = MissionMode.PAUSED
            self._cancel_current_goal()
            self._publish_stop()
            self._stop_burst_until = time.monotonic() + self._stop_burst_seconds
            self.get_logger().info(
                f"mission: stop → PAUSED (보존={self._paused_from_mode.value}, "
                f"goal={self._paused_goal}, stop_burst {self._stop_burst_seconds}s)")
        elif command in ("resume", "continue"):
            if self._mode == MissionMode.PAUSED and self._paused_goal:
                self._mode = self._paused_from_mode
                self._goal_arrived = False
                self._send_goal_now(self._paused_goal)
                self.get_logger().info(
                    f"mission: resume → {self._mode.value} goal={self._paused_goal}")
            else:
                self.get_logger().info("resume 무시 (PAUSED 아님)")
        elif command in ("idle", "standby"):
            self._mode = MissionMode.IDLE
            self._cancel_current_goal()
            self._publish_stop()
            self.get_logger().info("mission: idle")
        else:
            self.get_logger().warn(f"unknown mission command: {msg.data}")

    # ── action client ─────────────────────────────────────────────────
    def _send_goal_now(self, point) -> None:
        if not self._nav_client.server_is_ready():
            self._mode = MissionMode.WAITING_FOR_NAV2
            self.get_logger().warn("navigate_to_pose action 미준비")
            return
        self._cancel_current_goal()
        self._current_goal = (float(point[0]), float(point[1]))
        goal = NavigateToPose.Goal()
        goal.pose = self._make_pose(self._current_goal)
        self.get_logger().info(
            f"action goal: x={self._current_goal[0]:.1f} y={self._current_goal[1]:.1f}")
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
        if status == GoalStatus.STATUS_SUCCEEDED:
            self.get_logger().info("Nav2 goal 성공 (도착 사각 판정과 별개)")
        else:
            self.get_logger().warn(f"Nav2 goal 종료 status={status}")

    def _cancel_current_goal(self) -> None:
        if self._goal_handle is not None:
            self._goal_handle.cancel_goal_async()
            self._goal_handle = None

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
