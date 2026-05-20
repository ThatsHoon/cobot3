import json
import math
import time

import cv2
import numpy as np
import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from std_msgs.msg import String


class YoloPersonDetector(Node):
    def __init__(self) -> None:
        super().__init__("yolo_person_detector")

        self.declare_parameter("image_topic", "/camera/image_raw")
        self.declare_parameter("annotated_topic", "/camera/annotated")
        self.declare_parameter("detections_topic", "/detections_text")
        self.declare_parameter("alerts_topic", "/alerts")
        self.declare_parameter("model", "yolov8n.pt")
        self.declare_parameter("confidence", 0.35)
        self.declare_parameter("image_size", 320)
        self.declare_parameter("every_n", 2)
        self.declare_parameter("device", "")
        self.declare_parameter("publish_annotated", False)
        self.declare_parameter("annotated_scale", 0.5)
        self.declare_parameter("alert_confidence", 0.20)
        self.declare_parameter("alert_cooldown", 1.0)
        self.declare_parameter("alert_label", "person")
        self.declare_parameter("alert_event", "person_detected_near_fence")
        self.declare_parameter("detect_classes", [-1])

        self._image_topic = self.get_parameter("image_topic").get_parameter_value().string_value
        self._annotated_topic = self.get_parameter("annotated_topic").get_parameter_value().string_value
        self._detections_topic = self.get_parameter("detections_topic").get_parameter_value().string_value
        self._alerts_topic = self.get_parameter("alerts_topic").get_parameter_value().string_value
        self._model_name = self.get_parameter("model").get_parameter_value().string_value
        self._confidence = float(self.get_parameter("confidence").value)
        self._image_size = int(self.get_parameter("image_size").value)
        self._every_n = max(1, int(self.get_parameter("every_n").value))
        self._device = self.get_parameter("device").get_parameter_value().string_value.strip()
        self._publish_annotated = bool(self.get_parameter("publish_annotated").value)
        self._annotated_scale = float(self.get_parameter("annotated_scale").value)
        self._alert_confidence = float(self.get_parameter("alert_confidence").value)
        self._alert_cooldown = max(0.0, float(self.get_parameter("alert_cooldown").value))
        self._alert_label = self.get_parameter("alert_label").get_parameter_value().string_value
        self._alert_event = self.get_parameter("alert_event").get_parameter_value().string_value
        raw_classes = list(self.get_parameter("detect_classes").get_parameter_value().integer_array_value)
        self._detect_classes = None if (not raw_classes or raw_classes == [-1]) else raw_classes

        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError(
                "ultralytics is not installed. Install it with: "
                "python3 -m pip install --user ultralytics"
            ) from exc

        self._model = YOLO(self._model_name)
        self._frame_count = 0
        self._last_log_time = 0.0
        self._last_alert_time = 0.0

        self._robot_x = 0.0
        self._robot_y = 0.0
        self._robot_yaw = 0.0
        self._odom_sub = self.create_subscription(
            Odometry, "/odom", self._on_odom, qos_profile_sensor_data
        )

        self._annotated_pub = (
            self.create_publisher(Image, self._annotated_topic, 2) if self._publish_annotated else None
        )
        self._detections_pub = self.create_publisher(String, self._detections_topic, 10)
        self._alerts_pub = self.create_publisher(String, self._alerts_topic, 10)
        self._image_sub = self.create_subscription(
            Image,
            self._image_topic,
            self._on_image,
            qos_profile_sensor_data,
        )

        self.get_logger().info(
            "YOLO person detector ready: "
            f"image={self._image_topic}, detections={self._detections_topic}, "
            f"alerts={self._alerts_topic}, annotated={self._publish_annotated}, "
            f"annotated_scale={self._annotated_scale:.2f}, model={self._model_name}"
        )

    def _on_odom(self, msg: Odometry) -> None:
        pose = msg.pose.pose
        self._robot_x = pose.position.x
        self._robot_y = pose.position.y
        q = pose.orientation
        siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
        cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        self._robot_yaw = math.atan2(siny_cosp, cosy_cosp)

    def _to_bgr(self, msg: Image):
        channels_by_encoding = {
            "rgb8": 3,
            "bgr8": 3,
            "rgba8": 4,
            "bgra8": 4,
            "mono8": 1,
        }
        channels = channels_by_encoding.get(msg.encoding)
        if channels is None:
            raise ValueError(f"Unsupported image encoding: {msg.encoding}")

        image = np.frombuffer(msg.data, dtype=np.uint8)
        if channels == 1:
            image = image.reshape((msg.height, msg.width))
        else:
            image = image.reshape((msg.height, msg.width, channels))

        if msg.encoding in ("rgb8", "rgba8"):
            code = cv2.COLOR_RGB2BGR if msg.encoding == "rgb8" else cv2.COLOR_RGBA2BGR
            return cv2.cvtColor(image, code)
        if msg.encoding == "bgra8":
            return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
        if msg.encoding == "mono8":
            return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        return image

    def _to_image_msg(self, image, header) -> Image:
        msg = Image()
        msg.header = header
        msg.height = int(image.shape[0])
        msg.width = int(image.shape[1])
        msg.encoding = "bgr8"
        msg.is_bigendian = False
        msg.step = int(image.shape[1] * 3)
        msg.data = np.ascontiguousarray(image).tobytes()
        return msg

    def _resize_annotated(self, image):
        scale = self._annotated_scale
        if scale >= 0.999:
            return image
        if scale <= 0.0:
            self.get_logger().warn("annotated_scale must be > 0.0; using original annotated image")
            return image

        width = max(1, int(round(image.shape[1] * scale)))
        height = max(1, int(round(image.shape[0] * scale)))
        return cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)

    def _on_image(self, msg: Image) -> None:
        self._frame_count += 1
        if self._frame_count % self._every_n != 0:
            return

        try:
            frame = self._to_bgr(msg)
        except ValueError as exc:
            self.get_logger().warn(str(exc))
            return
        predict_kwargs = {
            "source": frame,
            "conf": self._confidence,
            "imgsz": self._image_size,
            "verbose": False,
        }
        if self._detect_classes is not None:
            predict_kwargs["classes"] = self._detect_classes
        if self._device:
            predict_kwargs["device"] = self._device

        results = self._model.predict(**predict_kwargs)
        result = results[0]

        detections = []
        if result.boxes is not None:
            for box in result.boxes:
                xyxy = box.xyxy[0].detach().cpu().numpy().tolist()
                confidence = float(box.conf[0].detach().cpu().item())
                class_id = int(box.cls[0].detach().cpu().item())
                detections.append(
                    {
                        "class_id": class_id,
                        "label": result.names.get(class_id, str(class_id)),
                        "confidence": confidence,
                        "xyxy": [float(value) for value in xyxy],
                    }
                )

        if self._annotated_pub is not None:
            annotated = result.plot()
            annotated = self._resize_annotated(annotated)
            annotated_msg = self._to_image_msg(annotated, msg.header)
            self._annotated_pub.publish(annotated_msg)

        text_msg = String()
        text_msg.data = json.dumps(
            {
                "stamp": {"sec": msg.header.stamp.sec, "nanosec": msg.header.stamp.nanosec},
                "frame_id": msg.header.frame_id,
                "detections": detections,
            }
        )
        self._detections_pub.publish(text_msg)

        now = time.monotonic()
        alert_candidates = [item for item in detections if item["confidence"] >= self._alert_confidence]
        if alert_candidates and now - self._last_alert_time > self._alert_cooldown:
            best = max(alert_candidates, key=lambda item: item["confidence"])
            alert_msg = String()
            alert_msg.data = json.dumps(
                {
                    "level": "ALERT",
                    "event": self._alert_event,
                    "label": self._alert_label,
                    "frame_id": msg.header.frame_id,
                    "confidence": best["confidence"],
                    "bbox_xyxy": best["xyxy"],
                    "image_width": msg.width,
                    "image_height": msg.height,
                    "count": len(alert_candidates),
                    "action": "report_and_track",
                    "robot_x": self._robot_x,
                    "robot_y": self._robot_y,
                    "robot_yaw": self._robot_yaw,
                }
            )
            self._alerts_pub.publish(alert_msg)
            self.get_logger().warn(
                f"[ALERT] {self._alert_label} detected: "
                f"count={len(alert_candidates)}, best_conf={best['confidence']:.2f}"
            )
            self._last_alert_time = now

        if detections and now - self._last_log_time > 1.0:
            best = max(detections, key=lambda item: item["confidence"])
            self.get_logger().info(
                f"{self._alert_label} detected: count={len(detections)}, best_conf={best['confidence']:.2f}"
            )
            self._last_log_time = now


def main(args=None) -> None:
    rclpy.init(args=args)
    node = YoloPersonDetector()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
