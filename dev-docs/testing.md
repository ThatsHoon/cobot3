# 통합 테스트 가이드

DMZ Sentry 기능 통합(2026-05-20, CHANGELOG 참조)의 동작을 검증하는 자동/수동 테스트 모음.

소스: `tests/` (cobot3 루트)
실행기: `tests/run_all.sh`
반복 로그: `tests/iteration_log.md` (라이브 검증 시 발견·수정한 버그 누적)

---

## 1. 테스트 구조

```
cobot3/tests/
├── conftest.py                       # pytest fixture (mock yolo box, fake bgr 등)
├── _ros_helpers.py                   # subprocess spawn + spin_for 헬퍼 (ROS_DOMAIN_ID=199 격리)
├── test_unit_yolo_alert.py           # T2 단위 (8)
├── test_unit_patrol_state.py         # T3 단위 (13)
├── test_unit_safety_filter.py        # T4 단위 (7)
├── test_unit_map_bake.py             # T1 단위 (4)
├── test_ros_world_odom_tf.py         # T10 ROS round-trip (1)
├── test_ros_landmarks.py             # T9 ROS round-trip + latched (2)
├── test_ros_safety_filter.py         # T4 ROS round-trip (3)
├── test_ros_alerts.py                # T2/T3 alerts→ALERT_STOP (2)
├── test_db_schema.py                 # T11 DB 컬럼·INSERT (5)
├── test_api_endpoints.py             # T11 FastAPI 엔드포인트 (9, venv 필요)
├── run_all.sh                        # pytest + e2e 안내 진입점
└── iteration_log.md                  # 반복 검증·버그 수정 누적 로그
```

총 **54 자동 테스트** + **e2e 수동 시나리오**.

## 2. 실행

### 한 번에 (시스템 python 45 + venv 9)
```bash
bash tests/run_all.sh
```

### 개별

**단위 + ROS round-trip + DB** (시스템 python):
```bash
source /opt/ros/humble/setup.bash
python3 -m pytest tests/ --ignore=tests/test_api_endpoints.py -v
```

**FastAPI** (sub1_side venv 안에서):
```bash
sub1_side/server/.venv/bin/python -m pytest tests/test_api_endpoints.py -v
```

## 3. 사전조건

| 항목 | 검증 명령 | 미충족 시 |
|---|---|---|
| pytest, rclpy | `python3 -c "import pytest, rclpy"` | `apt install python3-pytest`, ROS humble |
| PostgreSQL | `pg_isready` | `sudo systemctl start postgresql` |
| DB 스키마 | `psql -d cobot3 -c "\d alerts"` | `psql -d cobot3 -f sub1_side/db/schema.sql` |
| sub1_side venv | `sub1_side/server/.venv/bin/python -c "import fastapi"` | `cd sub1_side/server && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt httpx pytest` |
| YOLO 모델 (선택) | `python3 -c "import ultralytics"` | 미설치 OK — 단위는 mock, 통합은 graceful skip |

## 4. ROS 도메인 격리

ROS round-trip 테스트는 `ROS_DOMAIN_ID=199` + `ROS_LOCALHOST_ONLY=1` 로 격리(`tests/_ros_helpers.py`).
운영 도메인(130, FastDDS UDP-only) 과 분리되어 Isaac/Nav2 가 켜져 있어도 충돌 없음.

## 5. 테스트 ID ↔ 기능 매핑

implementation_summary.md 의 핵심 기능별:

