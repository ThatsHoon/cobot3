"""camera_info_publisher — 3 카메라 sensor_msgs/CameraInfo 사이드카.

Isaac OG ROS2CameraHelper 가 type="camera_info" 미지원 (Isaac 5.1) 이라 별도
rclpy 사이드카로 합성 발행. Foxglove 3D 패널이 image + CameraCalibration
pair 받으면 robot 주변에 camera frustum + image plane 자동 렌더링.

intrinsic: Isaac OG 카메라 설정 (focal_length mm, horizontalAperture mm,
width px) 으로 fx 계산. distortion = zero (pinhole).

토픽:
  /cam/rear/camera_info     (frame camera_rear,    640×360, focal 10.5mm)
  /cam/inspect/camera_info  (frame camera_inspect, 640×360, focal 18.0mm)
  /cam/overhead/camera_info (frame camera_overhead,640×640, focal 8.0mm)

QoS = RELIABLE + TRANSIENT_LOCAL (latched) — Foxglove 늦은 join 도 OK.

실행: python3 main_side/camera_info_publisher.py
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import (DurabilityPolicy, HistoryPolicy, QoSProfile,
                       ReliabilityPolicy)
from sensor_msgs.msg import CameraInfo


# (topic, frame_id, width, height, focal_mm, aperture_mm)
_CAMS = [
    ("/cam/rear/camera_info",     "camera_rear",     640, 360, 10.5, 20.955),
    ("/cam/inspect/camera_info",  "camera_inspect",  640, 360, 18.0, 20.955),
    ("/cam/overhead/camera_info", "camera_overhead", 640, 640,  8.0, 20.955),
]


def _build_info(frame_id: str, w: int, h: int, focal_mm: float,
                ap_mm: float) -> CameraInfo:
    # fx = (image_width / sensor_aperture_width) * focal_length
    fx = (w / ap_mm) * focal_mm
    fy = fx   # 정사각 픽셀 (16:9 카메라도 aperture 비율 보정으로 동일)
    cx = w / 2.0
    cy = h / 2.0
    ci = CameraInfo()
    ci.header.frame_id = frame_id
    ci.width = w
    ci.height = h
    ci.distortion_model = "plumb_bob"
    ci.d = [0.0, 0.0, 0.0, 0.0, 0.0]
    ci.k = [fx, 0.0, cx,
            0.0, fy, cy,
            0.0, 0.0, 1.0]
    ci.r = [1.0, 0.0, 0.0,
            0.0, 1.0, 0.0,
            0.0, 0.0, 1.0]
    ci.p = [fx, 0.0, cx, 0.0,
            0.0, fy, cy, 0.0,
            0.0, 0.0, 1.0, 0.0]
    return ci


class CameraInfoPublisher(Node):
    def __init__(self):
        super().__init__("camera_info_publisher")
        latched = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self._pubs = []
        for topic, frame, w, h, focal, ap in _CAMS:
            pub = self.create_publisher(CameraInfo, topic, latched)
            ci = _build_info(frame, w, h, focal, ap)
            self._pubs.append((pub, ci, topic, frame, focal))
        # 2026-05-24: 1Hz timer 제거. TRANSIENT_LOCAL durability 가 새 subscriber 매칭 시
        # last sample 을 자동 재전송 (rmw_fastrtps_cpp 보장). 1회 발행만으로 충분.
        # 안전망: 60초 주기 보호 발행 (RMW 가 TL 미지원하는 극단 케이스 대비).
        self._publish_once()
        self.create_timer(60.0, self._publish_once)
        info_list = ", ".join(
            f"{t}({f}, focal={fc}mm)" for _, _, t, f, fc in self._pubs)
        self.get_logger().info(f"camera_info latched (1회 + 60s 보호): {info_list}")

    def _publish_once(self):
        stamp = self.get_clock().now().to_msg()
        for pub, ci, *_ in self._pubs:
            ci.header.stamp = stamp
            pub.publish(ci)


def main(args=None):
    rclpy.init(args=args)
    node = CameraInfoPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
