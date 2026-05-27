# 운용 가이드

## 1. 기동 순서

### 원커맨드 기동 (권장)

**Main PC:**
```bash
cobot3-start_all   # 역할=MAIN 자동판별 (MAIN_SIDE_IP 일치 확인)
```
실행 내용 (2026-05-22):
- 강력 좀비 정리 (SIGTERM → 2s → SIGKILL 2-pass, PAT 기반)
- `_cobot3_isaac_gui_up` → `run_camera_pub_gui.sh` (GP_HEADLESS=0,
  GP_GO2_NAV=0, GP_GO2_SETTLE=500)
- `run_degrade.sh` (rear+inspect+overhead **3인스턴스**)
- `run_telemetry_bridge.sh`
- `world_odom_tf_pub.py` (world→odom + Go2→base 2개 static TF)
- `landmarks_pub.py` (/scene/landmarks latched 발행)
- `inspect_relay.py` (/robot/inspect/command → /tmp/cobot3_inspect_cmd.json)
- `mission_echo.py` (/mission_command Isaac console echo)
- `npc_relay.py` (/npc/* 명령 릴레이)
- `camera_info_publisher.py` (3-카메라 CameraInfo 1Hz latched)
- `run_urdf_server.sh` (:8780 Go2 URDF + DAE 서빙)
- `fall_relay.py` / `weapon_relay.py` / `wind_publisher.py` (전투 이벤트 릴레이)
- `run_nav2.sh` (Nav2 stack: map_server/planner/controller/BT/velocity_smoother)
- `cmd_vel_safety_filter.py` (/cmd_vel_nav2_raw → /robot/cmd_vel, linear+angular 동시 통과, MUTE_MODES={"PAUSED"})
- `nav2_patrol.py` (FSM IDLE/PATROL/HOME/PAUSED, HOME=(212.8,890.53),
  GOAL=(287.59,1129.728), /clock 안정화 90s 대기 후 기동)

**C2 PC:**
```bash
cobot3-start_all   # 역할=C2 자동판별
```
실행 내용 (2026-05-22):
- 강력 좀비 정리 (SIGTERM → 2s → SIGKILL 2-pass)
- `_cobot3_pg_up` → PostgreSQL 시작 + 스키마 확인
  (alerts/patrol_state_log/intruder_states_log 포함)
- `_cobot3_web_up` → uvicorn :8000 + next dev :3000
- `_cobot3_foxglove_up` → foxglove_bridge :8765 + Lichtblick Docker :8080
- **`foxglove_sdk_publisher.py` :8767** (foxglove SDK native 채널)
- `dualsense_worker.py` (PS5 게임패드 폴링 50Hz)
- `run_nav2.sh` (Nav2 stack 사본 — MAIN 측과 동일)
- `cmd_vel_safety_filter.py` (C2 측 사본, linear+angular 동시 통과)
- `nav2_patrol.py` (FSM IDLE/PATROL/HOME/PAUSED, HOME=(212.8,890.53),
  GOAL=(287.59,1129.728), ±10m 사각 도착)

로그 파일: `/tmp/cobot3_{world_odom_tf,landmarks_pub,nav2,cmd_vel_safety,
nav2_patrol,foxglove_sdk,dualsense,mission_echo,npc_relay,camera_info,
urdf_server,inspect_relay}.log`

> `sb` 별칭 — `source ~/.bashrc` (rokey1234 sudo 없이 환경 변수만 재로드).

### 빠른 재기동 (2026-05-21)

코드/씬 변경 후 시연 중 빠르게 재시작이 필요할 때:

```bash
cobot3-restart_all          # = cobot3-clear → cobot3-start_all (gui)
cobot3-restart_all mcp      # = cobot3-clear → cobot3-start_all + GP_MCP=1 (Isaac MCP 확장 :8766, 씬+사이드카 모두 기동)
```

내부 동작: 잔존 정리 PAT 가동 → 2초 SIGTERM → SIGKILL → 포트 점유 강제 해제 → Lichtblick 컨테이너 정리 → 그 후 `start_all` (자체 cleanup 이 이중 보호).

### Isaac Sim MCP 확장 (2026-05-22, 2026-05-27 수정)

Claude Code ↔ Isaac Sim 직접 제어 채널. `cobot3-restart_all mcp` 시 자동 기동.

| 항목 | 값 |
|------|---|
| 구현 | `whats2000/isaacsim-mcp-server` (`~/dev_ws/isaacsim-mcp-server/`) |
| 확장 버전 | `isaac.sim.mcp_extension-0.4.1` |
| 기동 방식 | **2026-05-27 수정:** `GP_MCP=1` + `camera_publisher.py` 의 `SimulationApp(extra_args=[--ext-folder, ..., --enable, isaac.sim.mcp_extension])`. 이전 방식(`isaac-sim.sh --enable`)은 별도 Kit 인스턴스로 씬 공유 불가 → 폐기. |
| 포트 | `localhost:8766` (TCP, Kit 프로세스 내부) |
| MCP 서버 진입점 | `uv run --directory ~/dev_ws/isaacsim-mcp-server isaacsim-mcp-server` |
| 도구 수 | 42 (scene, objects, lighting, robots, sensors, materials, assets, simulation, graphs) |

### Nav2 lifecycle race 해결 — Isaac 안정화 대기 (2026-05-21)

`cobot3-start_all` 의 MAIN 분기는 nav2 기동 전에 **`ros2 topic echo /clock --once`** 로 첫 클럭 메시지 도착까지 (최대 90초) 대기한다.

**문제**: Isaac 가 씬/OG 로드 중 (스폰 후 약 60–90초) CPU 점유율 매우 높음 → nav2 가 그 시점에 같이 뜨면 lifecycle service RMW response 가 손실 (planner_server `change_state` timeout 로그) → lifecycle_manager autostart 중단 → bt_navigator/behavior_server 등 `unconfigured` → `navigate_to_pose` action 부재 → patrol `WAITING_FOR_NAV2` 무한 대기. teleop 은 nav2 우회라 정상 동작 (직접 /robot/cmd_vel).

**해결**: /clock 첫 메시지 = camera_publisher 의 OG ROS2PublishClock 가 발행 시작한 시점 = OG 빌드 + 씬 로드 완료. 그 후 추가 5초 + nav2 기동 → activation 안정. nav2_patrol 은 lifecycle activation 의 8초 마진 후 기동.

복구 방법 (한 번이라도 race 발생한 경우):
```bash
pkill -9 -f "nav2_|lifecycle_manager_cobot3|nav2_patrol\.py"
cd ~/dev_ws/isaac_sim/cobot3/main_side
setsid bash run_nav2.sh </dev/null >/tmp/cobot3_nav2.log 2>&1 &
sleep 8
setsid bash -c "source /opt/ros/humble/setup.bash && export ROS_DOMAIN_ID=130 \
  RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
  FASTRTPS_DEFAULT_PROFILES_FILE=$PWD/fastdds_no_shm.xml && \
  python3 nav2_patrol.py" </dev/null >/tmp/cobot3_nav2_patrol.log 2>&1 &
```

### 단계별 기동 (디버그)

**Main PC:**
```bash
cd ~/dev_ws/isaac_sim/cobot3/main_side
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=130 RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_LOCALHOST_ONLY=0
export FASTRTPS_DEFAULT_PROFILES_FILE=./fastdds_no_shm.xml

# (1) Isaac GUI + OG ROS2
bash run_camera_pub_gui.sh &    # 로그: /tmp/cobot3_isaac_gui.console.log

# (2) 비디오/depth 압축 (7 video + 4 depth = 11 인스턴스, 2026-05-27)
# ⚠ SSH 세션에서 직접 실행 금지 — SSH 끊김 시 SIGHUP으로 전체 사망
# 권장: systemd 서비스 사용 (아래 §7 참조)
systemctl --user start cobot3-degrade.service
# 또는 로컬 터미널에서: bash run_degrade.sh &

# (3) 텔레메트리 브리지
bash run_telemetry_bridge.sh &  # 로그: /tmp/cobot3_telemetry_bridge.log
```

**C2 PC:**
```bash
cd ~/dev_ws/isaac_sim/cobot3/sub1_side

# (1) PostgreSQL
createdb cobot3 2>/dev/null
psql -d cobot3 -f db/schema.sql

# (2) FastAPI 서버
cd server && bash run.sh &       # 로그: /tmp/cobot3_server.log

# (3) Next.js UI
cd ../web && npm run dev &

# (4) Foxglove Bridge
bash ../run_foxglove_bridge.sh &

# (5) Lichtblick Docker
docker run -d --rm --name cobot3-lichtblick -p 8080:8080 \
  -v $(pwd)/../lichtblick/layout.json:/lichtblick/default-layout.json:ro \
  ghcr.io/lichtblick-suite/lichtblick:latest
```

---

## 2. Scene 에셋 동기화 (Google Drive)

`main_side/scene/` 의 대용량 바이너리(USD/USDZ/DAE/policy/.pgm)는 git-ignore 대상이므로
Google Drive 아카이브로 팀 간 공유한다.

### 업로드 (에셋 변경 후)

```bash
# git-ignore 에셋만 압축 → 프로젝트 루트에 cobot3_scene_assets_YYYYMMDD.tar.gz 생성
bash main_side/scripts/scene_pack.sh

# 생성된 tar.gz 를 Google Drive 에 수동 업로드
# 공유 링크에서 FILE_ID 확인: https://drive.google.com/file/d/<FILE_ID>/view
```

### 다운로드 (최초 클론 또는 에셋 갱신 시)

```bash
# FILE_ID 설정 (아카이브 갱신 시마다 팀에 공유)
export COBOT3_SCENE_GDRIVE_ID=<Google_Drive_File_ID>

# scene/ 에셋 복원 (gdown 미설치 시 자동 pip install)
bash main_side/scripts/scene_pull.sh
```

> **협업 규칙**: 에셋이 변경되면 `scene_pack.sh` → Drive 업로드 → `FILE_ID` 를 팀에 공유.
> 코드 변경은 git push, 에셋 변경은 Drive 업로드 세트로 진행.

---

## 3. 정지

```bash
cobot3-down_all   # 역할별 모든 프로세스 종료

# 수동 정지 (Main PC):
pkill -f "camera_publisher\|video_degrade\|telemetry_bridge"

# 수동 정지 (C2 PC):
pkill -f "uvicorn\|next-server\|foxglove_bridge\|video_degrade"
docker stop cobot3-lichtblick 2>/dev/null
```

---

## 4. 환경변수 완전 목록

### ROS2/DDS (양쪽 PC 공통)
| 변수 | 값 | 설명 |
|------|-----|------|
| `ROS_DOMAIN_ID` | `130` | 도메인 격리 |
| `RMW_IMPLEMENTATION` | `rmw_fastrtps_cpp` | FastDDS 미들웨어 |
| `FASTRTPS_DEFAULT_PROFILES_FILE` | 절대경로 XML | SHM 비활성 프로파일 |
| `ROS_LOCALHOST_ONLY` | `0` | 크로스호스트 허용 |
| `ROS_DISTRO` | `humble` | 배포판 |

### YOLO (C2)

| env | 기본값 | 설명 |
|---|---|---|
| `C2_YOLO_MODEL` | (없음) | YOLO 가중치 경로. 비우면 `sub1_side/server/models/*.pt` → `yolov8n.pt` 폴백 |
| `C2_YOLO_ALERT_CONF` | `0.55` | person alert 최소 confidence |
| `C2_YOLO_ALERT_COOLDOWN` | `3.0` | person alert cooldown(s) |
| `C2_YOLO_ANIMAL_ALERT_CONF` | `0.50` | animal alert 최소 confidence |
| `C2_YOLO_ANIMAL_ALERT_COOLDOWN` | `5.0` | animal alert cooldown(s) |
| `C2_YOLO_CAMERAS` (2026-05-24) | `inspect,tp_a` | YOLO inference 활성 채널 set. CPU 부담 조절. 전체: `inspect,tp_a,tp_b,tp_c,tp_d` |
| `C2_ZONE_MAX_EDGE_M` (2026-05-24) | `10.0` | ZoneRouter 그래프 빌드 시 zone 간 최대 거리 (m). 작을수록 가까운 zone 순차 경유, 단 너무 작으면 graph disconnect → Dijkstra start/end 직결 fallback |

### Main PC (Isaac Sim, 2026-05-21 Go2)
| 변수 | 기본값 | 설명 |
|------|-------|------|
| `GP_HEADLESS` | `0` | `1`=헤드리스, `0`=GUI 창 표시 |
| `GP_SCENE` | `scene/gp_scene.usd` | 로드할 USD 씬 |
| `GP_ROS2_TELEM` | `1` | OG 텔레메트리 노드 활성 |
| `GP_ROS2_CMD` | `1` | OG cmd_vel 구독 활성 |
| `GP_GO2_NAV` | `0` | 1=Go2WtwController 내부 NAV P-ctrl, 0=Nav2 stack 단독 |
| `GP_GO2_SETTLE` | `500` | spawn 후 NAV P-ctrl 진입 settle step 수 |
| `GP_GO2_CMD_MODE` | (없음) | `cal`=캘리브레이션 (vx=0.5 고정) |
| `GP_GO2_SPAWN_X/Y/Z` | `194.56/837.70/5.02` | Go2 spawn 위치 (기본=Routing_Zones/StartingPoint, 2026-05-22) |
| `GP_GO2_GOAL_X` | `199.09` | 시동 시 Nav 목표 X (기본=Routing_Zones/Standard_Point, 2026-05-22) |
| `GP_GO2_GOAL_Y` | `892.60` | 시동 시 Nav 목표 Y (기본=Routing_Zones/Standard_Point) |
| `GP_GO2_GOAL_Z` | `4.52` | 시동 시 Nav 목표 Z (기본=Routing_Zones/Standard_Point) |
| `DEGRADE_IN` | **필수 (2026-05-24 변경)** | `/cam/{rear,inspect,overhead,tactical/tp_*}/rgb` 중 하나. env 없으면 SystemExit |
| `DEGRADE_OUT` | **필수 (2026-05-24 변경)** | `/c2/{rear,inspect,overhead,tp_*}/compressed` 중 하나 |
| `DEPTH_IN` (2026-05-24 신규) | (인스턴스별) | TP depth 입력 토픽, 예: `/cam/tactical/tp_a/depth` |
| `DEPTH_OUT` (2026-05-24 신규) | (인스턴스별) | TP depth 압축 출력 토픽, 예: `/c2/tp_a/depth_compressed` |
| `DEPTH_FPS` (2026-05-24 신규) | `2.0` | depth_degrade 출력 fps |
| `FRAME_TIMING` (2026-05-27 신규) | `0` | `1`로 설정 시 3-point 타이밍 로그 활성화. Main: `[FT] SEND`, C2 수신: `[FT] RECV recv_gap net yolo_busy`, C2 MJPEG: `[FT] MJPEG yield gap`. 네트워크 지연·블랙아웃 진단용 |
| `DEPTH_W`, `DEPTH_H` (2026-05-24 신규) | `320, 180` | depth 다운샘플 해상도 |
| `GP_APPROACH_OBJECTS` (2026-05-26 신규) | `1` | 접근 오브젝트 활성 (0=비활성) |
| `GP_APPROACH_OBJECT_SPEED` | `1.10` | NPC 접근 속도 (m/s) |
| `GP_APPROACH_START_Y` / `_TARGET_Y` / `_GROUND_Z` | `945.0 / 920.0 / 4.45` | NPC 출발/도착 Y 좌표 + 지면 Z |
| `GP_APPROACH_ANIM_REPEAT_LABELS` | `boar,wolf` | skel animation 반복 샘플 확장 대상 label (drone 제외 — 타겟 수 ↑) |
| `GP_APPROACH_ANIM_REPEAT_CYCLES` | `300` | 기본 반복 cycle 수 |
| `GP_APPROACH_DEER_ANIM_SPEED` / `_WOLF_ / _DRONE_` | `1.0` | label 별 애니메이션 속도 |
| `GP_APPROACH_ANIM_SOURCE_START_TC` / `_END_TC` | `4.0 / 44.0` | source clip TC 범위 |
| `URDF_SERVER_PORT` | `8780` | Go2 URDF HTTP 서버 포트. **2026-05-27: 8766→8780** (MCP TCP :8766 충돌 해소) |

### C2 PC (web_server, 2026-05-21)
| 변수 | 기본값 | 설명 |
|------|-------|------|
| `COBOT3_DB_URL` | `postgresql:///cobot3` | PostgreSQL 연결 |
| `ISAAC_SIM_API_KEY` | `""` | API 인증키 (빈 값=개발 모드) |
| `C2_WEB_ORIGINS` | `http://localhost:3000,...` | CORS 허용 오리진 |
| `GP_ROBOT_ID` | `gp0` | 로봇 ID |
| `C2_HTTP_HOST` | `0.0.0.0` | 서버 바인드 주소 |
| `C2_HTTP_PORT` | `8000` | 서버 포트 |
| `C2_DB_FLUSH_SEC` | `1.0` | DB 배치 flush 주기 (초) |
| `C2_DB_QUEUE_MAX` | `20000` | 텔레메트리 큐 최대 크기 |
| `C2_YOLO_MODEL` | (없음) | `/home/rokey/Downloads/dmz_sentry_best.pt` 등 절대경로. 비우면 `server/models/*.pt` → `yolov8n.pt` 폴백 |
| `FOXGLOVE_SDK_HOST` | `0.0.0.0` | foxglove SDK 자체 WS 서버 호스트 |
| `FOXGLOVE_SDK_PORT` | `8767` | foxglove SDK 자체 WS 서버 포트 |
| `NEXT_PUBLIC_C2_API` | (없음) | 프론트엔드 API URL — 비우면 런타임 `window.location.hostname:8000` |
| `NEXT_PUBLIC_LICHTBLICK_URL` | `http://localhost:8080` | 프론트엔드 Lichtblick iframe URL |
| `NEXT_PUBLIC_GP_ROBOT` | `gp0` | 프론트엔드 로봇 ID (빌드타임) |

---

## 5. 검증 명령어

```bash
# ROS2 토픽 확인 (Main PC)
ros2 topic list | grep robot
ros2 topic hz /robot/odom              # 기대: ~63 Hz
ros2 topic hz /c2/front/compressed     # 기대: ~5 Hz

# C2 서버 확인
curl http://localhost:8000/healthz
# 기대: {"status":"ok","robot":"gp0","ros":"RosBridge","yolo":false}

curl http://localhost:8000/robots/gp0/state
# 기대: {"odom":{...,"yaw":...}, "leg_q":[...12개...], "state":{...}}

# 토픽 발행자 수 확인
ros2 topic info /cam/front/rgb    # Publishers: 1
ros2 topic info /c2/front/compressed  # Publishers: 1

# DB 적재 확인
psql -d cobot3 -c "SELECT count(*) FROM robot_state_log;"
```

---

## 6. 트러블슈팅

| 증상 | 원인 | 해결책 |
|------|------|-------|
| **영상 블랙아웃 (recv_gap 수십 초)** | SSH에서 `run_degrade.sh` 실행 → SSH 끊길 때 SIGHUP이 프로세스 그룹 전파 → 모든 degrade 노드 동시 사망. YOLO와 무관 | **영구 해결:** `systemctl --user start cobot3-degrade.service` (SSH 독립 cgroup). 진단: `journalctl --user -u cobot3-degrade.service -f` |
| **채널당 publisher=2 (중복 인스턴스)** | `run_degrade.sh` 가 여러 세션에서 중복 기동됨 | `systemctl --user stop cobot3-degrade.service` → `pgrep -f 'video_degrade\|depth_degrade' \| xargs -r kill -9` → 서비스 재시작 |
| Main → C2 LAN 트래픽이 비정상 높음 (>5 MB/s) | (a) depth_degrade 미동작 → raw `/cam/tactical/*/depth` 가 C2로 직접 흐름, (b) FastDDS multicast가 `/cam/*/rgb`를 LAN으로 누출 | (a) `ps aux \| grep depth_degrade` 확인 후 `run_degrade.sh` 재시작, (b) `cat /sys/class/net/<iface>/statistics/tx_bytes` 차분 측정 → 정상 ≤2 MB/s. 상세: communication-optimization.md §8 |
| `video_degrade` SystemExit "DEGRADE_IN env 필수" (2026-05-24) | 단독 실행 시 env 미설정 | `run_degrade.sh` 사용 또는 `DEGRADE_IN=... DEGRADE_OUT=... python3 video_degrade_node.py` |
| `detection_events` row 미증가 (2026-05-24) | YOLO 채널 제한 (`C2_YOLO_CAMERAS=inspect,tp_a` 기본) | 전체 활성화: `export C2_YOLO_CAMERAS=inspect,tp_a,tp_b,tp_c,tp_d` 후 sub1side 재시작 |
| `/robot/odom` publishers=0 | Isaac OG 미시작 or 도메인 불일치 | `ROS_DOMAIN_ID=130` 확인, Isaac 재시작 |
| `ros2 topic list` 에 토픽 없음 | `ROS_LOCALHOST_ONLY=1` | `export ROS_LOCALHOST_ONLY=0` |
| OG nodes 미실행 | `world.step(render=False)` | `world.step(render=True)` 필수 |
| FastDDS "no matching endpoint" | SHM 충돌 or 도메인 불일치 | `fastdds_no_shm.xml` 적용 확인 |
| `uvicorn: not found` | venv PATH 누락 | `server/run.sh` 사용 (`./.venv/bin/uvicorn`) |
| Isaac 로그 스팸 (`getRenderSettings`) | Standalone OG viewport 없음 (양성) | 런처 `grep -vF`로 필터링 |
| OG `Failed to wrap graph` | 기존 그래프에 증분 edit | 씬 재시작 또는 RemovePrim 후 재생성 |
| YOLO 없이 실행 | ultralytics 미설치 | 정상: `yolo_infer.enabled=False`, graceful skip |
| MCP + Isaac GUI 동시 실행 | isaac-sim-mcp extension 포트 충돌 | GUI 실행 전 MCP 제거: `claude mcp remove "isaac-sim" -s user` |
| 첫 실행 시 Spot USD 다운로드 지연 | S3 원격 에셋 | 인터넷 연결 확인, 이후 캐시 사용 |
| Nav2 `tf2_echo world Go2` 가 "incompatible QoS" | OG `/tf` qosProfile 이 BEST_EFFORT (Nav2 는 RELIABLE 기대) | `camera_publisher.py` 의 OG TF `qosProfile = _REL_QOS` 사용 (2026-05-20 B3 수정) |
| Nav2 가 `Could not find a connection between world and Go2` | OG TF 가 USD prim 이름(`Go2`) 발행, OdoPub 가 다른 frame 이름(`base_link`) → TF 트리 단절 | `OdoPub.chassisFrameId` 와 `nav2_params.robot_base_frame` 둘 다 `Go2` 로 통일 (2026-05-20 B4) |
| OG edit `OmniGraphError: Could not create node using unrecognized type 'isaacsim.ros2.bridge.ROS2SubscribeString'` | Isaac 5.1 OG 에 String subscriber 노드 미등록 | 사이드카 `main_side/inspect_relay.py` (rclpy) 가 `/robot/inspect/command` 구독 → `/tmp/cobot3_inspect_cmd.json` 으로 dump, camera_publisher 가 mtime 폴 (2026-05-20 B2) |
| cmd_vel safety filter 출력에 NaN 가 max bound 로 누설 | Python `min(a, NaN)`/`max(a, NaN)` 결과 미정의 → clamp 가 NaN 을 silently bound 로 치환 | `_on_cmd_vel` 에서 clamp 전에 `isfinite` 가드 (2026-05-20 B1) |
| Nav2 planner_server `GridBased failed to generate a valid path` + `/cmd_vel_nav2_raw` 무발행 | goal 또는 robot pose 가 `gp_static.yaml` map 영역(origin/resolution × W×H) 밖 → unknown 셀 → planner 거부 | (a) goal 좌표를 map 영역 안으로, (b) Go2 spawn pose 는 `tf2_echo world Go2` 로 확인 (`/robot/odom` 은 IsaacComputeOdometry 누적값이라 world 좌표 아님), (c) `bake_gp_static_map.py --xmin <X1> --xmax <X2> --ymin <Y1> --ymax <Y2> --res 0.5` 로 spawn·Cube·Cone 모두 포함하는 박스 재베이크 (2026-05-20 정합 완료, AABB x∈[-987.1,-111.0] y∈[-4.0,1002.9] 1753×2014 ≈ 3.37MB) |
| `/robot/odom` 좌표가 world 와 크게 다름(예: (-161,46) 인데 robot 은 Cube(-714,952) 위치에 있음) | OG `IsaacComputeOdometry` 출력은 chassisPrim 의 **누적 변위(odometry)** 이지 world 좌표 자체가 아님 | world 좌표는 `ros2 run tf2_ros tf2_echo world Go2` 로 확인. Nav2 도 TF tree 기반이므로 odom 토픽 좌표와 무관 |
| nav2_patrol sortie 시 부적절한 좌표(e.g. -208,-208,z=118) 로 plan 시도 | `/scene/landmarks` 의 fence 항목이 gp_scene `/World/Fence/*` prim 의 metadata 좌표를 그대로 잡음 | 단기: `nav2_patrol._on_landmarks` 에서 fence 무시 (현재 cube↔cone 만). 장기: ros2 parameter `patrol_waypoints_xy` 외부 주입 (2026-05-20 B5 수정) |
| Lichtblick 컨테이너 기동 실패 (Docker 다운그레이드 후) | docker-ce 20.10 ↔ containerd.io 2.2.x mismatch 가능성 | `sudo docker run --rm hello-world` daemon healthy 확인, `apt-mark hold docker-ce` 로 자동 업그레이드 차단, 필요 시 containerd.io=1.6.* 페어 맞춤 |
| Isaac 콘솔에 `Physics Simulation View is not created yet` 4000+ 경고 폭주 + `policy_tick err: IndexError` | GPU PhysX 활성 시 `physics callback 내 SingleArticulation.initialize()` 가 GPU PhysicsSimulationView 생성 실패. ~1000 step 후 `get_joint_positions()` → 0-dim array. GPU 드라이버 정상화 후 표면화. | `camera_publisher.py` 에서 `world.reset()` 직후 메인스레드에서 `SingleArticulation.initialize()` 호출 후 `_ctrl._art` 에 주입 (2026-05-22 수정) |
| Go2 가 zero-cmd 상태에서 평면상 작은 원 드리프트 | walk-these-ways fallback `_CMD_BASE` 가 step_freq=3.6 / footswing=0.15 → 정책이 계속 step 페달링 → noise 가 yaw drift 로 누적 | `go2_controller._command()` 에서 `active_teleop=False` 시 `cmd[4]=0`/`cmd[9]=0` 강제 (standstill clamp, 2026-05-21) |
| Lichtblick 에서 Go2 URDF mesh 미렌더 (link 만 표시) | URDF 루트 link 이름="base" 이지만 OG TF frame 이름="Go2" → URDFLayer 가 TF 트리에 link 없다고 인식 | `main_side/world_odom_tf_pub.py` 가 `Go2→base` identity static TF 추가 발행 (2026-05-21) |
| `/c2/sample` rx 카운터 모두 0 으로 표시 | `ros.br._node._rx` 잘못된 attribute path | `ros._node._rx` (`hasattr` 가드, 2026-05-21) |
| Next.js 빌드 `window is not defined` | `lib/api.ts` 의 `API_BASE` 가 모듈 상수 → SSR prerender 시 window 없음 | `getApiBase()` 런타임 함수 + `typeof window` guard (2026-05-19) |
| ImmersiveCameraView 런타임 `Cannot read properties of undefined (reading 'S')` | `@react-three/fiber@9.x` 가 React 19 요구, 현 프로젝트는 React 18.3.1 | `@react-three/fiber@8.18` + `@react-three/drei@9.122` 다운그레이드 (2026-05-21) |
| inspect 카메라 walking 중 흔들림 / pan 이 roll 처럼 보임 | 카메라 local axes 에 q_user 적용 + base body roll/pitch 미보정 | `_update_inspect_xform()` 에서 `q_stab=qy(-pitch)*qx(-roll)` × `q_user_base` × `_Q_FRONT` (base frame, 2026-05-21) |
| Stop 버튼 눌러도 보행 지속 | velocity_smoother/dualsense/web teleop 의 multi-publisher 잔여 발행이 ros_bridge.pub_cmd_vel 을 통과 | `ros_bridge.pub_cmd_vel` 진입 시 `patrol_state.mode==PAUSED` 면 즉시 return (2026-05-21) |
| FastDDS cross-PC discovery 실패 | `fastdds_web.xml` `__MAIN_PC_IP__` 미치환 + interfaceWhiteList 에 127.0.0.1 누락 | `~/.config/cobot3/fastdds_web.xml` 로 복사 후 sed 치환 + 127.0.0.1 추가 (2026-05-21) |
| **자동 주행(Nav2) 이 teleop 대비 느리고 멈췄다 가는 현상** | ① `cmd_vel_safety_filter.py` 의 DRIVE/TURN 이진 분리: `|angular| ≥ 0.32 rad/s` 이면 TURN 모드 진입 → `linear.x = 0` 강제 → 로봇이 정지 후 제자리 회전 → 전진 반복. teleop 은 `/robot/cmd_vel` 직접 발행으로 필터 우회. ② DWB `max_vel_x = 0.6 m/s` (teleop 은 무제한). ③ `acc_lim_x = 0.5 m/s²` — 최고속 도달 1.2s. | (A) 빠른 완화: `nav2_params.yaml` `max_vel_x` 를 1.0으로 올리고 `acc_lim_x = 1.5`로 상향. (B) 근본 해결: `cmd_vel_safety_filter.py` DRIVE/TURN 분기 제거 — linear+angular 동시 통과 허용(사족 로봇은 실제로 곡선 주행 가능). (2026-05-22 분석) |
| Isaac Sim 상단 메뉴에서 **Add → Animation Graph 옵션 없음** | `isaacsim.exp.full.kit` 에 `omni.anim.graph.*` / `omni.anim.retarget.*` / `omni.anim.people` 확장이 누락되어 Animation Graph UI 미등록. CLI `--enable` 플래그는 UI 확장에 불신뢰. | `isaacsim.exp.full.kit` `[dependencies]` 에 7개 확장 직접 추가 (2026-05-22): `omni.anim.graph.core`, `omni.anim.graph.bundle`, `omni.anim.graph.ui`, `omni.anim.retarget.core`, `omni.anim.retarget.bundle`, `omni.anim.retarget.ui`, `omni.anim.people`. Isaac Sim 재시작 시 영구 반영. |
| **M_Medical_01 캐릭터 Play 해도 애니메이션 미재생** | (1) `skel:animationSource` 만 지정 시 Animation Graph 를 우회 → 직접 바인딩 — SkelAnimation 조인트(Root/Pelvis/…)와 Skeleton 조인트(RL_BoneRoot/…) 가 0개 매칭 → 무동작. (2) Animation Graph + ControlRig 의 `retargetTags` 레이어가 없으면 리타게팅 불가. | `Isaac/People/Characters/Biped_Setup.usd` 를 씬에 reference 로 추가 (USD prim `/World/BipedSetup`) → 내장 AnimationGraph(`/CharacterAnimation/AnimationGraph`)의 StateMachine(Idle/Walk/Sit/Talk) + ControlRig 리타게팅 자동 활성. 절차 → `main-side.md § M_Medical_01 캐릭터 애니메이션` 참조. (2026-05-22) |
| **지형/가드타워가 시간대 변경 시 밝기 그대로** | 재질에 `tex_emissive`(UsdUVTexture) → `pbr_shader.emissiveColor` 연결로 **자체발광** 설정. 씬 조명(DomeLight/SphereLight) 강도와 무관하게 항상 baseColor 텍스처 색상으로 발광. | `weather_visuals.py` `_setup_lights()` 에서 7개 emissive prim 의 `inputs:scale`(Float4) attr 수집. `_apply_lights()` 에서 `Gf.Vec4f(ts,ts,ts,1.0)` 으로 프리셋별 `terrain_scale × dome_multiplier` 적용 (2026-05-27). |
| **`cobot3-restart_all mcp` 시 씬 미로드·사이드카 미기동** | `_cobot3_isaac_up mcp` 가 `isaac-sim.sh --enable mcp_extension` 로 별도 Kit 인스턴스 기동 → 씬/OG/사이드카 없는 빈 인스턴스. `_cobot3_start_all_impl` 이 mcp 모드 early-return. | `GP_MCP=1 run_camera_pub_gui.sh` 로 camera_publisher 의 동일 Kit 인스턴스에 extra_args 로 extension 주입. early-return 제거로 사이드카 동시 기동 (2026-05-27). |
| **MCP `Unknown command type: scene.get_info`** | `~/dev_ws/isaac-sim-mcp/`(구버전, 플랫 명령) 과 `~/dev_ws/isaacsim-mcp-server/`(신버전, dot 명령) 두 레포가 혼재. camera_publisher 가 구버전 ext-folder 로드. | `extra_args` 의 `--ext-folder` 를 `~/dev_ws/isaacsim-mcp-server/` 로 통일 (2026-05-27). |
| **URDF HTTP 서버(:8766) 와 MCP TCP(:8766) 포트 충돌** | `run_urdf_server.sh` 기본 포트가 MCP extension 와 동일 8766. MCP 모드 기동 시 URDF 서버 바인드 실패. | `URDF_SERVER_PORT` 기본값 8766→8780 변경. `lichtblick/layout.json` URDF URL 동기 수정 (2026-05-27). |

---

## 7. cobot3-degrade systemd 서비스 (2026-05-27 신규)

SSH 세션과 독립적으로 degrade 노드를 관리하는 systemd user 서비스.

```
위치: ~/.config/systemd/user/cobot3-degrade.service
WorkingDirectory: ~/dev_ws/isaac_sim/cobot3/main_side
```

**관리 명령:**
```bash
systemctl --user status  cobot3-degrade.service   # 상태
systemctl --user start   cobot3-degrade.service   # 시작
systemctl --user stop    cobot3-degrade.service   # 중지
systemctl --user restart cobot3-degrade.service   # 재시작
journalctl --user -u cobot3-degrade.service -f    # 실시간 로그
```

**특성:**
- `Restart=always RestartSec=3` — 서비스 전체 사망 시 3초 후 자동 재시작
- `KillMode=control-group` — stop 시 cgroup 내 모든 자식 프로세스 정리
- `StandardInput=null` — SSH/터미널 없이 독립 실행
- `loginctl enable-linger rokey` 적용 — rokey 로그인 없이도 서비스 유지
- 부팅 후 자동 시작 (`[Install] WantedBy=default.target` + enabled)

**내부 구조:** `run_degrade.sh` 의 `_restart_loop` 가 각 채널(11개)을 무한 루프로 감싸
개별 노드 크래시 시 2초 후 자동 재기동.
systemd `Restart=always` 는 `run_degrade.sh` 자체(상위 프로세스) 사망 시 복구.

**FRAME_TIMING 타이밍 계측:**
```bash
# 환경변수 FRAME_TIMING=1 (서비스 기본값)
# inspect 채널 3-point 타이밍:
journalctl --user -u cobot3-degrade.service | grep 'FT.*SEND'   # Main 발송
# C2: tail /tmp/cobot3_server.log | grep 'FT.*RECV'             # C2 수신
# C2: tail /tmp/cobot3_server.log | grep 'FT.*MJPEG'            # MJPEG 출력
```

---

## 8. 로그 파일

| 로그 경로 | 내용 |
|-----------|------|
| `/tmp/cobot3_isaac_gui.console.log` | Isaac Sim stdout (스팸 필터 후) |
| `journalctl --user -u cobot3-degrade.service` | video_degrade_node × 7 + depth_degrade_node × 4 (systemd 서비스, 2026-05-27) |
| `/tmp/degrade_crash_<channel>.log` | degrade 노드 예외 크래시 시 스택트레이스 (2026-05-27) |
| `/tmp/cobot3_telemetry_bridge.log` | telemetry_bridge_node |
| `/tmp/cobot3_server.log` | FastAPI uvicorn |
| `/tmp/cobot3_foxglove.log` | Foxglove Bridge (:8765) |
| `/tmp/cobot3_foxglove_sdk.log` | foxglove SDK 사이드카 (:8767, 신규) |
| `/tmp/cobot3_dualsense.log` | DualSense PS5 polling worker (신규) |
| `/tmp/cobot3_camera_info.log` | 3-카메라 CameraInfo latched 발행 (Main, 신규) |
| `/tmp/cobot3_mission_echo.log` | /mission_command Isaac console echo (Main, 신규) |
| `/tmp/cobot3_npc_relay.log` | /npc/* 명령 릴레이 (Main, 신규) |
| `/tmp/cobot3_urdf_server.log` | Go2 URDF HTTP 서버 (:8780) |
| `/tmp/cobot3_web.log` | Next.js dev server |
| `/tmp/cobot3_world_odom_tf.log` | world→odom + Go2→base static TF (Main) |
| `/tmp/cobot3_landmarks_pub.log` | /scene/landmarks latched 발행 (Main) |
| `/tmp/cobot3_inspect_relay.log` | /robot/inspect/command 사이드카 (Main) |
| `/tmp/cobot3_nav2.log` | Nav2 stack launch (Main + C2 각각) |
| `/tmp/cobot3_cmd_vel_safety.log` | cmd_vel_safety_filter (Main + C2 각각) |
| `/tmp/cobot3_nav2_patrol.log` | nav2_patrol 상태머신 (Main + C2 각각) |
| `/tmp/cobot3_landmarks.json` | camera_publisher dump (IPC, 비-로그) |
| `/tmp/cobot3_inspect_cmd.json` | inspect_relay dump (IPC, 비-로그) |
