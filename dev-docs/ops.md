# 운용 가이드

## 1. 기동 순서

### 원커맨드 기동 (권장)

**Main PC:**
```bash
cobot3-start_all   # 역할=MAIN 자동판별 (MAIN_SIDE_IP 일치 확인)
```
실행 내용:
- `_cobot3_isaac_gui_up` → `run_camera_pub_gui.sh` (GP_HEADLESS=0)
- `run_degrade.sh` (front+rear 2인스턴스)
- `run_telemetry_bridge.sh`
- **(DMZ Sentry M9)** `world_odom_tf_pub.py` (Nav2 TF 트리: world→odom static)
- **(DMZ Sentry M9)** `landmarks_pub.py` (/scene/landmarks latched 발행)

**C2 PC:**
```bash
cobot3-start_all   # 역할=C2 자동판별
```
실행 내용:
- `_cobot3_pg_up` → PostgreSQL 시작 + 스키마 확인 (alerts/patrol_state_log/intruder_states_log 포함)
- `_cobot3_web_up` → uvicorn :8000 + next dev :3000
- `_cobot3_foxglove_up` → foxglove_bridge :8765 + Lichtblick Docker :8080
- **(DMZ Sentry M9)** `run_nav2.sh` (Nav2 stack: map_server/planner/controller/BT/velocity_smoother)
- **(DMZ Sentry M9)** `cmd_vel_safety_filter.py` (Nav2 → /robot/cmd_vel drive/turn 분리)
- **(DMZ Sentry M9)** `nav2_patrol.py` (mission_command 상태머신 + alert hold)

로그 파일: `/tmp/cobot3_{world_odom_tf,landmarks_pub,nav2,cmd_vel_safety,nav2_patrol}.log`

### 단계별 기동 (디버그)

**Main PC:**
```bash
cd ~/dev_ws/isaac_sim/cobot3/main_side
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=130 RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_LOCALHOST_ONLY=0
export FASTRTPS_DEFAULT_PROFILES_FILE=./fastdds_no_shm.xml

# (1) Isaac GUI + OG ROS2
bash run_camera_pub_gui.sh &    # 로그: /tmp/cobot3_isaac_gui.console.log

# (2) 비디오 압축 (2인스턴스)
bash run_degrade.sh &           # 로그: /tmp/cobot3_degrade.log

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

## 2. 정지

```bash
cobot3-down_all   # 역할별 모든 프로세스 종료

# 수동 정지 (Main PC):
pkill -f "camera_publisher\|video_degrade\|telemetry_bridge"

# 수동 정지 (C2 PC):
pkill -f "uvicorn\|next-server\|foxglove_bridge\|video_degrade"
docker stop cobot3-lichtblick 2>/dev/null
```

---

## 3. 환경변수 완전 목록

### ROS2/DDS (양쪽 PC 공통)
| 변수 | 값 | 설명 |
|------|-----|------|
| `ROS_DOMAIN_ID` | `130` | 도메인 격리 |
| `RMW_IMPLEMENTATION` | `rmw_fastrtps_cpp` | FastDDS 미들웨어 |
| `FASTRTPS_DEFAULT_PROFILES_FILE` | 절대경로 XML | SHM 비활성 프로파일 |
| `ROS_LOCALHOST_ONLY` | `0` | 크로스호스트 허용 |
| `ROS_DISTRO` | `humble` | 배포판 |

### DMZ_Zone / YOLO (P2~P3, 2026-05-20)

| env | 기본값 | 설명 |
|---|---|---|
| `GP_GO2_SPAWN_ZONE` | `cube` | `cube`=기존 Cube nearest-vertex spawn / `dmz`=DMZ_Zone home(0,0) nearest-vertex |
| `C2_YOLO_MODEL` | (없음) | YOLO 가중치 경로. 비우면 `sub1_side/server/models/*.pt` → `yolov8n.pt` 폴백 |
| `C2_YOLO_ALERT_CONF` | `0.55` | person alert 최소 confidence |
| `C2_YOLO_ALERT_COOLDOWN` | `3.0` | person alert cooldown(s) |
| `C2_YOLO_ANIMAL_ALERT_CONF` | `0.50` | animal alert 최소 confidence |
| `C2_YOLO_ANIMAL_ALERT_COOLDOWN` | `5.0` | animal alert cooldown(s) |

### Main PC (Isaac Sim)
| 변수 | 기본값 | 설명 |
|------|-------|------|
| `GP_HEADLESS` | `0` | `1`=헤드리스, `0`=GUI 창 표시 |
| `GP_SCENE` | `scene/gp_scene.usd` | 로드할 USD 씬 |
| `GP_SPOT_CONTROL` | `1` | SpotController + RL 정책 활성 |
| `GP_ROS2_TELEM` | `1` | OG 텔레메트리 노드 활성 |
| `GP_ROS2_CMD` | `1` | OG cmd_vel 구독 활성 |
| `DEGRADE_IN` | `/cam/front/rgb` | video_degrade 입력 토픽 |
| `DEGRADE_OUT` | `/c2/front/compressed` | video_degrade 출력 토픽 |
| `URDF_SERVER_PORT` | `8766` | URDF HTTP 서버 포트 |

### C2 PC (web_server)
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
| `C2_YOLO_MODEL` | `yolov8n.pt` | YOLO 모델 파일 |
| `NEXT_PUBLIC_C2_API` | `http://localhost:8000` | 프론트엔드 API URL (빌드타임) |
| `NEXT_PUBLIC_GP_ROBOT` | `gp0` | 프론트엔드 로봇 ID (빌드타임) |

---

## 4. 검증 명령어

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

## 5. 트러블슈팅

| 증상 | 원인 | 해결책 |
|------|------|-------|
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

---

## 6. 로그 파일

| 로그 경로 | 내용 |
|-----------|------|
| `/tmp/cobot3_isaac_gui.console.log` | Isaac Sim stdout (스팸 필터 후) |
| `/tmp/cobot3_degrade.log` | video_degrade_node (front+rear) |
| `/tmp/cobot3_telemetry_bridge.log` | telemetry_bridge_node |
| `/tmp/cobot3_server.log` | FastAPI uvicorn |
| `/tmp/cobot3_foxglove.log` | Foxglove Bridge |
| `/tmp/cobot3_web.log` | Next.js dev server |
| `/tmp/cobot3_world_odom_tf.log` | world→odom static TF (Main, M9 신규) |
| `/tmp/cobot3_landmarks_pub.log` | /scene/landmarks latched 발행 (Main) |
| `/tmp/cobot3_inspect_relay.log` | /robot/inspect/command 사이드카 (Main) |
| `/tmp/cobot3_nav2.log` | Nav2 stack launch (C2) |
| `/tmp/cobot3_cmd_vel_safety.log` | cmd_vel_safety_filter (C2) |
| `/tmp/cobot3_nav2_patrol.log` | nav2_patrol 상태머신 (C2) |
| `/tmp/cobot3_landmarks.json` | camera_publisher dump (IPC, 비-로그) |
| `/tmp/cobot3_inspect_cmd.json` | inspect_relay dump (IPC, 비-로그) |
