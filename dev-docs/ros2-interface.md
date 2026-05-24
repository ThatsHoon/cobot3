# ROS2 인터페이스 참조

ROS_DOMAIN_ID=130, RMW=rmw_fastrtps_cpp, FastDDS UDP-only

---

## 실측 LAN 트래픽 (2026-05-24)

| 측정 시점 | Main → C2 LAN TX | 비고 |
|-----------|------------------|------|
| 변경 전 | **17.9 MB/s** | depth raw 9MB/s + FastDDS multicast 누출 ~8MB/s |
| 변경 후 | **0.57 MB/s** | depth 압축(`/c2/tp_*/depth_compressed`) + 구독 정리 |

상세 분석: [communication-optimization.md](communication-optimization.md)

---

## 토픽 목록

### 다운링크 (Main PC → C2 PC, 2026-05-24 7-카메라 + 4 depth 압축 구성)

| 토픽 | 타입 | QoS | Hz | 발행자 | 구독자 |
|------|------|-----|----|-------|-------|
| `/cam/rear/rgb` | sensor_msgs/Image | BEST_EFFORT depth=5 | ~50 | OG CamRear | video_degrade_node (rear) |
| `/cam/inspect/rgb` | sensor_msgs/Image | BEST_EFFORT depth=5 | ~50 | OG CamInspect | video_degrade_node (inspect) — YOLO 입력 |
| `/cam/overhead/rgb` | sensor_msgs/Image | BEST_EFFORT depth=5 | ~50 | OG CamOverhead | video_degrade_node (overhead) |
| `/cam/rear/depth` | sensor_msgs/Image (32FC1) | BEST_EFFORT depth=5 | ~50 | OG CamRearDepth | Lichtblick |
| `/cam/{rear,inspect,overhead}/camera_info` | sensor_msgs/CameraInfo | **RELIABLE + TRANSIENT_LOCAL** | 1 latched | `camera_info_publisher.py` | Lichtblick 3D frustum/투영 |
| `/cam/rear/points` | sensor_msgs/PointCloud2 | BEST_EFFORT depth=5 | ~50 | OG CamRearPCL (type=depth_pcl) | Foxglove → 3D!go2 보울 |
| `/c2/rear/compressed` | sensor_msgs/CompressedImage | BEST_EFFORT depth=5 | 5 | video_degrade_node | ros_bridge._on_video("rear") |
| `/c2/inspect/compressed` | sensor_msgs/CompressedImage | BEST_EFFORT depth=5 | 5 | video_degrade_node | ros_bridge._on_video("inspect") **+ YOLO** |
| `/c2/overhead/compressed` | sensor_msgs/CompressedImage | BEST_EFFORT depth=5 | 5 | video_degrade_node | ros_bridge._on_video("overhead") |
| `/c2/tp_{a,b,c,d}/compressed` | sensor_msgs/CompressedImage | BEST_EFFORT depth=5 | ~2 | video_degrade_node (TP) | ros_bridge._on_video("tp_*") **+ YOLO** (config.YOLO_CAMERAS 가드) |
| `/cam/tactical/tp_{a,b,c,d}/depth` | sensor_msgs/Image (32FC1) | BEST_EFFORT depth=5 | 1-5 | OG CamTP*Depth | **로컬만** — `depth_degrade_node` (Main 내부) |
| `/c2/tp_{a,b,c,d}/depth_compressed` (**2026-05-24 신규**) | sensor_msgs/CompressedImage (PNG 16UC1 320×180) | BEST_EFFORT depth=5 | ~2 | `depth_degrade_node` | ros_bridge._on_depth — 3D projection 거리 샘플. 압축률 ~2.4% (920KB→22KB) |
| `/robot/odom` | nav_msgs/Odometry | RELIABLE depth=10 | ~63 | OG OdoPub (chassisFrameId=Go2) | telemetry_bridge, ros_bridge._on_odom |
| `/robot/gps` | sensor_msgs/NavSatFix | RELIABLE depth=10 | 5 | telemetry_bridge_node | ros_bridge._on_gps |
| `/robot/state` | std_msgs/String (JSON) | RELIABLE depth=10 | 5 | telemetry_bridge_node | ros_bridge._on_state |
| `/robot/leg_joint_states` | sensor_msgs/JointState | RELIABLE depth=10 | ~500 | OG LegJS | ros_bridge._on_leg |
| `/tf` | tf2_msgs/TFMessage | **RELIABLE** depth=10 | ~50 | OG TF (Nav2 호환) | Foxglove, Nav2 tf_buffer |
| `/tf_static` | tf2_msgs/TFMessage | RELIABLE+TRANSIENT_LOCAL | latched | `world_odom_tf_pub.py` (world→odom, Go2→base 2개) | Nav2, Lichtblick URDF |
| `/rosout` | rcl_interfaces/Log | RELIABLE depth=10 | on-event | 각 ROS2 노드 | ros_bridge._on_rosout (level>=30만) |

