# sub1_side — 지휘통제실(C2) 측

GP 경계근무 4족보행 로봇 시스템의 **별도 로컬 PC(지휘통제실)** 구성.
실배포는 시뮬레이터(Main PC)와 ROS 2(`ROS_DOMAIN_ID=130`) LAN 연결,
**임시 같은-PC 는 D-확장 HTTP `/ingest` 우회**(server `/ingest/frame`·
`/ingest/telemetry`, ros_bridge 무관). 설계: `../dev-docs/gp-quadruped-system-design.md`
(§4·§9·§12·§13·§14 + Appendix-D). **환경·사전설정·기동·트러블슈팅:
`../dev-docs/project_requirments.md` 먼저 참조.**
**2-PC LAN ROS2 정공 시 웹PC FastDDS 설정/IP 치환·트러블슈팅:
[`FASTDDS.md`](FASTDDS.md) (프로파일: [`fastdds_web.xml`](fastdds_web.xml)).**

```
sub1_side/
├── FASTDDS.md           웹PC FastDDS 설정 가이드(2-PC LAN 정공)
├── fastdds_web.xml      웹PC FastDDS 프로파일(배포 전 IP 치환)
├── CLOUDFLARE.md        공개 호스팅 가이드(Cloudflare Tunnel + Access)
├── FOXGLOVE.md          Foxglove 도입 런북(B 정공·Lichtblick·/debug)
├── run_cloudflared.sh   Cloudflare Tunnel 멱등 기동(PUBLIC_HOST SSOT)
├── cloudflared/config.yml  터널 ingress 템플릿(런타임 치환)
├── db/schema.sql        로컬 PostgreSQL 스키마(영상 외 전 데이터 — §13)
├── server/              FastAPI + rclpy + aiortc(WebRTC) + asyncpg + YOLO
│   ├── config.py        환경변수/토픽 규약
│   ├── ros_bridge.py    ROS2 다운/업링크 (별도 스레드 spin)
│   ├── db_writer.py     asyncpg COPY 배치 적재
│   ├── yolo_infer.py    서버측 YOLO (선택, graceful)
│   ├── webrtc_video.py  aiortc 영상 트랙 (5fps)
│   ├── app.py           REST + WS /events + /c2/webrtc/offer + MJPEG 폴백
│   └── run.sh
└── web/                 Next.js 14 + Tailwind — 전술 작전 콘솔 UI
```

## 데이터 경로 (설계 D7/D8/§13)

- **영상**: RealSense rgb(degrade 5fps) → web_server → **WebRTC(aiortc)** → 브라우저
  (실패 시 `/c2/video/mjpeg` 폴백). **DB 저장 안 함.**
- **영상 외 전부**: state/gps/odom/`/dsr01/joint_states`/leg joint/rosout(≥WARN)
  → ros_bridge → **로컬 Postgres**(asyncpg COPY) + WS `/events` 라이브
- **서버측 YOLO**: 수신 rgb 프레임 추론 → bbox 오버레이 + `intruder_detections` 기록
- **업링크**: 맵 클릭→`/robots/{id}/goto`, 확성기→`/speaker`, 사격→`/fire`
  (변경계열은 `X-API-Key`; 미설정 시 LAN 개발모드)

## 2-PC 실전 — C2(서브사이드) PC 설치·설정 체크리스트

> Isaac=Main PC / 웹·브리지·DB=이 C2 PC. 통신 전제 `FASTDDS.md`,
> Foxglove `FOXGLOVE.md`, 공개호스팅 `CLOUDFLARE.md`.

### A. 사전 설치 (1회, C2 PC)

```bash
# ROS 2 Humble 설치 전제(/opt/ros/humble). 그 외 apt:
echo 'rokey1234' | sudo -S apt-get install -y \
  ros-humble-foxglove-bridge docker.io postgresql \
  python3-venv python3-pip nodejs npm
# docker 그룹(재로그인 필요) — 또는 start_all_2 처럼 sudo docker 사용
echo 'rokey1234' | sudo -S usermod -aG docker "$USER"
```

### B. 리포 + IP 단일소스(SSOT) — **가장 중요**

```bash
git clone https://github.com/ThatsHoon/cobot3.git ~/dev_ws/isaac_sim/cobot3
cd ~/dev_ws/isaac_sim/cobot3
# common/site.env 를 이 배포 IP 로 (양 PC 동일 값):
#   MAIN_SIDE_IP = Isaac PC LAN IP
#   SUB1_SIDE_IP = 이 C2 PC LAN IP   ← 역할 자동판별·FastDDS 치환 기준
nano common/site.env
ip -4 addr show   # SUB1_SIDE_IP 가 이 PC 실제 LAN NIC 인지 확인(docker0/wlan 아님)
```

### C. 서버 venv / 웹 / DB

```bash
cd sub1_side/server
python3 -m venv --system-site-packages .venv      # rclpy 가시 위해 시스템 패키지
./.venv/bin/pip install -r requirements.txt
cd ../web && npm install

# DB: schema.sql 은 멱등·자가치유(구 배포 컬럼 드리프트 q/qd→arm_q/leg_q
# 자동 마이그레이션) — start_all_2 가 매 기동 자동 적용. 수동은:
createdb cobot3 2>/dev/null || true; psql -d cobot3 -f ../db/schema.sql
```

### D. web `.env.local` (2-PC)

`sub1_side/web/.env.local` — `.env.local.example` 참고. 2-PC 는 둘 중:
- **공개(Cloudflare 단일오리진, 권장)**: `NEXT_PUBLIC_C2_API=https://<PUBLIC_HOST>`,
  `NEXT_PUBLIC_LICHTBLICK_URL=https://<foxglove 호스트>` — 같은 도메인이라
  CORS 무발생(`CLOUDFLARE.md`).
