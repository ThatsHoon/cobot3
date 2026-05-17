# cobot3 — 개발환경 & 사전설정 (Project Requirements)

cobot3(GP 경계근무 spot_with_arm) 시스템을 **처음 기동하기 위한 개발환경·사전설치·
환경변수·기동절차·트러블슈팅**을 정리한 문서. 시스템 설계는
[`gp-quadruped-system-design.md`](gp-quadruped-system-design.md) 참조.

---

## 1. 머신 역할 (2-PC 설계, 임시는 1-PC)

| 측 | 폴더 | 역할 | 핵심 런타임 |
|---|---|---|---|
| **main_side** | `cobot3/main_side/` | **Isaac Sim 시뮬레이터 PC** | Isaac `python.sh`, camera_publisher, (2-PC 시) video_degrade |
| **sub1_side** | `cobot3/sub1_side/` | **지휘통제실(C2) 별도 PC** | web_server(FastAPI venv), web(Next.js), PostgreSQL |

> 분리 규약: main_side 스크립트는 **Isaac 번들 python.sh**(시스템 ROS 미소싱),
> sub1_side/server 는 **시스템 ROS 2 Humble + venv** 사용. 섞지 말 것.

---

## 2. 사전 요건 (OS / 핵심 SW)

- Ubuntu 22.04, NVIDIA GPU + 드라이버, **prime nvidia** 모드(외부 모니터/렌더)
- **Isaac Sim 5.1.0** 소스빌드: `~/dev_ws/isaac_sim/isaacsim/_build/linux-x86_64/release`
  (Python **3.11** 내장 — 시스템 ROS Humble 의 3.10 과 ABI 불일치, §6 핵심)
- **ROS 2 Humble** (`/opt/ros/humble`, Python 3.10)
- **PostgreSQL 14** (로컬, `cobot3` DB)
- **Node 20** (Next.js)

### 2.1 apt 사전설치 (이번에 막혔던 것들 — 필수)
```bash
echo 'rokey1234' | sudo -S apt-get install -y \
  python3.10-venv python3-pip
```
- `python3.10-venv` 없으면 sub1_side server `.venv` 의 pip 부트스트랩 실패.
- RMW 는 **FastDDS(`rmw_fastrtps_cpp`) 로 통일** — ROS 2 Humble 기본
  제공이라 별도 apt 불요. CycloneDDS 는 사용하지 않음(크로스-벤더
  RMW 비지원 → Isaac 동봉 FastDDS 와 통일). 구 `cyclonedds.xml` 삭제됨.

---

## 3. 환경변수 (`~/.bashrc` 에 기설정)

```bash
export ROS_DOMAIN_ID=130
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE=/home/rokey/dev_ws/isaac_sim/cobot3/main_side/fastdds_no_shm.xml
export ROS_LOCALHOST_ONLY=0
export COBOT3_DB_URL="postgresql:///cobot3"
```
RMW 는 **FastDDS 로 통일**(Isaac 동봉이 FastDDS → 크로스-벤더 RMW 비지원).
CycloneDDS 는 사용하지 않는다.
- `fastdds_no_shm.xml` = SharedMemory 비활성(UDP-only). NVIDIA 공식
  `IsaacSim-ros_workspaces/humble_ws/fastdds.xml` 과 동일 — 2-PC ROS2 시 필수.
- alias: `isaac` / `isaac-mcp` (둘 다 RMW·DOMAIN prefix 포함),
  함수 `cobot3-cobot3_web-restart_full` (C2 스택 일괄 재기동).

---

## 4. 최초 설치(빌드 산출물 재생성)

`.venv / node_modules / .next / __pycache__` 는 git 미추적(정리됨).
GP 씬·에셋은 `main_side/scene/` 에 **자체완결로 동봉**(clone 만으로 열림 —
Spot 만 공개 S3 URL, 최초 로드시 인터넷). 최초/클론 후 1회:

```bash
# sub1_side web_server (시스템 ROS 가시 위해 --system-site-packages)
cd ~/dev_ws/isaac_sim/cobot3/sub1_side/server
python3 -m venv --system-site-packages .venv
./.venv/bin/pip install -r requirements.txt

# sub1_side web
cd ../web && npm install

# DB 스키마 (멱등 — DROP FUNCTION 포함)
createdb cobot3 2>/dev/null; psql -d cobot3 -f ../db/schema.sql

# 씬: main_side/scene/gp_scene.usd 동봉 — 별도 생성 불요(camera_publisher
#   기본값, 스크립트 상대경로). 상세: main_side/scene/README.md
# (씬 재구성 시에만) 로봇은 spot_with_arm USD(단일 아티큘레이션) 기준 —
#   gp_scene.usd 에 Spot 가 이미 로컬화 동봉(공개 S3 레퍼런스). 별도
#   URDF→USD 임포트 불요. importer 사용 시 make_default_prim 누락 무한
#   recompose 주의(§6)는 일반 원칙으로 유효.
```

