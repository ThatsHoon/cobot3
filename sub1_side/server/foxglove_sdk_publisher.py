"""Foxglove Python SDK 사이드카 — ROS String JSON 토픽을 native schema 변환·발행.

rclpy + foxglove SDK 가 같은 process 에서 병행. ROS topic 구독 → SDK channel
publish. Lichtblick 가 ws://host:8767 연결해 native 시각화 패널 즉시 사용.

채널:
  /sdk/intruder_markers     SceneUpdate (Sphere per intruder, color by level)
  /sdk/landmark_markers     SceneUpdate (Cube home/goal + Cylinder arrive_box + Text)
  /sdk/patrol_goal_pose     PoseInFrame
  /sdk/inspect_annotations  ImageAnnotations (YOLO bbox vector overlay)
  /sdk/alert_log            Log

실행: python3 sub1_side/server/foxglove_sdk_publisher.py
"""
import json

import foxglove
from foxglove.channels import (
    SceneUpdateChannel, PoseInFrameChannel, ImageAnnotationsChannel,
    LogChannel,
)
from foxglove.messages import (
    SceneUpdate, SceneEntity, SpherePrimitive, CubePrimitive, CylinderPrimitive,
    TextPrimitive, PoseInFrame, ImageAnnotations, PointsAnnotation, Point2,
    Color, Vector3, Pose, Quaternion, Log, LogLevel,
)

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class FoxgloveSdkBridge(Node):
    def __init__(self):
        super().__init__("foxglove_sdk_publisher")
        self._server = foxglove.start_server(host="0.0.0.0", port=8767)
        self._intr = SceneUpdateChannel(topic="/sdk/intruder_markers")
        self._lm   = SceneUpdateChannel(topic="/sdk/landmark_markers")
        self._goal = PoseInFrameChannel(topic="/sdk/patrol_goal_pose")
        self._anno = ImageAnnotationsChannel(topic="/sdk/inspect_annotations")
        self._log  = LogChannel(topic="/sdk/alert_log")

        self.create_subscription(String, "/intruder_states", self._on_intruders, 10)
        self.create_subscription(String, "/scene/landmarks", self._on_landmarks, 10)
        self.create_subscription(String, "/patrol_state",    self._on_patrol, 10)
        self.create_subscription(String, "/detections_text", self._on_dets, 10)
        self.create_subscription(String, "/alerts",          self._on_alert, 10)

        self.get_logger().info(
            "Foxglove SDK :8767 ready — channels: intruder_markers, "
            "landmark_markers, patrol_goal_pose, inspect_annotations, alert_log")

    def _on_intruders(self, msg):
        try:
            d = json.loads(msg.data)
        except Exception:
            return
        items = d if isinstance(d, list) else d.get("items", [])
        ents = []
        for i, it in enumerate(items):
            level = str(it.get("level", "")).upper()
            color = (Color(r=1.0, g=0.2, b=0.2, a=0.85) if level == "ALERT"
                     else Color(r=1.0, g=0.85, b=0.3, a=0.7))
            ents.append(SceneEntity(
                id=f"intruder_{it.get('id', i)}",
                frame_id="world",
                spheres=[SpherePrimitive(
                    pose=Pose(
                        position=Vector3(x=float(it["x"]), y=float(it["y"]),
                                         z=float(it.get("z", 0.5))),
                        orientation=Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
                    ),
                    size=Vector3(x=1.2, y=1.2, z=1.2),
                    color=color,
                )],
            ))
        if ents:
            self._intr.log(SceneUpdate(entities=ents))

    def _on_landmarks(self, msg):
        try:
            lm = json.loads(msg.data)
        except Exception:
            return
        ents = []
        if isinstance(lm.get("home"), dict) and "x" in lm["home"]:
            h = lm["home"]
            hz = float(h.get("z", 0))
            ents.append(SceneEntity(
                id="home",
                frame_id="world",
                cubes=[CubePrimitive(
                    pose=Pose(position=Vector3(x=float(h["x"]), y=float(h["y"]),
                                               z=hz + 0.5),
                              orientation=Quaternion(x=0, y=0, z=0, w=1)),
                    size=Vector3(x=2.0, y=2.0, z=1.0),
                    color=Color(r=0.2, g=1.0, b=0.4, a=0.85),
                )],
                texts=[TextPrimitive(
                    pose=Pose(position=Vector3(x=float(h["x"]), y=float(h["y"]),
                                               z=hz + 2.5),
                              orientation=Quaternion(x=0, y=0, z=0, w=1)),
                    billboard=True, font_size=0.8, scale_invariant=False,
                    color=Color(r=0.2, g=1.0, b=0.4, a=1.0),
                    text="HOME",
                )],
            ))
        if isinstance(lm.get("goal"), dict) and "x" in lm["goal"]:
            g = lm["goal"]
            gz = float(g.get("z", 0))
            ab = float(lm.get("arrive_box", 0))
            cylinders = []
            if ab > 0:
                cylinders.append(CylinderPrimitive(
                    pose=Pose(position=Vector3(x=float(g["x"]), y=float(g["y"]),
                                               z=gz),
                              orientation=Quaternion(x=0, y=0, z=0, w=1)),
                    size=Vector3(x=ab * 2, y=ab * 2, z=0.1),
                    bottom_scale=1.0, top_scale=1.0,
                    color=Color(r=1.0, g=0.3, b=0.3, a=0.25),
                ))
            ents.append(SceneEntity(
                id="goal",
                frame_id="world",
                cubes=[CubePrimitive(
                    pose=Pose(position=Vector3(x=float(g["x"]), y=float(g["y"]),
                                               z=gz + 0.5),
                              orientation=Quaternion(x=0, y=0, z=0, w=1)),
                    size=Vector3(x=2.0, y=2.0, z=1.0),
                    color=Color(r=1.0, g=0.3, b=0.3, a=0.85),
                )],
                cylinders=cylinders,
                texts=[TextPrimitive(
                    pose=Pose(position=Vector3(x=float(g["x"]), y=float(g["y"]),
                                               z=gz + 2.5),
                              orientation=Quaternion(x=0, y=0, z=0, w=1)),
                    billboard=True, font_size=0.8, scale_invariant=False,
                    color=Color(r=1.0, g=0.4, b=0.4, a=1.0),
                    text="GOAL",
                )],
            ))
        if ents:
            self._lm.log(SceneUpdate(entities=ents))

    def _on_patrol(self, msg):
        try:
            d = json.loads(msg.data)
        except Exception:
            return
        wp = d.get("waypoint") or d.get("goal")
        if not (isinstance(wp, dict) and "x" in wp):
            return
        self._goal.log(PoseInFrame(
            frame_id="world",
            pose=Pose(
                position=Vector3(x=float(wp["x"]), y=float(wp["y"]), z=0.0),
                orientation=Quaternion(x=0, y=0, z=0, w=1),
            ),
        ))

    def _on_dets(self, msg):
        try:
            d = json.loads(msg.data)
        except Exception:
            return
        # ImageAnnotations.points: each PointsAnnotation has type + points list
        # type=2 LINE_STRIP (bbox outline)
        anns = []
        for det in d.get("detections", []):
            try:
                x, y, w, h = det["bbox"]
            except Exception:
                continue
            pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]
            anns.append(PointsAnnotation(
                type=2,
                points=[Point2(x=float(px), y=float(py)) for px, py in pts],
                outline_color=Color(r=0.0, g=1.0, b=0.5, a=0.95),
                outline_colors=[],
                fill_color=Color(r=0.0, g=0.0, b=0.0, a=0.0),
                thickness=2.0,
            ))
        self._anno.log(ImageAnnotations(points=anns))

    def _on_alert(self, msg):
        try:
            d = json.loads(msg.data)
        except Exception:
            return
        self._log.log(Log(
            level=LogLevel.WARNING,
            name="alert",
            message=f"{d.get('event', '?')} conf={d.get('confidence', 0):.2f}",
        ))


def main():
    rclpy.init()
    node = FoxgloveSdkBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
