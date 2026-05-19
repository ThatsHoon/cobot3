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

**C2 PC:**
```bash
cobot3-start_all   # 역할=C2 자동판별
```
실행 내용:
- `_cobot3_pg_up` → PostgreSQL 시작 + 스키마 확인
- `_cobot3_web_up` → uvicorn :8000 + next dev :3000
- `_cobot3_foxglove_up` → foxglove_bridge :8765 + Lichtblick Docker :8080

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
