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

## 기동 (C2 PC 에서)

```bash
# 1) DB
createdb cobot3 2>/dev/null || true
psql -d cobot3 -f db/schema.sql

# 2) web_server (ROS 2 Humble 필요)
cd server
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
./run.sh                     # :8000  (ROS_DOMAIN_ID=130 자동)

# 3) web (다른 터미널)
cd web
cp .env.local.example .env.local   # 필요 시 NEXT_PUBLIC_C2_API 수정
npm install && npm run dev          # :3000
```

브라우저 → `http://localhost:3000`. `X-API-KEY` 는 CommandBar 입력칸에
넣으면 localStorage 에 저장된다(서버 `ISAAC_SIM_API_KEY` 와 일치해야 변경계열 동작).

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
- **DiagnosticsStrip**: m0609 q[6]·ANYmal q[12] — 접이식 슬림(평소 접힘)

미학: 다크 인광-그린 전술 콘솔, Chakra Petch / JetBrains Mono, HUD 코너
브래킷·스캔라인, 접촉 시 전역 적색 경보 전환.