> 구 `/cam/front/*` 토픽은 모두 제거. inspect 카메라가 YOLO 입력 역할 인수.

### 업링크 (C2 PC → Main PC)

| 토픽/서비스 | 타입 | QoS | 발행자 | 구독자 |
|-----------|------|-----|-------|-------|
| `/robot/cmd_vel` | geometry_msgs/Twist | RELIABLE depth=10 | ros_bridge.pub_cmd_vel · cmd_vel_safety_filter | OG SubCmd → Go2WtwController |
| `/robot/nav/goal` | geometry_msgs/PoseStamped | RELIABLE depth=10 | ros_bridge.publish_goal | (Nav2 사용 시 미사용) |
| `/robot/speaker/audio` | std_msgs/String (JSON) | RELIABLE depth=10 | ros_bridge.send_speaker | (미구현 소비자 — C2측 발행만) |
| `/robot/weapon/fire` | std_srvs/Trigger (service) | RELIABLE | ros_bridge.fire() (client) | (서버: C2 명령 노드 예정) |
| `/robot/inspect/command` | std_msgs/String (JSON) | RELIABLE depth=10 | ros_bridge.pub_inspect_cmd | OG SubInspect → camera_publisher._apply_inspect_cmd |

### DMZ Sentry 신규 토픽 (2026-05-20 통합)

| 토픽 | 타입 | QoS | Hz | 발행자 | 구독자 |
|------|------|-----|----|-------|-------|
| `/cam/inspect/rgb` | sensor_msgs/Image | BEST_EFFORT depth=5 | ~50 | OG CamInspect | (Foxglove · 향후 MJPEG) |
| `/cam/inspect/camera_info` | sensor_msgs/CameraInfo | BEST_EFFORT depth=5 | ~50 | OG CamInspect | (intrinsics) |
| `/scene/landmarks` | std_msgs/String (JSON) | RELIABLE+TRANSIENT_LOCAL (latched) | 0.5 | landmarks_pub.py | nav2_patrol._on_landmarks, ros_bridge._on_landmarks |
| `/intruder_states` | std_msgs/String (JSON) | RELIABLE depth=10 | (장래 5Hz) | (미구현 — intruder NPC 미스폰) | ros_bridge._on_intruders |
| `/alerts` | std_msgs/String (JSON) | RELIABLE depth=10 | on-event | ros_bridge `_on_video` alert 정책 | nav2_patrol._on_alert · web AlertsLog |
| `/detections_text` | std_msgs/String (JSON) | RELIABLE depth=10 | on-event | ros_bridge `_on_video` | (선택 소비자) |
| `/mission_command` | std_msgs/String | RELIABLE depth=10 | on-event | app.py POST /missions/command → ros_bridge.pub_mission | nav2_patrol._on_mission |
| `/patrol_state` | std_msgs/String (JSON) | RELIABLE depth=10 | 5 | nav2_patrol._publish_state | ros_bridge._on_patrol_state · web PatrolControls |
| `/navigate_to_pose` | nav2_msgs/NavigateToPose (action) | — | on-goal | nav2_patrol._send_next_goal (client) | Nav2 bt_navigator (server) |
| `/cmd_vel_nav2_raw` | geometry_msgs/Twist | RELIABLE depth=10 | 10 | Nav2 velocity_smoother | cmd_vel_safety_filter |
| `world→odom` TF | tf2_msgs/TFMessage (static) | RELIABLE+TRANSIENT_LOCAL | 1 (latched) | world_odom_tf_pub.py | Nav2 tf_buffer |

### DMZ Sentry 토픽 JSON 스키마

**`/scene/landmarks`**:
```json
{ "cube": {"x":-714.32,"y":952.93,"z":30.57},
  "cone": {"x":-937.07,"y":938.98,"z":0.0},
  "fence": [{"x":...,"y":...,"z":...}, ...] }
```

**`/mission_command`**: 단일 문자열 (`sortie|home|stop|resume|idle`).

**`/patrol_state`**:
```json
{ "mode":"PATROL", "waypoint":{"x":-937.1,"y":939.0},
  "home":{"x":-714.3,"y":952.9}, "route":[...],
  "pose":{"x":...,"y":...,"yaw":...},
  "landmarks_received": true }
```

