"""C2 web_server 설정 — 환경변수 중심 (설계 문서 §4.2 / §4.3)."""
import os

# ROS 2 — Main PC(Isaac) 와 동일 도메인 (설계 §4.2 / D10)
ROS_DOMAIN_ID = os.environ.get("ROS_DOMAIN_ID", "130")

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
    "video_front": "/c2/front/compressed",    # sensor_msgs/CompressedImage (전방 카메라)
    "video_rear":  "/c2/rear/compressed",     # sensor_msgs/CompressedImage (후방 카메라)
    "depth":       "/c2/depth/compressed",    # sensor_msgs/CompressedImage
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
}

ROSOUT_WARN_LEVEL = 30  # WARN 이상만 중계 (설계 §9.4)


# YOLO 모델 우선순위 (P3 2026-05-20): C2_YOLO_MODEL env > models/*.pt > yolov8n.pt
_MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")


def _pick_model() -> str:
    _env = os.environ.get("C2_YOLO_MODEL", "").strip()
    if _env:
        return _env
    if os.path.isdir(_MODELS_DIR):
        for _f in sorted(os.listdir(_MODELS_DIR)):
            if _f.endswith(".pt"):
                return os.path.join(_MODELS_DIR, _f)
    return "yolov8n.pt"  # ultralytics 자동 다운로드


YOLO_MODEL = _pick_model()

# 클래스 매핑 — person + COCO 동물 + jsy 2-class 호환 (class 1=animal)
YOLO_CLASSES = {
    0: "person",
    1: "animal",
    16: "bird", 17: "cat", 18: "dog", 19: "horse", 20: "sheep",
    21: "cow", 22: "elephant", 23: "bear", 24: "zebra", 25: "giraffe",
}

# YOLO alert 정책 (DMZ Sentry M5 — alert_conf 이상 + cooldown 초과 시 /alerts 발행)
YOLO_ALERT_CONF = float(os.environ.get("C2_YOLO_ALERT_CONF", "0.55"))
YOLO_ALERT_COOLDOWN = float(os.environ.get("C2_YOLO_ALERT_COOLDOWN", "3.0"))
# P3 신규: 동물 alert 정책 (독립 cooldown)
YOLO_ANIMAL_ALERT_CONF = float(os.environ.get("C2_YOLO_ANIMAL_ALERT_CONF", "0.50"))
YOLO_ANIMAL_ALERT_COOLDOWN = float(os.environ.get("C2_YOLO_ANIMAL_ALERT_COOLDOWN", "5.0"))
