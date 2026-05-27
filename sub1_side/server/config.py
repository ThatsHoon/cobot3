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
    # video_front 삭제 (2026-05-20 사용자 요청) — Go2 전방 카메라 제거
    "video_rear":     "/c2/rear/compressed",     # sensor_msgs/CompressedImage (후방/real)
    "video_inspect":  "/c2/inspect/compressed",  # sensor_msgs/CompressedImage (검사 짐벌)
    "video_overhead": "/c2/overhead/compressed", # CompressedImage (TACTICAL MAP 배경)
    "video_tp_a":    "/c2/tp_a/compressed",     # TP_A 고정 감시카메라
    "video_tp_b":    "/c2/tp_b/compressed",     # TP_B 고정 감시카메라
    "video_tp_c":    "/c2/tp_c/compressed",     # TP_C 고정 감시카메라
    "video_tp_d":    "/c2/tp_d/compressed",     # TP_D 고정 감시카메라
    # Depth: 2026-05-24 PNG 압축본 사용 (LAN 9MB/s → 0.4MB/s 절감, depth_degrade_node 가 재발행)
    "depth_tp_a":    "/c2/tp_a/depth_compressed", # CompressedImage 16UC1 PNG 320×180
    "depth_tp_b":    "/c2/tp_b/depth_compressed",
    "depth_tp_c":    "/c2/tp_c/depth_compressed",
    "depth_tp_d":    "/c2/tp_d/depth_compressed",
    "depth":         "/c2/depth/compressed",    # sensor_msgs/CompressedImage
    # 업링크 (C2 → 로봇)
    "nav_goal":  "/robot/nav/goal",         # geometry_msgs/PoseStamped
    "speaker":   "/robot/speaker/audio",    # std_msgs/String (JSON: preset/pcm-b64)
    "fire_srv":  "/robot/weapon/fire",      # std_srvs/Trigger (간이) — 설계 §10.2
    "cmd_vel":   "/robot/cmd_vel",          # geometry_msgs/Twist (RELIABLE) — 최종 출구 (safety_filter 발행)
    "cmd_vel_manual": "/robot/cmd_vel_manual",  # geometry_msgs/Twist — C2 manual override 입력
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
    # Zone 기반 라우팅 (2026-05-22)
    "routing_state": "/routing_state",      # std_msgs/String (JSON) — zone 경유 진행상황
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

# 클래스 매핑 — cobot3_4class 커스텀 모델 (2026-05-26 교체).
# {0: person, 1: soldier, 2: drone, 3: animal}
# WHY 교체: COCO80 범용 → DMZ 경계근무 특화 4-class 모델로 정확도 향상.
# alert 정책: person/soldier/drone → intruder_alert, animal → animal_alert.
YOLO_CLASSES = {
    0: "person",
    1: "soldier",
    2: "drone",
    3: "animal",
}

# animal 그룹 (alert 정책용) — 4-class 모델에서 class 3이 animal
YOLO_ANIMAL_CLASS_IDS = {3}

# YOLO 인퍼런스 채널 선택 (2026-05-24). CPU 부하 조절용.
# 기본: inspect + tp_a (1차 정찰 카메라 2채널). 전부 켜려면
# C2_YOLO_CAMERAS=inspect,tp_a,tp_b,tp_c,tp_d 로 override.
YOLO_CAMERAS: set[str] = {
    c.strip() for c in os.environ.get("C2_YOLO_CAMERAS", "inspect,tp_a").split(",")
    if c.strip()
}

# YOLO 사용자 사양 #8 (2026-05-20): conf 0.7 단일 임계. bbox 표시 + alert 동일.
YOLO_ALERT_CONF = float(os.environ.get("C2_YOLO_ALERT_CONF", "0.7"))
YOLO_ALERT_COOLDOWN = float(os.environ.get("C2_YOLO_ALERT_COOLDOWN", "3.0"))
# P3 신규: 동물 alert 정책 (독립 cooldown)
YOLO_ANIMAL_ALERT_CONF = float(os.environ.get("C2_YOLO_ANIMAL_ALERT_CONF", "0.50"))
YOLO_ANIMAL_ALERT_COOLDOWN = float(os.environ.get("C2_YOLO_ANIMAL_ALERT_COOLDOWN", "5.0"))
# 자동사격 쿨다운 (Feature 3 — 안정 감지 후 재발동 방지)
AUTO_FIRE_COOLDOWN_S = float(os.environ.get("GP_AUTO_FIRE_COOLDOWN_S", "30.0"))

# TP fixed-camera projection — must match main_side/camera_publisher.py.
TACTICAL_CAMERA_HEIGHT = float(os.environ.get("GP_TACTICAL_CAMERA_HEIGHT", "8.0"))
TACTICAL_CAMERA_FOCAL  = float(os.environ.get("GP_TACTICAL_CAMERA_FOCAL",  "6.0"))
TACTICAL_CAMERA_APERTURE = 20.955
TACTICAL_CAMERA_FORWARDS = {
    "tp_a": (0.15,  1.0, -0.18),
    "tp_b": (-0.22, 1.0, -0.18),
    "tp_c": (0.0,   1.0, -0.28),
    "tp_d": (-0.15, 1.0, -0.18),
}
TACTICAL_CAMERA_HEIGHT_OFFSETS = {
    "tp_a": 1.0, "tp_b": 0.7, "tp_c": 0.0, "tp_d": 0.0,
}
TACTICAL_DEFAULT_RANGE_M = float(os.environ.get("C2_TACTICAL_DEFAULT_RANGE_M", "35.0"))
