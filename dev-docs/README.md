# cobot3 개발문서

GP 경계근무 4족보행 로봇 시스템 — Isaac Sim 5.1 + Unitree **Go2** (walk-these-ways RL) + ROS2 Humble + FastAPI + Next.js 14 + Foxglove SDK

---

## 문서 맵

| 문서 | 내용 |
|------|------|
| [architecture.md](architecture.md) | 2-PC 토폴로지, 포트 맵, 서비스 의존성, 통신 흐름 |
| [main-side.md](main-side.md) | Isaac Sim 측: OmniGraph, SpotController, 센서, 텔레메트리 |
| [sub1-side.md](sub1-side.md) | C2 측: FastAPI REST/WS, ROS bridge, Next.js UI, PostgreSQL |
| [ros2-interface.md](ros2-interface.md) | 토픽·서비스 완전 참조 (타입·QoS·Hz) |
| [ops.md](ops.md) | 기동 순서, 환경변수, FastDDS 설정, 트러블슈팅 |
| [CHANGELOG.md](CHANGELOG.md) | 주요 변경 이력 |
| [design-ros2-bridge.md](design-ros2-bridge.md) | ROS2 정공 양방향 통신 설계 스펙 (2026-05-18) |
| [architecture.html](architecture.html) | 시스템 아키텍처 인터랙티브 시각화 |
| [gp-quadruped-system-design.md](gp-quadruped-system-design.md) | 구 설계서 (아카이브) |
| [project_requirments.md](project_requirments.md) | 개발환경 초기 설정 가이드 |

---

## 30초 퀵스타트

### Main PC (Isaac Sim)
```bash
cobot3-start_all   # 역할=MAIN 자동판별 → Isaac GUI + degrade + telemetry_bridge
```

### C2 PC (Command Center)
```bash
cobot3-start_all   # 역할=C2 자동판별 → PG + web_server + Next.js + Foxglove + Lichtblick
```

### 확인
```bash
ros2 topic hz /robot/odom              # ~63 Hz (Main PC에서)
ros2 topic hz /c2/inspect/compressed   # ~5 Hz  (Main PC에서)
curl http://localhost:8000/healthz      # C2 서버 정상 확인
curl -I http://localhost:8767           # foxglove SDK WS 서버 (101 Switching Protocols)
```

---

## 시스템 한눈에 보기 (2026-05-21 Go2)

```
┌─────────────────── Main PC (192.168.10.94) ────────────────────┐
│  Isaac Sim 5.1 (go2.usd, gp_scene.usd)                          │
│  ┌─ camera_publisher.py ─────────────────────────────────────┐  │
│  │  OmniGraph: sensor_bridge                                 │  │
│  │  RP{Rear,Inspect,Overhead} → Cam{Rear,Inspect,Overhead}   │  │
│  │  LegJS → /robot/leg_joint_states                          │  │
│  │  Odo → OdoPub(frame=Go2) → /robot/odom                    │  │
│  │  TF  → /tf (RELIABLE, Nav2 호환)                          │  │
│  │  SubCmd ← /robot/cmd_vel                                  │  │
│  │  inspect 짐벌 stabilization + overhead North-up           │  │
│  └────────────────────────────────────────────────────────────┘  │
│  Go2WtwController (walk-these-ways RL, 42×15 obs, standstill 클램프)│
│  video_degrade × 3 (rear+inspect+overhead → /c2/*/compressed)   │
│  telemetry_bridge_node + mission_echo + npc_relay               │
│  world_odom_tf_pub (world→odom + Go2→base 2-static TF)          │
│  camera_info_publisher (3-카메라 CameraInfo latched)            │
│  HTTP :8766 (Go2 URDF + DAE)                                    │
└─────────────────── ROS2 DDS domain=130 ────────────────────────┘
                              ↕ LAN (FastDDS UDP-only)
┌─────────────────── C2 PC  (192.168.10.105) ────────────────────┐
│  FastAPI :8000 ← ros_bridge (rclpy thread, PAUSED 가드)        │
│    REST: /robots/gp0/state, /gps, /missions/command,           │
│          /robots/{rid}/{cmd_vel,inspect,fire}, /c2/sample      │
│    WS:   /events  (state·gps·alert·patrol_state·diag·…)        │
│    MJPEG: /c2/video/mjpeg?camera={rear,inspect,overhead}        │
│  Nav2 stack + cmd_vel_safety_filter + nav2_patrol FSM          │
│  dualsense_worker (PS5 폴링 50Hz)                              │
│  foxglove_sdk_publisher :8767 (native SceneUpdate/PoseInFrame) │
│  PostgreSQL :5432 ← db_writer (asyncpg batch)                  │
│  Next.js  :3000  (DualCameraView, MapTrack, BaseMovementPanel, │
│                   PatrolControls, ImmersiveCameraView…)         │
│  Foxglove Bridge :8765  ←→ Lichtblick :8080 (8765+8767 동시)   │
└─────────────────────────────────────────────────────────────────┘
```
