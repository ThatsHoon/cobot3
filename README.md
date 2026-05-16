# cobot3 — GP 경계근무 4족보행 + m0609 로봇 시스템

Isaac Sim 시뮬레이션 안에서 **ANYmal-C 4족 로봇(번들 RL 보행 정책)** 등에
**Doosan m0609 6축 팔**을 결합하고, m0609 `link_6` 플랜지의 **RealSense RGB-D**
영상을 별도 PC의 **지휘통제실(C2) 웹 UI**로 실시간 송출·조작하는 프로젝트.

설계 원본: [`dev-docs/gp-quadruped-system-design.md`](dev-docs/gp-quadruped-system-design.md)

---

## 적정 클론 위치 ⚠ 중요

스크립트·런처·`~/.bashrc` 함수가 **절대경로**를 사용하므로 반드시 아래 경로에
클론한다(다른 곳이면 `main_side/run_*.sh`, `sub1_side/server/run.sh`,
`~/.bashrc` 의 `cobot3-cobot3_web-restart_full` 함수의 경로를 수정해야 함):

```bash
git clone https://github.com/ThatsHoon/cobot3.git \
  /home/rokey/dev_ws/isaac_sim/cobot3
```

전제: Isaac Sim 5.1 (`~/dev_ws/isaac_sim/isaacsim`), ROS 2 Humble,
PostgreSQL, Node 20, `RMW_IMPLEMENTATION=rmw_cyclonedds_cpp`(Isaac↔C2 공통).

---

## 폴더 구조 개요

```
cobot3/
├── dev-docs/                 설계 문서
│   └── gp-quadruped-system-design.md   권위 설계서(S1~S7, P0~P4)
│
├── scenes/                   Isaac 씬 빌드 모듈(절차적 지형/로봇/OG)
│   └── assets/               (gitignore) m0609 URDF→USD 임포트 산출 — 재생성됨
│
├── main_side/                ★ 시뮬레이터 PC 측 (Isaac Sim 구동 PC)
│   ├── camera_publisher.py   standalone: 씬 로드 + RealSense OG + /cam/realsense/rgb 발행
│   ├── run_camera_pub.sh     위 실행 런처(CycloneDDS, python.sh)
│   ├── video_degrade_node.py /cam/realsense/rgb → 5fps·640×360·JPEG q50 → /c2/video/compressed
│   └── run_degrade.sh        degrade 노드 런처
│
└── sub1_side/                ★ 지휘통제실(C2) PC 측 (시뮬과 별도 PC)
    ├── db/schema.sql         로컬 PostgreSQL 스키마(영상 외 전 데이터)
    ├── server/               FastAPI + rclpy + aiortc(WebRTC) + asyncpg + YOLO
    │   ├── app.py            REST + WS /events + /c2/webrtc/offer + MJPEG 폴백
    │   ├── ros_bridge.py     ROS2 다운/업링크 + 진단(WS diag)
    │   ├── video_*/db_writer/yolo_infer/config.py
    │   ├── run.sh            web_server 런처
    │   └── requirements.txt  (.venv 는 gitignore — 재설치)
    └── web/                  Next.js 14 전술 작전 콘솔 UI (node_modules gitignore)
        ├── app/  components/  lib/
        └── package.json
```

`main_side` = Isaac Sim 이 도는 PC, `sub1_side` = 지휘통제실 별도 PC.
둘은 ROS 2 (`ROS_DOMAIN_ID=130`, CycloneDDS, LAN)로 연결된다.

---

## 빠른 실행

### 1) 시뮬레이터 PC (`main_side`)
```bash
# RealSense 영상 발행 (Isaac standalone, headless+render)
~/dev_ws/isaac_sim/cobot3/main_side/run_camera_pub.sh
```

### 2) 지휘통제실 PC (`sub1_side`)
최초 1회 의존성:
```bash
cd sub1_side/server && python3 -m venv --system-site-packages .venv \
  && ./.venv/bin/pip install -r requirements.txt
cd ../web && npm install
psql -d cobot3 -f ../db/schema.sql
```
기동(웹서버+웹+DB+degrade 일괄 — `~/.bashrc` 함수):
```bash
cobot3-cobot3_web-restart_full
```
브라우저 → `http://localhost:3000` (영상벽=WebRTC, 상태/맵/로그/교전 콘솔)

---

## 데이터 경로

```
Isaac OG /cam/realsense/rgb
  → video_degrade(5fps·640×360·q50) → /c2/video/compressed
  → web_server(aiortc) → WebRTC → 브라우저 영상벽
```
영상 외 전 데이터(GPS·상태·joint·rosout WARN·탐지·사격)는 로컬 PostgreSQL 적재.
영상 프레임은 DB 저장하지 않음(전송 전용).

## 디버깅

모든 통신 노드는 기동 시 **ENV 자가점검**(`ROS_DOMAIN_ID`/`RMW_IMPLEMENTATION`),
**5초 주기 헬스 카운터**(수신/발행·publisher 수·원인 힌트)를 출력하고,
web_server 는 진단을 WS `type:"diag"` 로 송출 → 브라우저 콘솔 `[C2/...]` 접두사
로 확인. 다단 파이프라인 단절은 위→아래(`ros2 topic info` Publisher count
기준)로 진단.

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)
