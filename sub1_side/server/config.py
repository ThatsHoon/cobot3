"""C2 web_server 설정 — 환경변수 중심 (설계 문서 §4.2 / §4.3)."""
import os

# ROS 2 — Main PC(Isaac) 와 동일 도메인 (설계 §4.2 / D10)
ROS_DOMAIN_ID = os.environ.get("ROS_DOMAIN_ID", "129")

# 로컬 PostgreSQL (영상 외 전 데이터 저장 — 설계 §13)
DB_URL = os.environ.get("COBOT3_DB_URL", "postgresql:///cobot3")

# 변경계열 REST 인증 (설계 §4.3) — 사격/확성기/goto/mode
API_KEY = os.environ.get("ISAAC_SIM_API_KEY", "")

# CORS allowlist — env 미설정 시 LAN 전체 허용 (개발모드)
_raw_origins = os.environ.get("C2_WEB_ORIGINS", "")
WEB_ORIGINS: list[str] = _raw_origins.split(",") if _raw_origins else ["*"]

# 단일 로봇 (확장 시 r{N})
ROBOT_ID = os.environ.get("GP_ROBOT_ID", "gp0")

HTTP_HOST = os.environ.get("C2_HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(os.environ.get("C2_HTTP_PORT", "8000"))

# DB 배치 적재 주기/한도 (telemetry-supabase 패턴)
DB_FLUSH_SEC = float(os.environ.get("C2_DB_FLUSH_SEC", "1.0"))
DB_QUEUE_MAX = int(os.environ.get("C2_DB_QUEUE_MAX", "20000"))

# 토픽 규약 (설계 §12.2)
TOPICS = {
    "state":       "/robot/state",            # std_msgs/String (JSON)
    "gps":         "/robot/gps",              # sensor_msgs/NavSatFix
    "odom":        "/robot/odom",             # nav_msgs/Odometry
    "leg_joint":   "/robot/leg_joint_states", # sensor_msgs/JointState (Spot 12-DOF legs)
    "rosout":      "/rosout",                 # rcl_interfaces/Log (level>=30 필터)
    # video_front 삭제 (2026-05-20 사용자 요청) — Go2 전방 카메라 제거
    "video_rear":     "/c2/rear/compressed",     # sensor_msgs/CompressedImage (후방/real)
    "video_inspect":  "/c2/inspect/compressed",  # sensor_msgs/CompressedImage (검사 짐벌)
    "video_overhead": "/c2/overhead/compressed", # CompressedImage (TACTICAL MAP 배경)
    "video_tp_a":     "/c2/tp_a/compressed",     # TP_A 고정 감시카메라
    "video_tp_b":     "/c2/tp_b/compressed",     # TP_B 고정 감시카메라
    "video_tp_c":     "/c2/tp_c/compressed",     # TP_C 고정 감시카메라
    "video_tp_d":     "/c2/tp_d/compressed",     # TP_D 고정 감시카메라
    "depth_tp_a":     "/cam/tactical/tp_a/depth", # sensor_msgs/Image depth
    "depth_tp_b":     "/cam/tactical/tp_b/depth",
    "depth_tp_c":     "/cam/tactical/tp_c/depth",
    "depth_tp_d":     "/cam/tactical/tp_d/depth",
    "depth":         "/c2/depth/compressed",    # sensor_msgs/CompressedImage
    # 업링크 (C2 → 로봇)
    "nav_goal":  "/robot/nav/goal",         # geometry_msgs/PoseStamped
    "speaker":   "/robot/speaker/audio",    # std_msgs/String (JSON: preset/pcm-b64)
    "fire_srv":  "/robot/weapon/fire",      # std_srvs/Trigger (간이) — 설계 §10.2
    "cmd_vel":   "/robot/cmd_vel",          # geometry_msgs/Twist (RELIABLE) — C2→로봇
    # DMZ Sentry 통합 (2026-05-20)
    "mission_cmd":  "/mission_command",     # std_msgs/String (sortie/home/stop/resume/idle)
    "patrol_state": "/patrol_state",        # std_msgs/String (JSON mode/waypoint/route/pose)
    "alerts":       "/alerts",              # std_msgs/String (JSON YOLO alert 정책 통과)
    "detections":   "/detections_text",     # std_msgs/String (JSON 모든 detection)
    "intruders":    "/intruder_states",     # std_msgs/String (JSON 침입자 ground-truth)
    "landmarks":    "/scene/landmarks",     # std_msgs/String (JSON cube/cone/fence, latched)
    "inspect_cmd":  "/robot/inspect/command",  # std_msgs/String (JSON pan/tilt/zoom/look_at)
    "inspect_rgb":  "/cam/inspect/rgb",     # sensor_msgs/Image (검사 카메라 RGB)
    "cmd_nav_raw":  "/cmd_vel_nav2_raw",    # geometry_msgs/Twist (Nav2→safety filter)
    "animal_alerts": "/animal_alerts",      # std_msgs/String (JSON 동물 감지 alert, P3)
    "npc_spawn":     "/robot/npc/spawn",    # std_msgs/String (JSON forward_m/z_offset/count)
    # FALL 감지 (2026-05-21) — go2_controller IPC → fall_relay 사이드카가 발행
    "fall_alert":   "/robot/fall_alert",    # std_msgs/String (JSON edge, FALLEN/RECOVERING/RECOVERED/UPRIGHT)
    "fall_state":   "/robot/fall_state",    # std_msgs/String (JSON 2Hz 스냅샷)
    # Weather + Wind (2026-05-21)
    "weather_cmd":  "/weather/command",     # std_msgs/String (JSON) — C2→Main
    "wind_state":   "/wind/state",          # geometry_msgs/Vector3Stamped (20Hz, world)
    # Weapon (2026-05-21, HITL)
    "weapon_state": "/robot/weapon/state",  # std_msgs/String (JSON 1Hz latched)
    "weapon_fire":  "/robot/weapon/fire",   # std_srvs/Trigger
}

ROSOUT_WARN_LEVEL = 30  # WARN 이상만 중계 (설계 §9.4)


# YOLO 모델 우선순위 (P3 2026-05-20): C2_YOLO_MODEL env > models/*.pt > yolov8n.pt
_MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")


def _pick_model() -> str:
    _env = os.environ.get("C2_YOLO_MODEL", "").strip()
    if _env:
        return _env
    _dmz4 = "/home/rokey/Downloads/dmz_4class_v14.pt"
    if os.path.isfile(_dmz4):
        return _dmz4
    if os.path.isdir(_MODELS_DIR):
        for _f in sorted(os.listdir(_MODELS_DIR)):
            if _f.endswith(".pt"):
                return os.path.join(_MODELS_DIR, _f)
    return "yolov8n.pt"  # ultralytics 자동 다운로드


YOLO_MODEL = _pick_model()

# 클래스 매핑 — COCO 80 전체 (사용자 사양 #8 — 2026-05-20). bbox 표시 대상.
# alert 정책은 person(0) / animal(1, 16-25) 두 그룹만 트리거.
YOLO_CLASSES = {
    0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 4: "airplane",
    5: "bus", 6: "train", 7: "truck", 8: "boat", 9: "traffic light",
    10: "fire hydrant", 11: "stop sign", 12: "parking meter", 13: "bench",
    14: "bird", 15: "cat", 16: "dog", 17: "horse", 18: "sheep",
    19: "cow", 20: "elephant", 21: "bear", 22: "zebra", 23: "giraffe",
    24: "backpack", 25: "umbrella", 26: "handbag", 27: "tie", 28: "suitcase",
    29: "frisbee", 30: "skis", 31: "snowboard", 32: "sports ball", 33: "kite",
    34: "baseball bat", 35: "baseball glove", 36: "skateboard", 37: "surfboard",
    38: "tennis racket", 39: "bottle", 40: "wine glass", 41: "cup", 42: "fork",
    43: "knife", 44: "spoon", 45: "bowl", 46: "banana", 47: "apple",
    48: "sandwich", 49: "orange", 50: "broccoli", 51: "carrot", 52: "hot dog",
    53: "pizza", 54: "donut", 55: "cake", 56: "chair", 57: "couch",
    58: "potted plant", 59: "bed", 60: "dining table", 61: "toilet",
    62: "tv", 63: "laptop", 64: "mouse", 65: "remote", 66: "keyboard",
    67: "cell phone", 68: "microwave", 69: "oven", 70: "toaster", 71: "sink",
    72: "refrigerator", 73: "book", 74: "clock", 75: "vase", 76: "scissors",
    77: "teddy bear", 78: "hair drier", 79: "toothbrush",
}

# animal 그룹 (alert 정책용) — COCO 14-23
YOLO_ANIMAL_CLASS_IDS = {14, 15, 16, 17, 18, 19, 20, 21, 22, 23}

# YOLO 사용자 사양 #8 (2026-05-20): conf 0.7 단일 임계. bbox 표시 + alert 동일.
YOLO_ALERT_CONF = float(os.environ.get("C2_YOLO_ALERT_CONF", "0.7"))
YOLO_ALERT_COOLDOWN = float(os.environ.get("C2_YOLO_ALERT_COOLDOWN", "3.0"))
# P3 신규: 동물 alert 정책 (독립 cooldown)
YOLO_ANIMAL_ALERT_CONF = float(os.environ.get("C2_YOLO_ANIMAL_ALERT_CONF", "0.50"))
YOLO_ANIMAL_ALERT_COOLDOWN = float(os.environ.get("C2_YOLO_ANIMAL_ALERT_COOLDOWN", "5.0"))

# TP fixed-camera projection. Must match main_side/camera_publisher.py.
TACTICAL_CAMERA_HEIGHT = float(os.environ.get("GP_TACTICAL_CAMERA_HEIGHT", "8.0"))
TACTICAL_CAMERA_FOCAL = float(os.environ.get("GP_TACTICAL_CAMERA_FOCAL", "6.0"))
TACTICAL_CAMERA_APERTURE = 20.955
TACTICAL_CAMERA_FORWARDS = {
    "tp_a": (0.15, 1.0, -0.18),
    "tp_b": (-0.22, 1.0, -0.18),
    "tp_c": (0.0, 1.0, -0.28),
    "tp_d": (-0.15, 1.0, -0.18),
}
TACTICAL_CAMERA_HEIGHT_OFFSETS = {
    "tp_a": 1.0,
    "tp_b": 0.7,
    "tp_c": 0.0,
    "tp_d": 0.0,
}
TACTICAL_DEFAULT_RANGE_M = float(os.environ.get("C2_TACTICAL_DEFAULT_RANGE_M", "35.0"))