- **LAN 직결**: `NEXT_PUBLIC_C2_API=http://localhost:8000`(C2 PC 에서 브라우저
  띄울 때) 또는 `http://<SUB1_SIDE_IP>:8000`. `NEXT_PUBLIC_LICHTBLICK_URL`
  동일 호스트 `:8080`. ⚠ https 페이지에 http iframe = 혼합콘텐츠 차단 —
  스킴 통일. `NEXT_PUBLIC_*` 는 빌드/`next dev` 기동 시 주입 → 변경 시 재기동.

CORS: web_server 는 `config.WEB_ORIGINS`(기본 `localhost:3000`,`127.0.0.1:3000`)
만 허용. 다른 오리진에서 브라우저 접속 시 `C2_WEB_ORIGINS` env 로 추가.

### E. 통신 사전조건 (`FASTDDS.md` 참조)

- 런처가 `common/site.sh` 로 `RMW=rmw_fastrtps_cpp`·`ROS_DOMAIN_ID=130`·
  FastDDS 프로파일(`cobot3_fastdds_profile web`, site.env IP 자동치환) 설정.
- OS 커널 버퍼(`FASTDDS.md §4`) + 방화벽 C2 서브넷 허용(`§5`) 1회.

### F. 기동 (한 명령 — 역할 자동판별)

```bash
source ~/.bashrc          # bashrc 함수 사용(머신로컬, 리포 미포함)
cobot3-start_all_2        # 로컬 IP=SUB1_SIDE_IP → C2 역할 자동:
#   PG+schema · web_server(:8000, 재발행 OFF=정공) · web(:3000) ·
#   video_degrade · telemetry_bridge · foxglove_bridge(:8765) ·
#   Lichtblick(:8080) · cloudflared(PUBLIC_HOST 설정 시)
# 종료: cobot3-down_all_2     (C2 역할 = 위 전체 정리)
# ⚠ Isaac PC 에서도 cobot3-start_all_2 (MAIN 역할 = GUI Isaac) 실행
```

수동 기동(디버그)도 가능: `db→server/run.sh→web npm run dev`,
`run_degrade.sh`,`run_telemetry_bridge.sh`,`run_foxglove_bridge.sh`.

### G. 검증

브라우저 `http://localhost:3000`(또는 공개 URL) → `/` 작전콘솔, `/debug`
Foxglove. `curl -s localhost:8000/healthz`=200, `ros2 topic list` 에 Isaac
실토픽(`/robot/odom`,`/dsr01/joint_states`,`/c2/video/compressed`…),
ros_bridge HEALTH `rx` 가 0→증가(정공 성립). `X-API-KEY` 는 CommandBar
입력 시 localStorage 저장(서버 `ISAAC_SIM_API_KEY` 와 일치해야 변경계열 동작).

## Main PC 와의 계약 (토픽/서비스)

| 방향 | 토픽/서비스 | 타입 |
|---|---|---|
| ← | `/robot/state` | std_msgs/String (JSON) |
| ← | `/robot/gps` | sensor_msgs/NavSatFix |
| ← | `/robot/odom` | nav_msgs/Odometry |
| ← | `/dsr01/joint_states` | sensor_msgs/JointState |
| ← | `/robot/leg_joint_states` | sensor_msgs/JointState |
| ← | `/rosout` (level≥30) | rcl_interfaces/Log |
| ← | `/c2/video/compressed` | sensor_msgs/CompressedImage |
| → | `/robot/nav/goal` | geometry_msgs/PoseStamped |
| → | `/robot/speaker/audio` | std_msgs/String (JSON) |
| → | `/robot/weapon/fire` (srv) | std_srvs/Trigger (message="hit;dist") |

> 설계 문서는 `/robot/state`·`/robot/speaker/audio` 를 커스텀 msg 로 명시했으나,
> C2 를 독립 기동 가능하게 하기 위해 **std_msgs/String + JSON** 인터페이스로
> 구현했다(의도된 결정). 커스텀 msg 패키지 도입 시 `ros_bridge.py` 만 교체.

## UI (전술 작전 콘솔 — 데이터 우선순위 기반 재구성)

담당자의 실시간 판단 루프("위협 있나 → 어디 → 대응 가능한가 → 교전")에 맞춰
실제 수신 데이터를 운영 우선도로 재배치. 관절 텔레메트리(엔지니어링)는 강등.

- **ThreatBar** (1순위): detection 이벤트 기반 SECURE ↔ CONTACT. 접촉 시
  전역 경보모드(`.alert-active`)로 UI 강조 + 마지막 탐지 경과시간
- **ReadinessStrip** (2순위): MODE·BATTERY·LINK·WAYPOINT·GPS 컴팩트 타일
- **VideoWall**: WebRTC 영상(MJPEG 폴백) + HUD 레티클(접촉 시 적색 +
  TARGET ACQUIRED)
- **ContactsPanel**: 실시간 탐지 접촉 목록(클래스·신뢰도 바·시각)
- **MapTrack**: ODOM 궤적 + 링 그리드, 클릭=목표지정 / 더블클릭=GOTO
- **EngagementConsole**: 교전 절차순(확성기 경고 → ARM → FIRE 확인모달),
  접촉 시 강조, X-API-KEY 설정
- **OpsLedger**: 탐지·사격·rosout WARN 을 시간순 **단일 작전 원장**으로 통합
- **DiagnosticsStrip**: Spot arm0 q[*]·Spot leg q[*] — 접이식 슬림(평소 접힘)

미학: 다크 인광-그린 전술 콘솔, Chakra Petch / JetBrains Mono, HUD 코너
브래킷·스캔라인, 접촉 시 전역 적색 경보 전환.
