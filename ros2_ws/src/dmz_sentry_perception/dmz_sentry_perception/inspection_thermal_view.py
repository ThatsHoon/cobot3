import time

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image


class InspectionThermalView(Node):
    def __init__(self) -> None:
        super().__init__("inspection_thermal_view")

        self.declare_parameter("image_topic", "/inspection_camera/image_raw")
        self.declare_parameter("thermal_topic", "/inspection_camera/thermal/image_raw")
        self.declare_parameter("model", "yolov8n.pt")
        self.declare_parameter("confidence", 0.25)
        self.declare_parameter("image_size", 320)
        self.declare_parameter("every_n", 2)
        self.declare_parameter("device", "")
        self.declare_parameter("detection_hold_frames", 8)
        self.declare_parameter("person_alpha", 0.92)
        self.declare_parameter("draw_boxes", False)

        self._image_topic = self.get_parameter("image_topic").get_parameter_value().string_value
        self._thermal_topic = self.get_parameter("thermal_topic").get_parameter_value().string_value
        self._model_name = self.get_parameter("model").get_parameter_value().string_value
        self._confidence = float(self.get_parameter("confidence").value)
        self._image_size = int(self.get_parameter("image_size").value)
        self._every_n = max(1, int(self.get_parameter("every_n").value))
        self._device = self.get_parameter("device").get_parameter_value().string_value.strip()
        self._detection_hold_frames = max(0, int(self.get_parameter("detection_hold_frames").value))
        self._person_alpha = float(np.clip(float(self.get_parameter("person_alpha").value), 0.0, 1.0))
        self._draw_boxes = bool(self.get_parameter("draw_boxes").value)

        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError(
                "ultralytics is not installed. Install it with: "
                "python3 -m pip install --user ultralytics"
            ) from exc

        self._model = YOLO(self._model_name)
        self._frame_count = 0
        self._last_detections = []
        self._last_detection_frame = -10_000
        self._last_log_time = 0.0

        self._thermal_pub = self.create_publisher(Image, self._thermal_topic, 2)
        self._image_sub = self.create_subscription(
            Image,
            self._image_topic,
            self._on_image,
            qos_profile_sensor_data,
        )

        self.get_logger().info(
            "Inspection thermal view ready: "
            f"image={self._image_topic}, thermal={self._thermal_topic}, "
            f"model={self._model_name}, every_n={self._every_n}"
        )

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

    def _detect_people(self, frame) -> list[dict]:
        predict_kwargs = {
            "source": frame,
            "conf": self._confidence,
            "imgsz": self._image_size,
            "classes": [0],
            "verbose": False,
        }
        if self._device:
            predict_kwargs["device"] = self._device

        results = self._model.predict(**predict_kwargs)
        result = results[0]
        detections = []
        if result.boxes is None:
            return detections

        for box in result.boxes:
            xyxy = box.xyxy[0].detach().cpu().numpy().astype(float).tolist()
            confidence = float(box.conf[0].detach().cpu().item())
            detections.append({"xyxy": xyxy, "confidence": confidence})
        return detections

    def _make_thermal_background(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        cool = cv2.applyColorMap(gray, cv2.COLORMAP_OCEAN)
        return np.clip(cool.astype(np.float32) * 0.42, 0, 255).astype(np.uint8)

    def _apply_person_heat(self, thermal, frame, detection: dict) -> None:
        height, width = thermal.shape[:2]
        x1, y1, x2, y2 = detection["xyxy"]
        x1 = int(np.clip(np.floor(x1), 0, width - 1))
        y1 = int(np.clip(np.floor(y1), 0, height - 1))
        x2 = int(np.clip(np.ceil(x2), x1 + 1, width))
        y2 = int(np.clip(np.ceil(y2), y1 + 1, height))
        box_w = x2 - x1
        box_h = y2 - y1
        if box_w < 3 or box_h < 3:
            return

        yy, xx = np.mgrid[0:box_h, 0:box_w].astype(np.float32)
        nx = (xx + 0.5) / float(box_w)
        ny = (yy + 0.5) / float(box_h)
        body = 1.0 - ((nx - 0.50) / 0.46) ** 2 - ((ny - 0.54) / 0.58) ** 2
        head = 1.0 - ((nx - 0.50) / 0.27) ** 2 - ((ny - 0.17) / 0.18) ** 2
        mask = np.maximum(body, head * 0.95)
        mask = np.clip(mask, 0.0, 1.0)
        mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=max(1.0, box_w * 0.025))

        confidence_boost = float(np.clip(detection.get("confidence", 0.0), 0.0, 1.0))
        heat_gray = np.clip(80.0 + 175.0 * mask + 28.0 * confidence_boost, 0.0, 255.0).astype(np.uint8)
        heat = cv2.applyColorMap(heat_gray, cv2.COLORMAP_INFERNO)

        alpha = (self._person_alpha * np.clip(mask, 0.0, 1.0) ** 0.55)[..., None]
        roi = thermal[y1:y2, x1:x2].astype(np.float32)
        blended = roi * (1.0 - alpha) + heat.astype(np.float32) * alpha
        thermal[y1:y2, x1:x2] = np.clip(blended, 0, 255).astype(np.uint8)

        if self._draw_boxes:
            cv2.rectangle(thermal, (x1, y1), (x2, y2), (0, 210, 255), 2)

    def _on_image(self, msg: Image) -> None:
        self._frame_count += 1
        try:
            frame = self._to_bgr(msg)
        except ValueError as exc:
            self.get_logger().warn(str(exc))
            return

        if self._frame_count % self._every_n == 0:
            self._last_detections = self._detect_people(frame)
            self._last_detection_frame = self._frame_count

        if self._frame_count - self._last_detection_frame > self._detection_hold_frames:
            detections = []
        else:
            detections = self._last_detections

        thermal = self._make_thermal_background(frame)
        for detection in detections:
            self._apply_person_heat(thermal, frame, detection)

        self._thermal_pub.publish(self._to_image_msg(thermal, msg.header))

        now = time.monotonic()
        if detections and now - self._last_log_time > 1.0:
            best = max(detections, key=lambda item: item["confidence"])
            self.get_logger().info(
                f"thermal inspection highlight: count={len(detections)}, best_conf={best['confidence']:.2f}"
            )
            self._last_log_time = now


def main(args=None) -> None:
    rclpy.init(args=args)
    node = InspectionThermalView()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