---

## 5. 배포 모드 — 전송 경로 선택

전송 경로는 **두 가지**(D-확장 HTTP `/ingest` 우회 / ROS2 토픽)이고,
"같은-PC=D-확장, 2-PC=ROS2" 같은 **택1 강제가 아니다**:

- **같은 PC** → **D-확장 강제**. Isaac 내부 ROS2(py3.11) ↔ 시스템 ROS2(py3.10)
  가 같은 호스트에서 DDS 디스커버리 불통(§6)이므로 ROS2 경로는 **불가**.
- **2-PC LAN** → **D-확장·ROS2 둘 다 가능**. D-확장은 HTTP(TCP)라 POST 타깃
  URL 만 웹PC IP 로 바꾸면 그대로 동작(DDS 미사용 → py 버전 충돌 자체가 없음).
  ROS2 경로는 머신 분리 시 DDS 와이어가 ABI 무관이라 정상. **요구사항에 따라 선택.**

| | D-확장 HTTP `/ingest` | ROS2 토픽 |
|---|---|---|
| 같은-PC | ✅ (유일한 선택지) | ❌ 같은-호스트 DDS 불통(§6) |
| 2-PC LAN | ✅ 가장 단순·검증됨 | ✅ ROS 생태계 정공 |
| 적합 상황 | 영상+텔레메트리만 빠르게/확실하게, 데모, 단일 소비자 | `ros2 topic`/rosbag/rqt·다중 구독자·DDS QoS·실로봇 확장 |
| 구현 부담 | urllib POST(Isaac 의존 없음), 동작 검증 완료 | OG ROS2 브리지 + fastdds UDP-only 세팅 |
| main_side | `camera_publisher.py` in-process 캡처(rgb/depth annotator + Articulation joint + base pose→sim-GPS) → web_server `POST /ingest/*` | OG ROS2 브리지 발행 → LAN |
| 기동 | 아래 §5.1 (같은-PC) / 2-PC 는 POST 타깃을 웹PC IP 로 | 설계서 본문(2-PC ROS2 정공) |

### 5.1 임시 같은-PC 기동 절차
```bash
# (A) C2 스택 (sub1_side) — web_server+web+db
cobot3-cobot3_web-restart_full          # ~/.bashrc 함수

# (B) Isaac + 카메라/텔레메트리 uplink (main_side)
#   GUI 로 보며:  사용자 터미널에서  ! ~/dev_ws/isaac_sim/cobot3/main_side/run_camera_pub_gui.sh
#   headless:     ~/dev_ws/isaac_sim/cobot3/main_side/run_camera_pub.sh

# (C) 확인
curl -s localhost:8000/healthz ; curl -s localhost:8000/ingest/stats
#   브라우저: http://localhost:3000  (영상벽 WebRTC + 상태/맵/관절/GPS)
```
> robot_state 의 mode/battery/waypoint 는 보행 FSM 미구현이라 비어있음
> (전송수단 무관 — locomotion 노드 구현 시 채워짐).

### 5.2 2-PC 실배포 워크드 예시

**IP 단일소스(SSOT) = `common/site.env`** — 배포지 변경 시 여기만 수정하면
양측(C2_INGEST_URL·FastDDS 프로파일) 자동 반영. 아래는 현장 검증 예시값:
`MAIN_SIDE_IP=192.168.10.94`(Isaac), `SUB1_SIDE_IP=192.168.10.16`(C2/웹),
같은 LAN(`192.168.10.0/24`), `ROS_DOMAIN_ID=130`, `rmw_fastrtps_cpp`.

**영상·텔레메트리 (D-확장 — 검증·운용중, 권장)**