**`/alerts`**:
```json
{ "level":"ALERT", "event":"person_detected_near_fence",
  "confidence":0.78, "bbox_xyxy":[x1,y1,x2,y2],
  "count":1, "action":"report_and_track" }
```

**`/robot/inspect/command`**:
```json
{ "pan":0.5, "tilt":0.0, "zoom":1.25,
  "look_at":[x,y,z], "absolute":true, "reset":false }
```

**`/intruder_states`**:
```json
[ {"id":"i0", "x":..., "y":..., "z":..., "label":"person"}, ... ]
```

### Foxglove SDK native 채널 (`ws://host:8767`, 2026-05-21 신규)

`server/foxglove_sdk_publisher.py` 가 자체 WS 서버를 띄워 ROS String JSON 을
foxglove well-known schema 로 변환 발행. ROS 토픽이 아니라 SDK 채널 — 일반
`ros2 topic list` 에는 안 나옴. Lichtblick UI 에서 Open Connection →
`ws://192.168.10.105:8767` 로 별도 source 추가.

| SDK 채널 | well-known schema | 입력 ROS 토픽 |
|---|---|---|
| `/sdk/intruder_markers` | `foxglove.SceneUpdate` | `/intruder_states` |
| `/sdk/landmark_markers` | `foxglove.SceneUpdate` | `/scene/landmarks` |
| `/sdk/patrol_goal_pose` | `foxglove.PoseInFrame` | `/patrol_state.waypoint` |
| `/sdk/inspect_annotations` | `foxglove.ImageAnnotations` | `/detections_text` |
| `/sdk/alert_log` | `foxglove.Log` | `/alerts` |

---

## 메시지 스키마

### `/robot/state` JSON
```json
{
  "mode": "patrol",
  "gait": "stand" | "walk",
  "battery": 95.3,
  "waypoint": 0,
  "extra": {}
}
```

### `/robot/odom` (핵심 필드)
```
pose.pose.position.{x, y, z}           — base 위치 (m, world 좌표)
pose.pose.orientation.{x, y, z, w}     — 쿼터니언 (yaw 추출에 사용)
twist.twist.linear.{x, y, z}           — 선속도 (m/s)
twist.twist.angular.{x, y, z}          — 각속도 (rad/s)
```

**yaw 추출 공식 (ros_bridge._on_odom):**
```python
siny = 2.0 * (q.w * q.z + q.x * q.y)
cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
yaw = math.atan2(siny, cosy)
```

### `/robot/cmd_vel` (Twist)
```
linear.x  — 전진 속도 (m/s), SpotController: [-0.6, 0.6]
angular.z — 회전 속도 (rad/s), SpotController: [-1.2, 1.2]
```

### `/robot/weapon/fire` (Trigger)
```
Request:  (빈 요청)
Response: success: bool
          message: "hit;distance_m" (예: "true;12.5")
```

---

## QoS 프로파일 상세

### RELIABLE (명령·텔레메트리)
```json
{
  "history": "keepLast", "depth": 10,
  "reliability": "reliable", "durability": "volatile",
  "deadline": 0.0, "lifespan": 0.0,
  "liveliness": "systemDefault", "leaseDuration": 0.0
}
```

### BEST_EFFORT (영상·TF)
```json
{
  "history": "keepLast", "depth": 5,
  "reliability": "bestEffort", "durability": "volatile",
  "deadline": 0.0, "lifespan": 0.0,
  "liveliness": "systemDefault", "leaseDuration": 0.0
}
```

> **주의:** Isaac OG ROS2 노드는 8개 키 전체 필수. 일부 생략 시 `WARNING: QoSProfile` 후 엔드포인트 미생성.

---

## FastDDS 설정

```
fastdds_no_shm.xml    — UDPv4-only, SharedMemory 비활성
fastdds_main.xml      — 2-PC LAN 프로파일 (unicast initialPeers 포함, IP 치환 필요)
```

**환경변수:**
```bash
RMW_IMPLEMENTATION=rmw_fastrtps_cpp
FASTRTPS_DEFAULT_PROFILES_FILE=/path/to/fastdds_no_shm.xml
ROS_DOMAIN_ID=130
ROS_LOCALHOST_ONLY=0    # 크로스호스트 허용
```

**SHM 비활성 이유:** Isaac 번들 FastDDS 2.6.x와 시스템 FastDDS 2.6.11이 SharedMemory 포맷 비호환
→ UDP-only로 강제하면 wire 포맷 호환 달성.
