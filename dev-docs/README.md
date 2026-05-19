# cobot3 개발문서

GP 경계근무 4족보행 로봇 시스템 — Isaac Sim 5.1 + ROS2 Humble + FastAPI + Next.js 14

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
ros2 topic hz /robot/odom          # ~63 Hz (Main PC에서)
ros2 topic hz /c2/front/compressed # ~5 Hz  (Main PC에서)
curl http://localhost:8000/healthz  # C2 서버 정상 확인
```

---

## 시스템 한눈에 보기

```
┌─────────────────── Main PC (192.168.10.94) ───────────────────┐
│  Isaac Sim 5.1 (spot.usd, gp_scene.usd)                       │
│  ┌─ camera_publisher.py ─────────────────────────────────┐    │
│  │  OmniGraph: sensor_bridge                             │    │
│  │  RPFront/RPRear → CamFront/CamRear (50Hz)             │    │
│  │  LegJS → /robot/leg_joint_states                      │    │
│  │  Odo → OdoPub → /robot/odom                           │    │
│  │  TF  → /tf                                            │    │
│  │  SubCmd ← /robot/cmd_vel                              │    │
│  └────────────────────────────────────────────────────────┘   │
│  SpotController (RL policy, 500 Hz physics)                    │
│  video_degrade_node × 2 (5fps JPEG /c2/{front,rear}/compressed)│
│  telemetry_bridge_node (/robot/odom → /robot/gps + /robot/state)│
└──────────────────────── ROS2 DDS domain=130 ──────────────────┘
                              ↕ LAN (FastDDS UDP-only)
┌─────────────────── C2 PC  (192.168.10.105) ───────────────────┐
│  FastAPI :8000 ← ros_bridge (rclpy thread)                     │
│    REST: /robots/gp0/state, /gps, /goto, /fire, /cmd_vel       │
│    WS:   /events  (state·gps·detection·fire·log·diag)          │
│    MJPEG: /c2/video/mjpeg                                       │
│  PostgreSQL :5432 ← db_writer (asyncpg batch)                  │
│  Next.js  :3000  (VideoWall, MapTrack, EngagementConsole …)    │
│  Foxglove Bridge :8765  ←→ Lichtblick :8080                    │
└───────────────────────────────────────────────────────────────┘
```
