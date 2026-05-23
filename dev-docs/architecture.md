# 시스템 아키텍처

## 1. 2-PC 토폴로지 (2026-05-21 Go2)

```
Main PC (Isaac Sim)              C2 PC (Command Center)
192.168.10.94                    192.168.10.105
─────────────────                ──────────────────────
Isaac Sim 5.1 (Go2)              FastAPI :8000
  └ camera_publisher        ──ROS2──→ ros_bridge (rclpy, PAUSED 가드)
  └ Go2WtwController                └ db_writer → PostgreSQL :5432
  └ video_degrade ×3                └ /events WS → Next.js :3000
  └ telemetry_bridge                └ Nav2 stack + safety_filter + patrol FSM
  └ mission_echo · npc_relay        └ dualsense_worker (PS5 50Hz)
  └ world_odom_tf_pub · landmarks   └ foxglove_sdk_publisher :8767
  └ camera_info_publisher       ←   ← /robot/cmd_vel (rear/inspect/overhead)
                                    Foxglove Bridge :8765
HTTP :8766 (Go2 URDF + DAE)  ────→  Lichtblick :8080 (8765+8767 dual)
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
| 8000 | FastAPI web_server | C2 | HTTP/REST + WS | API, /events, /c2/sample, WebRTC offer, MJPEG |
| 3000 | Next.js UI | C2 | HTTP | 전술 콘솔 대시보드 |
| 5432 | PostgreSQL | C2 | TCP | 텔레메트리 저장 |
| 8080 | Lichtblick (Docker) | C2 | HTTP | Foxglove 3D 시각화 (8765+8767 dual source) |
| 8765 | Foxglove Bridge | C2 | WebSocket | ROS2→WS 릴레이 (모든 토픽) |
| **8767** | **Foxglove SDK 사이드카** | **C2** | **WebSocket** | **native SceneUpdate/PoseInFrame/ImageAnnotations/Log** |
| 8766 | URDF HTTP Server | Main | HTTP | Go2 URDF + DAE 서빙 (CORS) |
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
  reads:    gp_scene.usd + main_side/scene/go2_unitree/go2.usd
  writes:   OmniGraph /World/Graphs/sensor_bridge (단일 빌드)
  publishes: /cam/{rear,inspect,overhead}/rgb, /cam/rear/{depth,points},
             /robot/{odom,leg_joint_states}, /tf

go2_controller.py (Go2WtwController)
  requires: scene/go2_policy/{adaptation_module,body}.jit (walk-these-ways)
  requires: camera_publisher 에서 world.add_physics_callback 으로 주입
  reads:    OG SubCmd.outputs (cmd_vel, in-process)
  policy:   42-dim obs × 15-step history, PD kp=25/kd=0.6, standstill clamp

camera_info_publisher.py (Main 사이드카, 2026-05-21)
  publishes: /cam/{rear,inspect,overhead}/camera_info (1Hz latched)

world_odom_tf_pub.py (Main 사이드카)
  publishes: /tf_static (world→odom, Go2→base 2개 identity)

telemetry_bridge_node.py
  subscribes: /robot/odom
  publishes:  /robot/gps, /robot/state (5Hz)

video_degrade_node.py × 3 (rear+inspect+overhead)
  env:      DEGRADE_IN, DEGRADE_OUT
  inspect:  /cam/inspect/rgb → /c2/inspect/compressed (YOLO 입력)

ros_bridge.py (C2)
  subscribes: /robot/{state,gps,odom,leg_joint_states},
              /c2/{rear,inspect,overhead}/compressed,
              /patrol_state, /scene/landmarks, /intruder_states,
              /alerts, /animal_alerts, /rosout
  publishes:  /robot/cmd_vel (PAUSED 가드), /robot/inspect/command,
              /mission_command, /robot/nav/goal, /robot/speaker/audio
  calls svc:  /robot/weapon/fire

foxglove_sdk_publisher.py (C2 사이드카, 2026-05-21)
  requires: foxglove-sdk (pip), rclpy
  server:   ws://0.0.0.0:8767 (자체 WS)
  channels: /sdk/{intruder_markers,landmark_markers,patrol_goal_pose,
                  inspect_annotations,alert_log}

dualsense_worker.py (C2 사이드카, 2026-05-21)
  requires: pygame.joystick (PS5 DualSense)
  publishes (ros_bridge 경유):
            /robot/cmd_vel · /robot/inspect/command · /mission_command
```

---

## 5. 데이터 흐름 (End-to-End)

### 카메라 영상 다운링크 (2026-05-21, inspect 가 YOLO 입력)
```
Isaac OG (50Hz) → /cam/inspect/rgb (Image)
  → video_degrade_node (throttle 5fps, resize 640×360, JPEG q50)
  → /c2/inspect/compressed (CompressedImage)
  → ros_bridge._on_video("inspect") (OpenCV decode + YOLO dmz_sentry_best.pt)
  → ros_bridge._video["inspect"] (BGR ndarray, thread-safe lock)
  → GET /c2/video/mjpeg?camera=inspect (MJPEG 스트림)
  → Next.js DualCameraView / TripleCameraView / ImmersiveCameraView
  → person 검출 시 /alerts publish → foxglove_sdk_publisher → /sdk/alert_log
  → animal 검출 시 /animal_alerts publish → WS animal_alert event
```

### 텔레메트리 상태 업링크
```
Go2WtwController → physics simulation (500Hz)
  → Odo OG node → /robot/odom (Odometry, ~63Hz 수신)
  → telemetry_bridge_node._on_odom() (throttle 5Hz)
  → /robot/state (String JSON: {mode, gait, battery, waypoint})
  → ros_bridge._on_state()
  → db_writer.put("robot_state_log", ...) → PostgreSQL (1s batch)
  → ros_bridge._emit({"type":"state", ...})
  → asyncio._broadcast() → WS /events
  → useEvents() React hook → UI state 업데이트
```

### 원격조작 업링크 (2026-05-21, multi-source)
```
Web BaseMovementPanel / TeleopPad / DualSense PS5
  → POST /robots/gp0/cmd_vel {linear, angular, linear_y}
     또는 직접 dualsense_worker → ros_bridge.pub_cmd_vel(vx, wz, vy)
  → ros_bridge.pub_cmd_vel() — PAUSED 가드 (mode==PAUSED 시 무발행)
  → _C2Node.pub_cmd_vel() → /robot/cmd_vel (Twist)
  → camera_publisher OG SubCmd 수신 (in-process attribute read)
  → _apply_cmd() → Go2WtwController.set_cmd_vel(vx, vy, wz)
  → Go2WtwController._arbitrate() (active_teleop AND |vel|>1e-6, 0.5s TTL)
  → walk-these-ways JIT 정책 step → ArticulationAction (12-DOF)
  → standstill clamp: cmd[4]=0, cmd[9]=0 시 정지 (drift 방지)
```

### Nav2 Patrol 업링크
```
Web PatrolControls → POST /missions/command {command:"sortie"}
  → ros_bridge.pub_mission("sortie") → /mission_command
  → nav2_patrol FSM: IDLE → PATROL
  → _send_goal_now() → /navigate_to_pose action (Nav2 bt_navigator)
  → controller → velocity_smoother → /cmd_vel_nav2_raw (Twist 10Hz)
  → cmd_vel_safety_filter → /robot/cmd_vel (MUTE_MODES={"PAUSED"})
  → camera_publisher OG SubCmd → Go2WtwController
  → ±10m 사각 도착 → goal 완료 → FSM 전이
```
