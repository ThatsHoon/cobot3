"""telemetry_bridge_node — ROS2 정공 텔레메트리 파생 (설계 §12 / FASTDDS.md §0).

Isaac OG 가 발행하는 base Odometry(`/robot/odom`)를 받아, OG 정규노드가 없는
두 토픽을 파생·재발행한다:
  - `/robot/gps`   sensor_msgs/NavSatFix   ← odom 위치 → sim-GPS 환산(설계 §S5)
  - `/robot/state` std_msgs/String(JSON)   ← mode/gait/battery/waypoint 합성

video_degrade_node.py 와 동일한 발행측(Main PC) 시스템 ROS2 노드 패턴이다.
arm/leg JointState 와 odom 자체는 camera_publisher 의 OG 가 직접 발행하므로
여기서 다루지 않는다(중복 방지). 영상은 어떤 경로로도 다루지 않는다.

sim-GPS 기준점/환산식은 camera_publisher._sim_gps 와 **동일**해야 D-확장
HTTP 경로와 ROS2 정공 경로의 좌표가 일치한다(LAT0/LON0/ALT0 고정).

QoS: C2 web_server(ros_bridge) 가 state/gps/odom 을 RELIABLE 로 구독하고
Isaac OG OdoPub 도 RELIABLE 로 발행 → 본 노드도 RELIABLE 통일.
RMW 는 환경(RMW_IMPLEMENTATION=rmw_fastrtps_cpp).
실행: source /opt/ros/humble/setup.bash && python3 telemetry_bridge_node.py
     (런처: main_side/run_telemetry_bridge.sh)
"""
import json
import math
import os
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from nav_msgs.msg import Odometry
from sensor_msgs.msg import NavSatFix
from std_msgs.msg import String

IN_ODOM = "/robot/odom"            # Isaac OG ROS2PublishOdometry
OUT_GPS = "/robot/gps"             # → web_server (NavSatFix)
OUT_STATE = "/robot/state"         # → web_server (String JSON)

# sim 원점 기준점 — camera_publisher.py 와 반드시 동일(설계 §S5 sim-GPS)
LAT0, LON0, ALT0 = 38.30, 127.50, 200.0
TARGET_HZ = 5.0                    # 파생 발행 스로틀(odom 은 sim tick rate)
MOVE_EPS = 0.05                    # m/s — gait idle/walk 임계
BATT_FULL = 100.0
BATT_DRAIN_PER_MIN = 0.1           # 합성 배터리 감소율(%/분)
BATT_MIN = 20.0

REL_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    history=HistoryPolicy.KEEP_LAST, depth=10)


def _sim_gps(x, y, z):
    """camera_publisher._sim_gps 와 동일 환산(좌표 정합 필수)."""
    dlat = (y / 6378137.0) * (180.0 / math.pi)
    dlon = (x / (6378137.0 * math.cos(math.radians(LAT0)))) * (180.0 / math.pi)
    return LAT0 + dlat, LON0 + dlon, ALT0 + float(z)


class TelemetryBridge(Node):
    def __init__(self):
        super().__init__("telemetry_bridge_node")
        self.sub = self.create_subscription(
            Odometry, IN_ODOM, self._on_odom, REL_QOS)
        self.pub_gps = self.create_publisher(NavSatFix, OUT_GPS, REL_QOS)
        self.pub_state = self.create_publisher(String, OUT_STATE, REL_QOS)
        self._last = 0.0
        self._n_in = 0
        self._n_out = 0
        self._first_logged = False
        self._t0 = time.monotonic()
        self.create_timer(5.0, self._stats)
        L = self.get_logger()
        L.info("==== telemetry_bridge ENV 점검 ====")
        L.info(f"  ROS_DOMAIN_ID={os.environ.get('ROS_DOMAIN_ID','<UNSET>')} "
               f"RMW={os.environ.get('RMW_IMPLEMENTATION','<UNSET>')} "
               f"LOCALHOST_ONLY={os.environ.get('ROS_LOCALHOST_ONLY','<UNSET>')}")
        if os.environ.get("RMW_IMPLEMENTATION") != "rmw_fastrtps_cpp":
            L.warn("  ⚠ RMW != rmw_fastrtps_cpp → Isaac 토픽 디스커버리 실패 위험")
        L.info(f"  pipeline: {IN_ODOM} → {OUT_GPS}(NavSatFix) + "
               f"{OUT_STATE}(String) @ {TARGET_HZ}fps")
        L.info("===================================")

    def _on_odom(self, msg: Odometry):
        self._n_in += 1
        if not self._first_logged:
            self._first_logged = True
            self.get_logger().info(
                "✓ 첫 odom 수신 — Isaac OG↔telemetry_bridge 통신 OK")
        now = time.monotonic()
        if now - self._last < 1.0 / TARGET_HZ:        # 스로틀
            return
        self._last = now

        p = msg.pose.pose.position
        v = msg.twist.twist.linear
        lat, lon, alt = _sim_gps(p.x, p.y, p.z)

        g = NavSatFix()
        g.header.stamp = msg.header.stamp
        g.header.frame_id = "gps"
        g.latitude = float(lat)
        g.longitude = float(lon)
        g.altitude = float(alt)
        self.pub_gps.publish(g)

        speed = math.sqrt(v.x * v.x + v.y * v.y)
        elapsed_min = (time.monotonic() - self._t0) / 60.0
        battery = max(BATT_MIN, BATT_FULL - BATT_DRAIN_PER_MIN * elapsed_min)
        st = {
            "mode": "AUTO",
            "gait": "walk" if speed > MOVE_EPS else "idle",
            "battery": round(battery, 1),
            "waypoint": {"x": round(p.x, 3), "y": round(p.y, 3)},
            "extra": {"synthetic": True, "src": "telemetry_bridge",
                      "speed": round(speed, 3)},
        }
        s = String()
        s.data = json.dumps(st)
        self.pub_state.publish(s)
        self._n_out += 1

    def _stats(self):
        npub = self.count_publishers(IN_ODOM)
        L = self.get_logger()
        L.info(f"in={self._n_in} out={self._n_out} "
               f"| {IN_ODOM} publishers={npub} (≈{TARGET_HZ}fps 목표)")
        if self._n_in == 0:
            if npub == 0:
                L.warn(f"  ⚠ {IN_ODOM} publisher 0 → Isaac 미발행/미재생 또는 "
                       f"GP_ROS2_TELEM=0·RMW·DOMAIN 불일치. camera_publisher 확인")
            else:
                L.warn(f"  ⚠ publisher {npub} 인데 수신 0 → QoS/타입 불일치 "
                       f"(OdoPub RELIABLE ↔ 본 노드 RELIABLE 매칭 확인)")


def main():
    rclpy.init()
    node = TelemetryBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            node.destroy_node()
        except Exception:
            pass
        # kill/SIGTERM 시 컨텍스트가 이미 내려갈 수 있어 이중 shutdown 가드
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()