| 측 | 설정 |
|---|---|
| main_side | **IP 단일소스 = `common/site.env`** (`MAIN_SIDE_IP`/`SUB1_SIDE_IP`). 런처가 `common/site.sh` 로 `C2_INGEST_URL`(=`http://$SUB1_SIDE_IP:8000`) 자동 파생 — bashrc·repo 하드코딩 없음. 배포지 변경 시 site.env 만 수정 |
| sub1_side | **추가 설정 없음** — `/ingest/*` 무인증, web_server `--host 0.0.0.0`(run.sh 기본). `cobot3-cobot3_web-restart_full` 로 가동만. 방화벽 :8000 은 도달 검증됨(`/healthz`·`/ingest/stats`=200) |
| 확인 | main 로그 `uplink ok/err` 의 ok 증가 / `curl http://192.168.10.16:8000/ingest/stats` 카운트 증가 / C2 ros_bridge `ingest=LIVE` |

**C2→시뮬 명령 토픽 (ROS2 정공 — 전송 prep, 미완)**

| 측 | 설정 | 문서 |
|---|---|---|
| main_side | FastDDS 크로스호스트: 런처가 `common/site.env` 로 `fastdds_main.xml` 치환본을 `~/.config/cobot3/` 에 자동 생성(`cobot3_fastdds_profile main`) + OS 버퍼 + 방화벽 | `main_side/FASTDDS.md` |
| sub1_side | `common/site.sh`+`cobot3_fastdds_profile web` 로 `fastdds_web.xml` 자동 치환본 + OS 버퍼 + 방화벽 | `sub1_side/FASTDDS.md` |
| **한계** | 전송이 열려도 **Isaac 측 명령 구독·실행 노드 미구현** → 토픽이 DDS 까지 가도 시뮬이 실행 안 함. 별도 구현 필요(설정 문제 아님) | `main_side/FASTDDS.md §6` |

> 두 경로는 **병행 가능**: 영상은 D-확장 그대로, 제어는 ROS2 추가.

---

## 6. 트러블슈팅 (이번 세션 근본원인 요약)

| 증상 | 원인 | 대응 |
|---|---|---|
| 같은-PC `ros2 topic` 에 Isaac Publisher 0 | Isaac 번들 ROS2(py3.11) ↔ 시스템(py3.10) 같은-호스트 DDS 불통(cyclone/LD/scrub/UDP-only 전부 무효) | **D-확장 HTTP 우회**(§5) / 실배포 2-PC LAN |
| `[json.exception.parse_error.101] last read: 's'` 스팸 | (MCP 가설 기각) standalone+OG 렌더프로덕트에서 `omni.usd-abi getRenderSettings failed getting a stage-id` 와 1:1 짝지어 매 렌더프레임 폭주 — 대화형 뷰포트가 렌더세팅 소유주 아님(Isaac standalone 알려진-양성). 씬/MCP/애너테이터 무관(증거: 신·구 씬 /Render 동일, MCP 제거 후 재발, 폭주가 attach 보다 먼저) | **기능 무영향 확정.** run 스크립트가 raw 로그 전량 `$LOG` 보존 + 콘솔에서만 2종 필터. getRenderSettings 성공시키려면 standalone 에 없는 뷰포트 소유주 필요 → 수정 무가치 |
| URDF 임포트 후 CPU 폭주/무한 recompose | `make_default_prim=False` → 미해결 `<defaultPrim>` 참조 | dest USD 에 defaultPrim 설정 후 참조 |
| OG `Failed to wrap graph / graph already exists` | 기존 그래프 위 edit | `stage.RemovePrim` 후 fresh `og.Controller.edit` |
| standalone OG ROS2 노드타입 미등록 | python.sh 가 ros2.bridge 미로드 | `enable_extension("isaacsim.ros2.bridge")` + `update()` 펌프 |
| Isaac GUI 백그라운드로 안 뜸(exit 144) | harness 백그라운드 = DISPLAY 없음 | 사용자 터미널 `! ...run_camera_pub_gui.sh` |
| web_server `exec: uvicorn: not found` | PATH 의존 | run.sh 가 `.venv/bin/uvicorn` 명시 사용(적용됨) |
| `cleanup_old_data() 반환형 변경 불가` | SQL 비멱등 | schema.sql `DROP FUNCTION IF EXISTS` 선행(적용됨) |
| C2 로그 `⚠ /c2/video/compressed 수신 0` | 안 쓰는 구 ROS2 경로 헬스 | ros_bridge 헬스 ingest-인지→`ingest=LIVE`(적용됨) |

상세 패턴은 스킬 참조: `gp-quadruped/references/ros2-interop-and-bypass.md`,
`isaac-sim-mcp/references/debugging.md`, `isaac-sim-bridge/references/installation.md`.
