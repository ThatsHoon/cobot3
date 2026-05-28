# cobot3 — GP 경계근무 4족보행 로봇 시스템 (Unitree Go2)

Isaac Sim 안에서 Unitree **Go2** 를 구동(walk-these-ways RL locomotion)하고,
7-카메라 RGB + 4채널 Depth 영상/텔레메트리/Foxglove SDK native 시각화를 별도 PC 의 지휘통제실(C2)
웹 UI 로 실시간 송출·조작하는 프로젝트.

> 2026-05 Spot+팔 → **Go2** 전환 완료. walk-these-ways RL 정책(42-dim obs ×
> 15-step history) 으로 경사면 보행 가능. spot_controller.py 와 spot_isaac.urdf
> 는 legacy 잔재.

---

## 폴더 구조

```
cobot3/
├── common/       2-PC 공통 설정 (site.env · site.sh)
│                 main_side/sub1_side 어느 쪽에도 속하지 않는
│                 IP·FastDDS 단일소스. 배포지 바뀌면 site.env만 수정.
│
├── main_side/    Isaac Sim PC 측
│                 카메라/텔레메트리 발행, Go2WtwController(walk-these-ways RL),
│                 OG sensor_bridge, camera_info_publisher, mission_echo,
│                 npc_relay, world_odom_tf_pub, landmarks_pub, inspect_relay,
│                 fall_relay, weapon_relay, wind_publisher, soldier_manager(NPC),
│                 yolo_node(YOLO 추론), depth_degrade_node, zone_router,
│                 씬·에셋, 런처, FastDDS
│
├── sub1_side/    지휘통제실(C2) PC 측
│                 FastAPI 서버, Next.js UI, PostgreSQL 스키마,
│                 ROS2 구독·cmd_vel 발행(ros_bridge), Nav2 patrol FSM,
│                 cmd_vel_safety_filter, dualsense_worker (게임패드 텔레옵),
│                 foxglove_sdk_publisher (native SceneUpdate :8767),
│                 Foxglove Bridge :8765, Lichtblick :8080
│
└── dev-docs/     설계·환경·트러블슈팅 문서
                  project_requirments.md — 개발환경·기동절차·트러블슈팅 ★먼저 읽기
                  gp-quadruped-system-design.md — 권위 설계서
                  CHANGELOG.md — 변경 이력 (Go2 전환·SDK·DualSense 등)
```

---

## 협업 룰

main 클론하시고 기능 추가하시고, 특정 기능 구현·동작이 확인되면
통째로 **새로운 브랜치**에 넣으세요.

넣으실 때 "기존에서 무슨무슨 기능이 어떻게 구현되었는지" 설명 문서 하나만
첨부해서 넣어주시면 됩니다. 그럼 제가 AI와 함께 main에서 확장하는 식으로
통합할게요.

기능 구현하실 때 폴더 구조나 참조 경로 같은 거 신경 쓰지 마시고 막 만드시고,
기능 돌아가는 것까지만 확인하시면 정리도 필요 없고 그냥 브랜치로 올리세요.
개떡같이 짜셔도 찰떡같이 통합시킬 테니까 편하고 자유롭게 설계하세요.

---

## 설정 & 실행 명령어

### 클론
```bash
git clone https://github.com/ThatsHoon/cobot3.git \
  /home/rokey/dev_ws/isaac_sim/cobot3
```

### bashrc 설정 (C2 PC — 최초 1회)
```bash
echo 'export ROS_DOMAIN_ID=130' >> ~/.bashrc
echo 'export RMW_IMPLEMENTATION=rmw_fastrtps_cpp' >> ~/.bashrc
echo 'export FASTRTPS_DEFAULT_PROFILES_FILE=/home/rokey/dev_ws/isaac_sim/cobot3/main_side/fastdds_no_shm.xml' >> ~/.bashrc  # ← 클론 위치에 맞게 경로 수정
echo 'export ROS_LOCALHOST_ONLY=0' >> ~/.bashrc
echo 'export COBOT3_DB_URL="postgresql:///cobot3"' >> ~/.bashrc
source ~/.bashrc
```

### 의존성 설치 (C2 PC — 최초 1회)
```bash
# sub1_side 서버
cd /home/rokey/dev_ws/isaac_sim/cobot3/sub1_side/server
python3 -m venv --system-site-packages .venv
./.venv/bin/pip install -r requirements.txt
# foxglove-sdk 포함 (native SceneUpdate :8767)

# Next.js UI (Three.js R3F 포함)
cd ../web && npm install

# DB 스키마 (멱등)
createdb cobot3 2>/dev/null
psql -d cobot3 -f ../db/schema.sql
```

### 실행

**Isaac PC (main_side)** — `cobot3-start_all` (역할 자동 감지)
```bash
cobot3-start_all
# → run_camera_pub_gui.sh (Isaac GUI + OG)
# → run_degrade.sh (7 RGB + 4 Depth, 11개 인스턴스)
# → run_telemetry_bridge.sh
# → world_odom_tf_pub.py · landmarks_pub.py · inspect_relay.py
# → mission_echo.py · npc_relay.py · soldier_manager.py
# → fall_relay.py · weapon_relay.py · wind_publisher.py
# → camera_info_publisher.py (전 카메라 CameraInfo latched)
# → run_urdf_server.sh (:8780 Go2 URDF 서빙)
```

**C2 PC (sub1_side)** — `cobot3-start_all`
```bash
cobot3-start_all
# → PostgreSQL + 스키마
# → uvicorn :8000 + next dev :3000
# → foxglove_bridge :8765 + Lichtblick :8080
# → foxglove_sdk_publisher.py :8767 (native SceneUpdate)
# → Nav2 stack + cmd_vel_safety_filter + nav2_patrol + dualsense_worker
```

브라우저:
- `http://localhost:3000` — 전술 콘솔 (DualCameraView · MapTrack · PatrolControls · BaseMovementPanel · ImmersiveCameraView 등)
- `http://localhost:3000/debug` — Lichtblick(8765+8767) 임베드 + ImmersiveCameraView + TopicHealthMonitor + RawJsonInspector
- `ws://<host>:8767` — Foxglove SDK native 채널 (`/sdk/intruder_markers` 등)

상세 트러블슈팅: `dev-docs/project_requirments.md`, `dev-docs/ops.md`
