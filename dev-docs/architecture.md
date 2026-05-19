# 시스템 아키텍처

## 1. 2-PC 토폴로지

```
Main PC (Isaac Sim)          C2 PC (Command Center)
192.168.10.94                192.168.10.105
─────────────────            ──────────────────────
Isaac Sim 5.1                FastAPI :8000
  └ camera_publisher    ──ROS2──→ ros_bridge (rclpy)
  └ SpotController                └ db_writer → PostgreSQL :5432
  └ video_degrade ×2              └ /events WS → Next.js :3000
  └ telemetry_bridge     ←──────   ← /robot/cmd_vel
                                 Foxglove Bridge :8765
HTTP :8766 (URDF)  ──────────→   Lichtblick :8080
                                 Cloudflare Tunnel (optional)
```

**네트워크 설정 단일소스:** `common/site.env`
```
MAIN_SIDE_IP=192.168.10.94
SUB1_SIDE_IP=192.168.10.105
PUBLIC_HOST=cobot3.thatshoon.com   # Cloudflare (선택)
```

---

## 2. 포트 맵

| 포트 | 서비스 | PC | 프로토콜 | 목적 |
|------|-------|----|---------|------|
| 8000 | FastAPI web_server | C2 | HTTP/REST + WS | API, /events, WebRTC offer |
| 3000 | Next.js UI | C2 | HTTP | 전술 콘솔 대시보드 |
| 5432 | PostgreSQL | C2 | TCP | 텔레메트리 저장 |
| 8080 | Lichtblick (Docker) | C2 | HTTP | Foxglove 3D 시각화 |
| 8765 | Foxglove Bridge | C2 | WebSocket | ROS2→WS 릴레이 |
| 8766 | URDF HTTP Server | Main | HTTP | spot_isaac.urdf 서빙 (CORS) |
| DDS UDP 7400+ | FastDDS discovery | Main+C2 | UDP | ROS2 노드 디스커버리 |

---

## 3. 서비스 레이어 (5계층)

```
Layer 5 — UI/Visualization
  Next.js :3000  ←WS /events─────────┐
  Lichtblick :8080 ←WS :8765─────────┤
                                      │
Layer 4 — API Gateway                 │
  FastAPI :8000 (REST + WS + WebRTC)  │
       ↕ asyncio                      │
Layer 3 — ROS2 Bridge                 │
  ros_bridge.py (rclpy thread)        │
       ↕ DDS domain=130 LAN           │
Layer 2 — Isaac Sim (Physics+OG)      │
  camera_publisher.py                 │
  SpotController                      │
       ↕ USD/PhysX                    │
Layer 1 — Scene/Assets                │
  gp_scene.usd → spot.usd, terrain   │
                                      │
Layer 0 — Data Persistence            │
  PostgreSQL ← db_writer (asyncpg) ───┘
```

---

## 4. 컴포넌트 의존성

```
camera_publisher.py
  requires: Isaac Sim python.sh (standalone app)
  requires: /opt/ros/humble (no-scrub)
  requires: fastdds_no_shm.xml (SHM 비활성화)
  reads:    gp_scene.usd + spot.usd (S3 fetch on first run)
  writes:   OmniGraph /World/Graphs/sensor_bridge (단일 빌드)

spot_controller.py
  requires: SpotFlatTerrainPolicy (Isaac bundle)
  requires: camera_publisher 에서 world.add_physics_callback 으로 주입
  reads:    OG SubCmd.outputs (cmd_vel, in-process)

telemetry_bridge_node.py
  requires: /opt/ros/humble rclpy
  subscribes: /robot/odom
  publishes: /robot/gps, /robot/state

video_degrade_node.py × 2
  requires: /opt/ros/humble rclpy, opencv-python, numpy
  env:      DEGRADE_IN, DEGRADE_OUT
  front:    /cam/front/rgb → /c2/front/compressed
  rear:     /cam/rear/rgb  → /c2/rear/compressed

ros_bridge.py (C2)
  requires: rclpy, asyncpg, cv2, numpy
  subscribes: /robot/state, /robot/gps, /robot/odom,
              /robot/leg_joint_states, /c2/front/compressed,
              /c2/rear/compressed, /rosout
  publishes:  /robot/cmd_vel, /robot/nav/goal,
              /robot/speaker/audio
  calls svc:  /robot/weapon/fire (std_srvs/Trigger)
```

---

## 5. 데이터 흐름 (End-to-End)

### 카메라 영상 다운링크
```
Isaac OG (50Hz) → /cam/front/rgb (Image)
  → video_degrade_node (throttle 5fps, resize 640×360, JPEG q50)
  → /c2/front/compressed (CompressedImage)
  → ros_bridge._on_video() (OpenCV decode, YOLO선택)
  → ros_bridge._video_front (BGR ndarray, thread-safe lock)
  → GET /c2/video/mjpeg (MJPEG 스트림) OR WebRTC BridgeVideoTrack
  → Next.js VideoWall 컴포넌트
```

### 텔레메트리 상태 업링크
```
SpotController → physics simulation (500Hz)
  → Odo OG node → /robot/odom (Odometry, ~63Hz 수신)
  → telemetry_bridge_node._on_odom() (throttle 5Hz)
  → /robot/state (String JSON: {mode, gait, battery, waypoint})
  → ros_bridge._on_state()
  → db_writer.put("robot_state_log", ...) → PostgreSQL (1s batch)
  → ros_bridge._emit({"type":"state", ...})
  → asyncio._broadcast() → WS /events
  → useEvents() React hook → UI state 업데이트
```

### 원격조작 업링크
```
Next.js TeleopPad → POST /robots/gp0/cmd_vel {linear, angular}
  → ros_bridge.pub_cmd_vel(lin, ang)
  → _C2Node.pub_cmd_vel() → /robot/cmd_vel (Twist)
  → camera_publisher OG SubCmd 수신 (in-process attribute read)
  → _apply_cmd() → spot_controller.set_cmd_vel(vx, 0, wz)
  → SpotController._arbitrate() (0.5s timeout)
  → SpotFlatTerrainPolicy step → ArticulationAction
```