| ID | 기능 | 테스트 파일 |
|---|---|---|
| T1 | gp_static 점유격자 | `test_unit_map_bake.py` |
| T2 | YOLO alert 정책 | `test_unit_yolo_alert.py`, `test_ros_alerts.py` |
| T3 | nav2_patrol 상태머신 | `test_unit_patrol_state.py`, `test_ros_alerts.py` |
| T4 | cmd_vel safety filter | `test_unit_safety_filter.py`, `test_ros_safety_filter.py` |
| T5 | 검사 카메라 명령 | (Isaac Kit 의존 — e2e 수동) |
| T6 | 웹 전술 지도 | `next build` (CI) |
| T8 | Nav2 launch lifecycle | e2e: `ros2 lifecycle get /bt_navigator` |
| T9 | /scene/landmarks latched | `test_ros_landmarks.py` |
| T10 | world→odom→Go2 TF | `test_ros_world_odom_tf.py` + e2e `tf2_echo` |
| T11 | DB + FastAPI | `test_db_schema.py`, `test_api_endpoints.py` |
| T12 | 단일 명령 e2e | `tests/iteration_log.md § 라이브 검증` |
| T13 | DMZ_Zone spawn + 보행 e2e | `tests/test_e2e_dmz_zone.md` (수동, `GP_GO2_SPAWN_ZONE=dmz` + Nav2 map 교체) |
| T14 | YOLO 동물 클래스 + animal_alerts | `test_unit_yolo_animal_classes.py` (4), `test_ros_animal_alerts.py` (2) |
| T15 | DMZ_Zone landmarks 분기 | `test_unit_dmz_zone_landmarks.py` (3) |

## 6. e2e 수동 시나리오 (T12)

`tests/iteration_log.md § 라이브 검증` 의 실제 명령 로그 참조. 요약:

```bash
isaac-clear
cobot3-start_all                              # Main 역할
( cd sub1_side/server && bash run_nav2.sh & )            # C2 Nav2
( cd sub1_side/server && python3 cmd_vel_safety_filter.py & )
( cd sub1_side/server && python3 nav2_patrol.py & )

# 30초 대기 후 — Nav2 lifecycle active
ros2 lifecycle get /bt_navigator              # → "active [3]"

# 시나리오 A — mission_command sortie → mode=PATROL
ros2 topic pub --once /mission_command std_msgs/String "{data: 'sortie'}"
ros2 topic echo --once --field data /patrol_state          # mode: PATROL

# 시나리오 B — alert → ALERT_STOP → (6s 후 자동 PATROL)
ros2 topic pub --once /alerts std_msgs/String "{data: '{\"level\":\"ALERT\",...}'}"

# 시나리오 C — 검사 카메라
ros2 topic pub --once /robot/inspect/command std_msgs/String "{data: '{\"pan\":0.5,\"absolute\":true}'}"
cat /tmp/cobot3_inspect_cmd.json
grep "\[inspect\]" /tmp/cobot3_isaac_gui.console.log | tail

# FastAPI (API_KEY 필요)
curl -X POST -H "X-API-Key: $ISAAC_SIM_API_KEY" -d '{"command":"home"}' \
  -H "Content-Type: application/json" http://localhost:8000/missions/command
```

## 7. 통합 검증으로 발견·수정한 버그

`tests/iteration_log.md § 반복 중 발견·수정한 버그` 에 누적:

- **B1** cmd_vel safety filter NaN 가드 누설 → clamp 전으로 이동
- **B2** OG `ROS2SubscribeString` 미등록 → 사이드카 `inspect_relay.py` + file mailbox
- **B3** OG `/tf` BEST_EFFORT QoS → Nav2 TransformListener 가 RELIABLE 요구 → `_REL_QOS` 변경
- **B4** OG TF 와 OdoPub frame 이름 불일치 (`Go2` vs `base_link`) → `Go2` 로 통일
- **B5** patrol fence waypoint 가 gp_scene `/World/Fence/*` 의 부적절 좌표(-208,-208,z=118) 를 잡아 plan 실패 → `_on_landmarks` 에서 fence 무시 (cube↔cone 만 patrol)

운영 시 동일 증상이 보이면 `dev-docs/ops.md § 5 트러블슈팅` 표 참조.

## 8. CI/회귀 회피 권장

- 코드 변경 후 `bash tests/run_all.sh` 실행 → 신규 회귀가 56 테스트 중 어디서 깨지는지 확인.
- 새 ROS 토픽/엔드포인트 추가 시 그에 맞는 `test_ros_*` 또는 `test_api_endpoints.py` 케이스 보강.
- 새 발견 버그는 `tests/iteration_log.md § 반복 중 발견·수정한 버그` 에 추가 후 동일 표를 `ops.md` 트러블슈팅에도 미러링.
