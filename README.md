# cobot3 — GP 경계근무 4족보행(Spot+팔) 로봇 시스템

Isaac Sim 안에서 spot_with_arm(4족+팔)을 구동하고, 카메라 영상/텔레메트리를
별도 PC의 지휘통제실(C2) 웹 UI로 실시간 송출·조작하는 프로젝트.

---

## 폴더 구조

```
cobot3/
├── common/       2-PC 공통 설정 (site.env · site.sh)
│                 main_side/sub1_side 어느 쪽에도 속하지 않는
│                 IP·FastDDS 단일소스. 배포지 바뀌면 site.env만 수정.
│
├── main_side/    Isaac Sim PC 측
│                 카메라/텔레메트리 발행, SpotController(RL 보행),
│                 씬·에셋, 런처 스크립트, FastDDS 설정
│
├── sub1_side/    지휘통제실(C2) PC 측
│                 FastAPI 서버, Next.js UI, PostgreSQL 스키마,
│                 ROS2 구독·cmd_vel 발행(ros_bridge), Foxglove 런북
│
└── dev-docs/     설계·환경·트러블슈팅 문서
                  project_requirments.md — 개발환경·기동절차·트러블슈팅 ★먼저 읽기
                  gp-quadruped-system-design.md — 권위 설계서
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
echo 'export FASTRTPS_DEFAULT_PROFILES_FILE=/home/rokey/dev_ws/isaac_sim/cobot3/main_side/fastdds_no_shm.xml' >> ~/.bashrc
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

# Next.js UI
cd ../web && npm install

# DB 스키마 (멱등)
createdb cobot3 2>/dev/null
psql -d cobot3 -f ../db/schema.sql
```

### 실행

**Isaac PC (main_side)**
```bash
# GUI 모드 (모니터 있을 때)
~/dev_ws/isaac_sim/cobot3/main_side/run_camera_pub_gui.sh

# headless 모드
~/dev_ws/isaac_sim/cobot3/main_side/run_camera_pub.sh
```

**C2 PC (sub1_side)**
```bash
# 웹서버+UI+DB 일괄 기동 (~/.bashrc 함수)
cobot3-cobot3_web-restart_full

# 브라우저
# http://localhost:3000        — 전술 콘솔 UI
# http://localhost:3000/debug  — Foxglove 텔레메트리 뷰어
```

상세 트러블슈팅: `dev-docs/project_requirments.md`
