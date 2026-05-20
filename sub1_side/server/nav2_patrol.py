"""Nav2 patrol 컨트롤러 — cobot3 Go2 적용 (DMZ Sentry 골격 차용).

웹 / FastAPI 의 mission_command 를 받아 Nav2 navigate_to_pose action 으로
순차 전송. alerts 가 들어오면 ALERT_STOP 으로 전환해 정지, alert_hold 후
이전 모드로 자동 복귀(M0 게이트).

waypoint 는 /scene/landmarks (RELIABLE+TRANSIENT_LOCAL latched) 1회 수신해
구성. 수신 실패 시 ros2 parameter fallback.

I/O:
- 구독: /mission_command (String)  — sortie/home/stop/resume/idle
        /alerts          (String JSON)
        /robot/odom      (Odometry)
        /scene/landmarks (String JSON, latched)
- 발행: /patrol_state    (String JSON, 5Hz)
        /robot/cmd_vel   (Twist, 정지 명령용)
- Action: /navigate_to_pose (nav2_msgs/NavigateToPose)

실행:
    python3 sub1_side/server/nav2_patrol.py
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


class MissionMode(str, Enum):
    IDLE = "IDLE"
    WAITING_FOR_NAV2 = "WAITING_FOR_NAV2"
    PATROL = "PATROL"
    HOME = "HOME"
    ALERT_STOP = "ALERT_STOP"
    STOPPED = "STOPPED"


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
        self.declare_parameter("alerts_topic", "/alerts")
        self.declare_parameter("odom_topic", "/robot/odom")
        self.declare_parameter("state_topic", "/patrol_state")
        self.declare_parameter("cmd_vel_topic", "/robot/cmd_vel")
        self.declare_parameter("landmarks_topic", "/scene/landmarks")
        self.declare_parameter("action_name", "navigate_to_pose")
        self.declare_parameter("global_frame", "world")
        # gp_scene 기본값 (이전 세션 측정치). landmarks 수신 시 덮어쓰기.
        self.declare_parameter("home_x", -714.32)
        self.declare_parameter("home_y", 952.93)
        self.declare_parameter("patrol_x", -937.07)
        self.declare_parameter("patrol_y", 938.98)
        self.declare_parameter("status_hz", 5.0)
        self.declare_parameter("alert_hold_seconds", 6.0)

        self._mission_topic = self.get_parameter("mission_topic").value
        self._alerts_topic = self.get_parameter("alerts_topic").value
        self._odom_topic = self.get_parameter("odom_topic").value
        self._state_topic = self.get_parameter("state_topic").value
        self._cmd_vel_topic = self.get_parameter("cmd_vel_topic").value
        self._landmarks_topic = self.get_parameter("landmarks_topic").value
        self._action_name = self.get_parameter("action_name").value
        self._global_frame = self.get_parameter("global_frame").value
        self._home = (float(self.get_parameter("home_x").value),
                      float(self.get_parameter("home_y").value))
        self._patrol_waypoints = [
            self._home,
            (float(self.get_parameter("patrol_x").value),
             float(self.get_parameter("patrol_y").value)),
        ]
        status_hz = max(1.0, float(self.get_parameter("status_hz").value))
        self._alert_hold_seconds = max(0.0,
            float(self.get_parameter("alert_hold_seconds").value))

        self._mode = MissionMode.IDLE
        self._resume_mode = MissionMode.PATROL
        self._pose = None
        self._current_goal = None
        self._route_queue = []
        self._next_patrol_index = 1
        self._goal_handle = None
        self._last_alert_time = 0.0
        self._landmarks_received = False

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
        self.create_subscription(String, self._alerts_topic, self._on_alert, 10)
        self.create_subscription(Odometry, self._odom_topic, self._on_odom, 20)
        self.create_subscription(String, self._landmarks_topic,
                                 self._on_landmarks, latched)
        self.create_timer(1.0 / status_hz, self._tick)

        self.get_logger().info(
            "patrol ready: mission=%s action=%s frame=%s home=(%.1f,%.1f) "
            "patrol=(%.1f,%.1f)" % (
                self._mission_topic, self._action_name, self._global_frame,
                self._home[0], self._home[1],
                self._patrol_waypoints[1][0], self._patrol_waypoints[1][1]))

    def _on_landmarks(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError as e:
            self.get_logger().warn(f"landmarks JSON parse error: {e}")
            return
        # zone 분기 (P2): "dmz" 면 DMZ_Zone 의 home/patrol 우선, "cube"(기본) 면
        # gp_scene 의 Cube/Cone. fence 좌표는 무시 (B5).
        zone = (payload.get("zone") or "cube").lower()
        if zone == "dmz" and payload.get("dmz_home") and payload.get("dmz_cone"):
            home = payload["dmz_home"]
            cone = payload["dmz_cone"]
            extra = payload.get("dmz_patrol_w")
        else:
            home = payload.get("cube") or payload.get("home")
            cone = payload.get("cone")
            extra = None
        if home and "x" in home and "y" in home:
            self._home = (float(home["x"]), float(home["y"]))
        waypoints = []
        if cone and "x" in cone and "y" in cone:
            waypoints.append((float(cone["x"]), float(cone["y"])))
        if extra and "x" in extra and "y" in extra:
            waypoints.append((float(extra["x"]), float(extra["y"])))
        if not waypoints:
            waypoints.append(self._patrol_waypoints[1])
        self._patrol_waypoints = [self._home] + waypoints
        self._landmarks_received = True
        self._zone = zone
        self.get_logger().info(
            f"landmarks 수신: home=({self._home[0]:.1f},{self._home[1]:.1f}) "
            f"waypoints={len(waypoints)}")

    def _on_odom(self, msg: Odometry) -> None:
        position = msg.pose.pose.position
        yaw = _yaw_from_quaternion(msg.pose.pose.orientation)
        self._pose = (float(position.x), float(position.y), float(yaw))

    def _on_mission(self, msg: String) -> None:
        command = msg.data.strip().lower()
        if command in ("start", "start_patrol", "launch", "sortie"):
            self._mode = MissionMode.PATROL
            self._resume_mode = MissionMode.PATROL
            self._set_patrol_route()
            self._send_next_goal()
        elif command in ("home", "go_home", "return_home", "rtb"):
            self._mode = MissionMode.HOME
            self._resume_mode = MissionMode.HOME
            self._set_home_route()
            self._send_next_goal()
        elif command in ("stop", "halt"):
            self._mode = MissionMode.STOPPED
            self._route_queue = []
            self._cancel_current_goal()
            self._publish_stop()
            self.get_logger().info("mission: stop")
        elif command in ("resume", "continue"):
            if self._mode in (MissionMode.ALERT_STOP, MissionMode.STOPPED):
                self._mode = self._resume_mode
                if not self._current_goal:
                    if self._mode == MissionMode.PATROL:
                        self._set_patrol_route()
                    else:
                        self._set_home_route()
                self._send_next_goal()
            self.get_logger().info(f"mission: resume -> {self._mode.value}")
        elif command in ("idle", "standby"):
            self._mode = MissionMode.IDLE
            self._route_queue = []
            self._cancel_current_goal()
            self._publish_stop()
            self.get_logger().info("mission: idle")
        else:
            self.get_logger().warn(f"unknown mission command: {msg.data}")

    def _on_alert(self, msg: String) -> None:
        self._last_alert_time = time.monotonic()
        if self._mode not in (MissionMode.IDLE, MissionMode.STOPPED,
                              MissionMode.ALERT_STOP):
            self._resume_mode = self._mode
        if self._mode != MissionMode.STOPPED:
            self._mode = MissionMode.ALERT_STOP
            self._cancel_current_goal()
            self._publish_stop()
        try:
            payload = json.loads(msg.data)
            confidence = float(payload.get("confidence", 0.0))
            self.get_logger().warn(
                f"ALERT — patrol holding (conf={confidence:.2f})")
        except Exception:
            self.get_logger().warn("ALERT — patrol holding")

    def _set_patrol_route(self) -> None:
        # patrol_waypoints[0]=home, [1..]=순찰점. home 제외 순환.
        if len(self._patrol_waypoints) < 2:
            self.get_logger().warn("patrol waypoint 부족 — sortie 무효")
            self._route_queue = []
            return
        target = self._select_initial_patrol_target()
        self._route_queue = [target]
        self._current_goal = None

    def _set_home_route(self) -> None:
        self._route_queue = [self._home]
        self._current_goal = None

    def _select_initial_patrol_target(self):
        # home(idx 0) 다음 가장 가까운 순찰점부터 시작
        if self._pose is None or len(self._patrol_waypoints) < 2:
            self._next_patrol_index = 2 if len(self._patrol_waypoints) > 2 else 1
            return self._patrol_waypoints[1]
        best_i = 1
        best_d = float("inf")
        for i in range(1, len(self._patrol_waypoints)):
            wx, wy = self._patrol_waypoints[i]
            d = math.hypot(wx - self._pose[0], wy - self._pose[1])
            if d < best_d:
                best_d = d
                best_i = i
        self._next_patrol_index = best_i + 1
        return self._patrol_waypoints[best_i]

    def _next_patrol_target(self):
        n = len(self._patrol_waypoints)
        if n < 2:
            return self._home
        # idx 1..n-1 순환 (home 제외)
        idx = ((self._next_patrol_index - 1) % (n - 1)) + 1
        self._next_patrol_index += 1
        return self._patrol_waypoints[idx]

    def _send_next_goal(self) -> None:
        if self._mode in (MissionMode.IDLE, MissionMode.STOPPED,
                          MissionMode.ALERT_STOP):
            return
        if self._goal_handle is not None:
            return
        if not self._nav_client.server_is_ready():
            self._mode = MissionMode.WAITING_FOR_NAV2
            self.get_logger().warn("navigate_to_pose action 미준비")
            return
        if not self._route_queue:
            if self._mode == MissionMode.HOME:
                self._mode = MissionMode.IDLE
                self._current_goal = self._home
                self._publish_stop()
                self.get_logger().info("home 도착 → IDLE")
                return
            self._route_queue.append(self._next_patrol_target())

        self._current_goal = self._route_queue.pop(0)
        goal = NavigateToPose.Goal()
        goal.pose = self._make_pose(self._current_goal)
        self.get_logger().info(
            f"goal x={self._current_goal[0]:.1f} y={self._current_goal[1]:.1f}")
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
        if self._mode in (MissionMode.ALERT_STOP, MissionMode.STOPPED,
                          MissionMode.IDLE):
            return
        if status == GoalStatus.STATUS_SUCCEEDED:
            self.get_logger().info("goal 도착")
            self._send_next_goal()
        else:
            self.get_logger().warn(f"goal 실패 status={status} — 다음 시도")
            self._send_next_goal()

    def _cancel_current_goal(self) -> None:
        if self._goal_handle is not None:
            self._goal_handle.cancel_goal_async()
            self._goal_handle = None

    def _publish_stop(self) -> None:
        self._cmd_pub.publish(Twist())

    def _tick(self) -> None:
        now = time.monotonic()
        if (self._mode == MissionMode.WAITING_FOR_NAV2
                and self._nav_client.server_is_ready()):
            self._mode = self._resume_mode
            self._send_next_goal()
        elif self._mode == MissionMode.ALERT_STOP:
            self._publish_stop()
            if now - self._last_alert_time > self._alert_hold_seconds:
                self._mode = self._resume_mode
                self.get_logger().info(
                    f"ALERT_STOP hold 종료 → {self._mode.value} 재개")
                self._send_next_goal()
        self._publish_state()

    def _publish_state(self) -> None:
        payload = {
            "mode": self._mode.value,
            "waypoint": (
                {"x": self._current_goal[0], "y": self._current_goal[1]}
                if self._current_goal else None),
            "home": {"x": self._home[0], "y": self._home[1]},
            "route": [{"x": w[0], "y": w[1]} for w in self._route_queue],
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
