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
}

ROSOUT_WARN_LEVEL = 30  # WARN 이상만 중계 (설계 §9.4)
YOLO_MODEL = os.environ.get("C2_YOLO_MODEL", "yolov8n.pt")
YOLO_CLASSES = {0: "person"}  # COCO 0=person (동물 등 확장 가능)
