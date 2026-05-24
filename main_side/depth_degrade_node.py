"""depth_degrade_node — 발행측 depth 대역 절감.

Isaac OG 가 발행하는 32FC1(또는 16UC1) depth 를 320×180 으로 downsample 후
PNG 무손실 압축(16UC1, mm 단위) 으로 재발행한다.

WHY: tactical TP 카메라 4개의 depth 가 각 920KB × 1~5.6Hz 로 LAN 9MB/s 송신.
C2 의 YOLO 3D projection 은 depth 의 정확도가 아니라 bbox 중앙 픽셀의 거리값만
필요 → 320×180 + PNG 압축으로 평균 ~50KB/msg (95% 감소).

토픽 매핑:
  /cam/tactical/tp_a/depth (raw 32FC1, 640×360, 920KB)  →
  /c2/tp_a/depth_compressed (PNG 16UC1, 320×180, ~50KB)

실행: env DEPTH_IN=/cam/tactical/tp_a/depth DEPTH_OUT=/c2/tp_a/depth_compressed \
      python3 depth_degrade_node.py
"""
import os
import time

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image, CompressedImage
import cv2

IN_DEPTH  = os.environ.get("DEPTH_IN",  "").strip()
OUT_DEPTH = os.environ.get("DEPTH_OUT", "").strip()
TARGET_FPS = float(os.environ.get("DEPTH_FPS", "2.0"))
OUT_W = int(os.environ.get("DEPTH_W", "320"))
OUT_H = int(os.environ.get("DEPTH_H", "180"))

if not IN_DEPTH or not OUT_DEPTH:
    raise SystemExit("[depth_degrade] DEPTH_IN, DEPTH_OUT env 필수 "
                     "(run_degrade.sh 참조)")

SENSOR_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    history=HistoryPolicy.KEEP_LAST, depth=5)


class DepthDegrade(Node):
    def __init__(self):
        super().__init__("depth_degrade_node")
        self.sub = self.create_subscription(
            Image, IN_DEPTH, self._on_depth, SENSOR_QOS)
        self.pub = self.create_publisher(
            CompressedImage, OUT_DEPTH, SENSOR_QOS)
        self._last = 0.0
        self._n_in = 0
        self._n_out = 0
        self._bytes_out = 0
        self._first_logged = False
        self.create_timer(5.0, self._stats)
        L = self.get_logger()
        L.info("==== depth_degrade ENV 점검 ====")
        L.info(f"  ROS_DOMAIN_ID={os.environ.get('ROS_DOMAIN_ID','<UNSET>')} "
               f"RMW={os.environ.get('RMW_IMPLEMENTATION','<UNSET>')}")
        L.info(f"  pipeline: {IN_DEPTH} → {OUT_DEPTH} @ {TARGET_FPS}fps "
               f"{OUT_W}x{OUT_H} PNG(16UC1 mm)")
        L.info("================================")

    def _on_depth(self, msg: Image):
        self._n_in += 1
        now = time.monotonic()
        if now - self._last < 1.0 / TARGET_FPS:
            return
        self._last = now

        h, w = msg.height, msg.width
        enc = (msg.encoding or "").lower()
        raw = bytes(msg.data)
        try:
            if enc == "32fc1":
                arr_m = np.frombuffer(raw, dtype=np.float32).reshape(h, w)
            elif enc == "16uc1":
                arr_m = (np.frombuffer(raw, dtype=np.uint16)
                         .reshape(h, w).astype(np.float32) / 1000.0)
            else:
                self.get_logger().warn(
                    f"unsupported depth encoding: {enc!r} (need 32fc1|16uc1)")
                return
        except ValueError:
            self.get_logger().warn(
                f"reshape 실패 enc={enc} {w}x{h} len={len(raw)}")
            return

        # 유효 범위 클램프 + 320×180 downsample (linear: depth 평균값 보존)
        arr_m = np.where(np.isfinite(arr_m), arr_m, 0.0)
        arr_m = np.clip(arr_m, 0.0, 60.0)   # 60m 이상 cutoff
        small = cv2.resize(arr_m, (OUT_W, OUT_H), interpolation=cv2.INTER_AREA)
        # mm 단위 16비트로 인코딩 (60m → 60000mm, uint16 max 65535)
        small_mm = (small * 1000.0).astype(np.uint16)
        ok, png = cv2.imencode(".png", small_mm,
                               [cv2.IMWRITE_PNG_COMPRESSION, 3])
        if not ok:
            return

        out = CompressedImage()
        out.header = msg.header
        out.format = "16UC1; png compressed"   # rviz/foxglove 가 인식하는 포맷 힌트
        out.data = png.tobytes()
        self.pub.publish(out)
        self._n_out += 1
        self._bytes_out += len(png)

        if not self._first_logged:
            self._first_logged = True
            self.get_logger().info(
                f"✓ 첫 depth: in {w}x{h} {enc} ({len(raw)//1024}KB) "
                f"→ out {OUT_W}x{OUT_H} PNG ({len(png)//1024}KB) "
                f"= {100*len(png)/len(raw):.1f}%")

    def _stats(self):
        L = self.get_logger()
        avg_kb = (self._bytes_out / max(1, self._n_out)) / 1024.0
        L.info(f"in={self._n_in} out={self._n_out} avg={avg_kb:.1f}KB/msg "
               f"| {IN_DEPTH}")


def main():
    rclpy.init()
    node = DepthDegrade()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            node.destroy_node()
        except Exception:
            pass
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()
