"""video_degrade_node — 발행측 영상 대역 절감 (설계 D8 / §9.1 / sensor-and-comms §4).

Isaac OG 가 발행하는 RealSense rgb 를 받아 해상도↓ + JPEG 화질↓ + 5fps 스로틀 후
`/c2/video/compressed` 로 재발행한다. C2 web_server(aiortc) 가 이를 WebRTC 로 송출.
영상은 어떤 경로로도 DB 저장하지 않는다.

토픽/QoS 는 설계 §12 표 고정. RMW 는 환경(RMW_IMPLEMENTATION=rmw_cyclonedds_cpp).
실행: source /opt/ros/humble/setup.bash && python3 video_degrade_node.py
"""
import os
import time

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image, CompressedImage
import cv2

IN_RGB = "/cam/realsense/rgb"          # Isaac OG ROS2CameraHelper (rgb)
OUT_RGB = "/c2/video/compressed"       # → web_server
TARGET_FPS = 5.0
OUT_W, OUT_H = 640, 360
JPEG_Q = 50

SENSOR_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    history=HistoryPolicy.KEEP_LAST, depth=5)


class VideoDegrade(Node):
    def __init__(self):
        super().__init__("video_degrade_node")
        self.sub = self.create_subscription(
            Image, IN_RGB, self._on_rgb, SENSOR_QOS)
        self.pub = self.create_publisher(
            CompressedImage, OUT_RGB, SENSOR_QOS)
        self._last = 0.0
        self._n_in = 0
        self._n_out = 0
        self._first_logged = False
        self.create_timer(5.0, self._stats)
        L = self.get_logger()
        L.info("==== video_degrade ENV 점검 ====")
        L.info(f"  ROS_DOMAIN_ID={os.environ.get('ROS_DOMAIN_ID','<UNSET>')} "
               f"RMW={os.environ.get('RMW_IMPLEMENTATION','<UNSET>')} "
               f"LOCALHOST_ONLY={os.environ.get('ROS_LOCALHOST_ONLY','<UNSET>')}")
        if os.environ.get("RMW_IMPLEMENTATION") != "rmw_cyclonedds_cpp":
            L.warn("  ⚠ RMW != rmw_cyclonedds_cpp → Isaac 토픽 디스커버리 실패 위험")
        L.info(f"  pipeline: {IN_RGB} → {OUT_RGB} @ {TARGET_FPS}fps "
               f"{OUT_W}x{OUT_H} q{JPEG_Q}")
        L.info("================================")

    def _on_rgb(self, msg: Image):
        self._n_in += 1
        if not self._first_logged:
            self._first_logged = True
            self.get_logger().info(
                f"✓ 첫 프레임 수신: {msg.width}x{msg.height} enc={msg.encoding} "
                f"— Isaac↔degrade 통신 OK")
        now = time.monotonic()
        if now - self._last < 1.0 / TARGET_FPS:      # 5fps 스로틀
            return
        self._last = now
        # sensor_msgs/Image → ndarray (rgb8/bgr8/rgba8 대응)
        h, w = msg.height, msg.width
        buf = np.frombuffer(msg.data, dtype=np.uint8)
        enc = (msg.encoding or "rgb8").lower()
        try:
            if enc in ("rgb8", "bgr8"):
                img = buf.reshape(h, w, 3)
                if enc == "rgb8":
                    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            elif enc in ("rgba8", "bgra8"):
                img = buf.reshape(h, w, 4)
                img = cv2.cvtColor(
                    img, cv2.COLOR_RGBA2BGR if enc == "rgba8"
                    else cv2.COLOR_BGRA2BGR)
            else:
                img = buf.reshape(h, w, -1)[:, :, :3]
        except ValueError:
            self.get_logger().warn(
                f"reshape 실패 enc={enc} {w}x{h} len={buf.size}")
            return
        img = cv2.resize(img, (OUT_W, OUT_H), interpolation=cv2.INTER_AREA)
        ok, jpg = cv2.imencode(
            ".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, JPEG_Q])
        if not ok:
            return
        out = CompressedImage()
        out.header = msg.header
        out.format = "jpeg"
        out.data = jpg.tobytes()
        self.pub.publish(out)
        self._n_out += 1

    def _stats(self):
        npub = self.count_publishers(IN_RGB)
        L = self.get_logger()
        L.info(f"in={self._n_in} out={self._n_out} "
               f"| {IN_RGB} publishers={npub} (≈{TARGET_FPS}fps 목표)")
        if self._n_in == 0:
            if npub == 0:
                L.warn(f"  ⚠ {IN_RGB} publisher 0 → Isaac 미발행/미재생 또는 "
                       f"RMW·DOMAIN 불일치. camera_publisher 로그 확인")
            else:
                L.warn(f"  ⚠ publisher {npub} 인데 수신 0 → QoS/타입 불일치 "
                       f"또는 Isaac 렌더프로덕트 미생성")


def main():
    rclpy.init()
    node = VideoDegrade()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
