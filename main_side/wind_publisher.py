"""wind_publisher — Isaac Sim 외부 ROS2 사이드카. 랜덤 풍속·풍향 발생.

분포:
  방위각 θ : von Mises (μ=base_dir, κ=4)  — base_dir 는 매 60s 천천히 회전
  풍속 |v| : Weibull (k=2, λ=mode 평균)
  smoothing: AR(1) α=0.85
  gust:    Bernoulli(gust_prob) trigger → 1.5× spike 1초 유지 후 decay

ROS2:
  publish: /wind/state (geometry_msgs/Vector3Stamped, world frame, m/s, 20Hz)
  subscribe: /weather/command (std_msgs/String JSON)
    {wind_mode: calm|breeze|windy|gale|storm,
     wind_random_dir: bool,
     wind_dir_deg: float (optional, 명시 방향),
     wind_speed_m_s: float (optional, mode 무시하고 고정 속도)}

물리적 상한: 18 m/s (walk-these-ways max_push_vel_xy=1.0 등가, 보퍼트 8).
"""
import json
import math
import time

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy
from geometry_msgs.msg import Vector3Stamped
from std_msgs.msg import String


WIND_PRESETS = {
    "calm":   {"speed_range": (0.0, 1.0),  "lambda": 0.5,  "gust_prob": 0.00},
    "breeze": {"speed_range": (1.0, 4.0),  "lambda": 2.0,  "gust_prob": 0.05},
    "windy":  {"speed_range": (4.0, 9.0),  "lambda": 5.0,  "gust_prob": 0.15},
    "gale":   {"speed_range": (9.0, 14.0), "lambda": 10.0, "gust_prob": 0.30},
    "storm":  {"speed_range": (14.0, 18.0),"lambda": 15.0, "gust_prob": 0.45},
}
WIND_SPEED_MAX = 18.0
PUBLISH_HZ = 20.0
BASE_DIR_DRIFT_HZ = 1.0 / 60.0   # base direction 회전 매우 느림


class WindPublisher(Node):
    def __init__(self):
        super().__init__("wind_publisher")
        qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            history=QoSHistoryPolicy.KEEP_LAST, depth=10)
        self._pub = self.create_publisher(Vector3Stamped, "/wind/state", qos)
        self.create_subscription(String, "/weather/command",
                                 self._on_cmd, qos)

        # 상태
        self._rng = np.random.default_rng()
        self._mode = "calm"
        self._random_dir = True
        self._fixed_dir = None    # rad or None
        self._fixed_speed = None  # m/s or None
        self._base_dir = self._rng.uniform(0, 2 * math.pi)
        # AR(1) state
        self._cur_v = np.zeros(3, dtype=float)
        self._gust_until = 0.0
        self._gust_scale = 1.0

        self.create_timer(1.0 / PUBLISH_HZ, self._tick)
        self.get_logger().info(
            "wind_publisher 시작 — /wind/state 20Hz, mode=calm")

    # ---- 명령 수신 ----
    def _on_cmd(self, msg: String) -> None:
        try:
            d = json.loads(msg.data)
        except Exception as e:
            self.get_logger().warning(f"weather cmd parse err: {e!r}")
            return
        if "wind_mode" in d:
            wm = str(d["wind_mode"]).lower()
            if wm in WIND_PRESETS:
                self._mode = wm
                self.get_logger().info(f"wind_mode → {wm}")
        if "wind_random_dir" in d:
            self._random_dir = bool(d["wind_random_dir"])
        if "wind_dir_deg" in d and d["wind_dir_deg"] is not None:
            self._fixed_dir = math.radians(float(d["wind_dir_deg"]))
        else:
            self._fixed_dir = None
        if "wind_speed_m_s" in d and d["wind_speed_m_s"] is not None:
            self._fixed_speed = max(0.0,
                min(WIND_SPEED_MAX, float(d["wind_speed_m_s"])))
        else:
            self._fixed_speed = None

    # ---- 매 tick ----
    def _tick(self) -> None:
        dt = 1.0 / PUBLISH_HZ
        preset = WIND_PRESETS[self._mode]

        # base direction 천천히 회전 (long-term variability)
        self._base_dir = (self._base_dir
                          + 2 * math.pi * BASE_DIR_DRIFT_HZ * dt
                          * self._rng.standard_normal() * 0.5) % (2 * math.pi)

        # 방위각: random vs fixed
        if self._fixed_dir is not None:
            theta = self._fixed_dir
        elif self._random_dir:
            # von Mises around base_dir
            theta = float(self._rng.vonmises(self._base_dir, 4.0))
        else:
            theta = self._base_dir

        # 속도: fixed vs Weibull
        if self._fixed_speed is not None:
            speed_sample = self._fixed_speed
        else:
            speed_sample = float(self._rng.weibull(2.0) * preset["lambda"])
            lo, hi = preset["speed_range"]
            speed_sample = float(np.clip(speed_sample, lo, hi))

        # gust
        now = time.time()
        if now > self._gust_until:
            if self._rng.random() < preset["gust_prob"] * dt:   # per-tick prob
                self._gust_until = now + 1.0
                self._gust_scale = 1.5
            else:
                self._gust_scale = 1.0
        speed_target = speed_sample * self._gust_scale
        speed_target = min(speed_target, WIND_SPEED_MAX)

        target = np.array([speed_target * math.cos(theta),
                           speed_target * math.sin(theta),
                           0.0])

        # AR(1) smoothing
        alpha = 0.85
        self._cur_v = alpha * self._cur_v + (1 - alpha) * target

        msg = Vector3Stamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "world"
        msg.vector.x = float(self._cur_v[0])
        msg.vector.y = float(self._cur_v[1])
        msg.vector.z = float(self._cur_v[2])
        self._pub.publish(msg)

        # IPC: camera_publisher 가 mtime poll 로 읽음 (in-process subscribe
        # 가 어렵기 때문 — Isaac standalone 의 rclpy 와 충돌 가능)
        try:
            with open("/tmp/cobot3_wind_state.json.tmp", "w") as f:
                json.dump({"vx": msg.vector.x, "vy": msg.vector.y,
                           "vz": msg.vector.z, "ts": now,
                           "mode": self._mode}, f)
            import os
            os.replace("/tmp/cobot3_wind_state.json.tmp",
                       "/tmp/cobot3_wind_state.json")
        except Exception:
            pass


def main():
    rclpy.init()
    node = WindPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
