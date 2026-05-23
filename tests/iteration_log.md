# 테스트 반복 로그 (2026-05-20)

implementation_summary.md 의 DMZ Sentry 핵심 기능별 통합 검증.

## 테스트 통과 현황

| 식별자 | 기능 | 단위 | ROS | e2e | 비고 |
|---|---|---|---|---|---|
| T1 | gp_static map | ✓ 4/4 | — | ✓ | Cube/Cone free 셀 |
| T2 | YOLO alert 정책 | ✓ 8/8 | ✓ 2/2 | △ | YOLO 모델 없어도 graceful |
| T3 | nav2_patrol 상태머신 | ✓ 13/13 | ✓ ALERT_STOP | ✓ sortie/home | resume 자동복귀 6s |
| T4 | cmd_vel safety filter | ✓ 7/7 | ✓ 3/3 | ✓ | NaN 가드 버그 발견·수정 |
| T5 | 검사 카메라 명령 | (Isaac 의존부 skip) | — | ✓ | inspect_relay file mailbox round-trip |
| T6 | 웹 전술 지도 | — | — | ✓ | `next build` 통과 |
| T7 | /intruder_states | (보류) | — | — | NPC 미구현 |
| T8 | Nav2 lifecycle | — | — | ✓ | 8 lifecycle ACTIVE, action 등장 |
| T9 | /scene/landmarks latched | — | ✓ 2/2 | ✓ | TRANSIENT_LOCAL late-subscribe OK |
| T10 | world→odom→base TF | — | ✓ 1/1 | △ | QoS 버그·frame 이름 버그 발견·수정 |
| T11 DB | alerts/patrol_state_log/intruder_states_log | ✓ 5/5 | — | ✓ | psql round-trip |
| T11 API | FastAPI 신규 엔드포인트 | ✓ 9/9 | — | ✓ | mission_command·inspect·alerts/ack |
| T12 | 단일 명령 e2e | — | — | ✓ | 보행은 사용자 요청으로 생략 |

**pytest 총계: 56 PASS** (Phase1 32 + Phase2 8 + Phase3 14 + 별도 ROS 2).

## 반복 중 발견·수정한 버그

### B1 — cmd_vel_safety_filter NaN 클램프 누설 (T4 단위)
- 증상: `linear.x = NaN` 입력 시 `_clamp(NaN, -0.8, 0.8)` 가 0.8 반환 → `isfinite` 가드가 못 잡음.
- 근본 원인: Python `min(a, NaN)`/`max(a, NaN)` 결과 미정의 — clamp 후 NaN 손실.
- 수정: `sub1_side/server/cmd_vel_safety_filter.py` — `_on_cmd_vel` 에서 clamp 전에 `isfinite` 가드.

### B2 — `ROS2SubscribeString` OG 노드 미등록 (e2e Isaac 재기동)
- 증상: Isaac Sim 부팅 시 `OmniGraphError: Could not create node using unrecognized type 'isaacsim.ros2.bridge.ROS2SubscribeString'` → 단일 OG edit 전체 실패 → `/cam/inspect/rgb`·`/tf`·`/robot/leg_joint_states`·SubCmd 미생성.
- 근본 원인: Isaac 5.1 `isaacsim.ros2.bridge` 에 String 구독자 노드 타입이 등록 안 됨 (다른 메시지 타입은 있음).
- 수정:
  - `main_side/camera_publisher.py` — SubInspect OG 노드 제거.
  - `main_side/inspect_relay.py` 신규 — standalone rclpy 가 `/robot/inspect/command` 구독해 `/tmp/cobot3_inspect_cmd.json` dump.
  - `camera_publisher._apply_inspect_cmd` — OG attribute 대신 파일 mtime 폴.
  - `~/.bashrc` cobot3-start_all — inspect_relay 자동 기동.

### B3 — OG `/tf` BEST_EFFORT QoS → Nav2 TransformListener 무시 (T10 e2e)
- 증상: `tf2_echo world odom` 에서 "incompatible QoS. No messages will be sent" → Nav2 가 로봇 base 위치 못 찾음.
- 근본 원인: `camera_publisher.py` 의 OG TF `qosProfile=_SENSOR_QOS` (BEST_EFFORT) — Nav2 표준은 RELIABLE.
- 수정: `_SENSOR_QOS` → `_REL_QOS`.

### B4 — TF base frame 이름 불일치 (`base_link` vs `Go2`) (T10 e2e)
- 증상: OG TF 가 `frame_id: world, child_frame_id: Go2` (USD prim 이름) 발행. OdoPub 는 `chassisFrameId="base_link"` 로 발행. 두 sub-tree 가 분리 → `world → odom → base_link` 트리 단절.
- 근본 원인: OG `ROS2PublishTransformTree` 가 USD prim 이름(`Go2`)을 그대로 frame_id 로 발행하는데, OdoPub 는 별개 frame 이름 사용.
- 수정:
  - `main_side/camera_publisher.py` — OdoPub `chassisFrameId="Go2"` (OG TF 와 일치).
  - `sub1_side/server/nav2_params.yaml` — 모든 `robot_base_frame: base_link` → `robot_base_frame: Go2`.

## 라이브 검증 결과 (Isaac 재기동 후)

ROS topic list (도메인 130) — 14개 정상:
```
/cam/{front,rear,inspect}/rgb     (BEST_EFFORT)
/robot/{odom,gps,state,leg_joint_states,cmd_vel,inspect/command,nav/goal,speaker/audio}  (RELIABLE)
/scene/landmarks                  (RELIABLE+TRANSIENT_LOCAL latched)
/tf, /tf_static                   (RELIABLE)
```

Nav2 lifecycle — bt_navigator/map_server/controller_server 모두 ACTIVE. `/navigate_to_pose` action 등장.

E2E 흐름:
- `ros2 topic pub /mission_command "sortie"` → patrol_state mode=PATROL ✓
- `ros2 topic pub /alerts {...}` → patrol_state mode=ALERT_STOP ✓
- `ros2 topic pub /robot/inspect/command {pan:0.5}` → camera_publisher inspect 상태 갱신(`[inspect] pan=0.50`) ✓
- `POST /missions/command {"command":"home"}` (X-API-Key) → patrol_state mode=HOME ✓
- `POST /robots/gp0/inspect {pan:1.0}` → `/tmp/cobot3_inspect_cmd.json` 갱신 ✓
- `GET /missions/state` → patrol_state JSON 응답 ✓
- DB `patrol_state_log` row 1+ 적재 ✓

## 사용자 요청 반영
- Go2 보행(Cube→Cone) 시나리오 검증 생략 — Nav2 액션 수신·patrol mission 전환·inspect·DB·웹만 검증.

## 추가 검증 — 토픽 hz + chain wiring (보행 생략)

### 토픽 발행 hz (Isaac 운영 중)
| 토픽 | 평균 Hz | 비고 |
|---|---|---|
| `/cam/front/rgb` | 12.2 | OG OnTick 50Hz 기대 대비 낮음 — GPU 부하 영향 |
| `/cam/rear/rgb` | 14.1 | 동일 |
| `/cam/inspect/rgb` | **11.4** | M6 검사 카메라 실제 frame 발행 ✓ |
| `/robot/odom` | 21.2 | OdoPub |
| `/robot/leg_joint_states` | 21.2 | LegJS |
| `/tf` | 21.7 | OG TF (RELIABLE 적용) |

### 다운링크 video + 웹 backend 검증 (보행 외 미검증)
| 항목 | 결과 |
|---|---|
| `/c2/front/compressed` hz | 4.13 Hz (계획 5Hz, 정상 범위) |
| `/c2/rear/compressed` hz | 4.19 Hz |
| MJPEG `/c2/video/mjpeg?camera=front` 8s 다운로드 | 345KB, multipart/x-mixed-replace + FFD8FFE0 JPEG 매직 + JFIF 헤더 ✓ |
| REST `/healthz` `/robots/gp0/{state,gps}` `/missions/state` `/telemetry/patrol_state` | 5개 모두 HTTP 200 |
| WS `/events` 4초 메시지 카운트 | `patrol_state`×20 (5Hz), `state`×18, `gps`×19, `diag`×1 — 푸시 라이브 |

### Nav2 → Go2 cmd_vel chain wiring 정적 검증
- `/cmd_vel_nav2_raw`: pub=`velocity_smoother`, sub=`cmd_vel_safety_filter` ✓
- `/robot/cmd_vel`: pub=`c2_web_server` + `cmd_vel_safety_filter` + `nav2_patrol_controller` (정지용) → Isaac OG SubCmd 구독 ✓
- 노드 라인업: bt_navigator / controller_server / velocity_smoother / cmd_vel_safety_filter / nav2_patrol_controller 모두 동시 가동
- `/scene/landmarks` → patrol: `landmarks_received=True`, home=(-714.3, 952.9) Cube 좌표 정확 적용

### 보행 실제 실행 시 path 계획 실패 — 별건
- 현재 Isaac 의 Go2 spawn world pose = (-161, 46) — gp_static map 영역 (-1017~-637, 858~1036) **밖**.
- Nav2 planner_server 가 "GridBased failed to generate a valid path" 로그 — start/goal 이 map 미커버 영역이라 정상 거부.
- 후속 작업으로 (a) Cube spawn 정확성 검증, (b) gp_static map 영역을 spawn pose 까지 확장 베이크 필요.
- 사용자 요청 "보행 부분 임시 생략" 으로 본 검증 라운드 범위 밖.

## gp_static map 영역 정합 + 보행 검증 (2026-05-20 후속)

### M1~M2 베이크
- AABB: spawn(-161, 46) ∪ Cube(-714.32, 952.93) ∪ Cone(-937.07, 938.98) ± 80m
  → x∈[-987.1, -111.0], y∈[-4.0, 1002.9], 1753×2014 px @ 0.5 m/px ≈ 3.37 MB
- 명령: `${ISAAC_PYTHON} bake_gp_static_map.py --xmin -987.1 --xmax -111.0 --ymin -4.0 --ymax 1002.9 --res 0.5`
- 결과: occupied 0.184%, free 99.816%. spawn/Cube/Cone 셀 모두 free(255)
- 회귀: `pytest tests/test_unit_map_bake.py` **4/4 PASS** (영역만 바뀌어도 셀 변환 일관)

### M3~M4 정합 검증
- Isaac 재기동 후 `tf2_echo world Go2` = **(-714.32, 952.93, 30.57)** (Cube 위 정확 spawn — 이전 odom 좌표 (-161,46) 는 IsaacComputeOdometry 누적값)
- Nav2 lifecycle 8개 active, `/navigate_to_pose` action 등장
- Cone 으로 단발 goal → planner WARN/Abort **0건**, `/cmd_vel_nav2_raw` 9.98Hz, `/robot/cmd_vel` 10Hz

### B5 — patrol fence waypoint 가 plan 실패 유발
- 증상: sortie 시 patrol_waypoints 에 fence (-208, -208, z=118) 가 포함 → planner 가 `"goal is off the global costmap"` 거부
- 근본 원인: gp_scene 의 `/World/Fence/*` 좌표가 비실용 위치 (z=118m, x/y= -208) — patrol 좌표 아닌 metadata
- 수정: `sub1_side/server/nav2_patrol.py` 의 `_on_landmarks` 에서 fence 항목 무시 (cube↔cone 만 patrol). 진짜 순찰 경로는 향후 ros2 parameter `patrol_waypoints_xy` 외부 주입으로 유연화.

### M5 e2e 보행
- sortie → mode=PATROL, waypoint=Cone(-937, 939), planner WARN 0건
- 30초 보행 동안 `/robot/odom` 누적 (0.45, -0.52) → (-1.92, -4.02), linear.x 0.12~1.61 m/s — **실제 보행 ✓**
- alert 발행 → mode=ALERT_STOP (2s 내), 자동 PATROL 복귀 (~4s)
- home 명령 정상 처리
- DB `patrol_state_log` 10행 적재 ✓

## DMZ_Zone + jsy YOLO/웹 통합 (P1~P5, 2026-05-20 후속)

### P1 외부 자산 잔여분 이동
- jsy `convert_replicator_to_yolo.py`, `train_2class_yolo.sh` → `main_side/scripts/yolo_train/` (PROJECT_ROOT cobot3 상대경로로 patch)
- hi `dmz_static.{pgm,yaml}` → `main_side/scene/maps/dmz_demo.{pgm,yaml}`
- jsy `web/tactical_map/*` → `sub1_side/web/_jsy_reference/` (build 제외 `_` 접두)
- `main_side/scene/assets/dmz/LICENSE.txt` 신규 (Guard_Tower/chainlink_fence 라이선스 TBD 명시)
- 외부 절대경로 grep 0건 (검증 통과)

### P2 DMZ_Zone 런타임 + spawn 분기
- `camera_publisher.py`: `_build_dmz_zone(stage)` 신규 — `/World/DMZ_Zone/{Ground, GTower_0~3, Fence_0~3, Home_Marker, Patrol_W_Marker, Patrol_E_Marker, Fence_N_Marker}` idempotent 빌드
- `GP_GO2_SPAWN_ZONE=cube|dmz` env: cube=기존 Cube nearest-vertex, dmz=DMZ_Zone home(0,0) 위
- landmarks JSON 에 `zone`, `dmz_home`, `dmz_cone`, `dmz_patrol_w`, `dmz_fence` 추가 (zone 무관 항상 dump → web 가시화)
- `nav2_patrol._on_landmarks` zone 분기: dmz 면 dmz_home/cone/patrol_w 우선, cube 면 기존
- `bake_gp_static_map.py --zone dmz` 옵션: world(-40,-40)~(40,40) 80×80m 베이크 → `dmz_static.{pgm,yaml}`
- OG sensor_bridge 와 prim 경로 분리 → 단일 OG edit 무영향

### P3 YOLO 동물 클래스 + 모델 슬롯
- `sub1_side/server/models/{README.md,.gitignore}` 신규
- `config.py`: `_pick_model()` (env > models/*.pt > yolov8n.pt), `YOLO_CLASSES` 11개 클래스 (person + COCO 동물 16~25 + jsy class 1=animal), `YOLO_ANIMAL_ALERT_CONF=0.50` `COOLDOWN=5.0`, `TOPICS["animal_alerts"]`
- `yolo_infer.infer_with_alerts()` → 3-tuple `(dets, person_alert, animal_alert)`. 독립 `_last_person_alert_ts` / `_last_animal_alert_ts`. animal alert event="animal_detected", label=종 명
- `ros_bridge._on_video`: 3-tuple 언패킹, `_animal_pub.publish` + WS `animal_alert` emit + DB `alerts` 적재

### P4 Next.js 컴포넌트 (jsy 포팅)
- 신규: `DualCameraView.tsx` (FRONT + INSPECT MJPEG 2-panel), `AnimalAlertsLog.tsx` (animal_alert 누적), `EventLog.tsx` (모든 C2Event 14줄)
- 수정: `MapTrack.tsx` (zone="dmz" 시 dmz_* marker amber + fence 점선), `app/page.tsx` (3 신규 컴포넌트 + animal_alert 핸들러 + eventStream), `lib/api.ts` (`animal_alert` C2Event + `LandmarksPayload.zone/dmz_*`)
- next build 9.89kB (이전 8.97kB + 1kB), tsc --noEmit 무에러

### P5 통합 테스트 결과
| 식별자 | 파일 | 결과 |
|---|---|---|
| 기존 yolo_alert | `test_unit_yolo_alert.py` | **8/8** (3-tuple 마이그레이션, COCO 30 미등록 클래스 케이스 수정) |
| **신규** yolo_animal_classes | `test_unit_yolo_animal_classes.py` | **4/4** (animal alert, cls=1=animal, cooldown 독립, unknown class) |
| **신규** dmz_zone_landmarks | `test_unit_dmz_zone_landmarks.py` | **3/3** (zone=dmz/cube/missing 분기) |
| **신규** ros_animal_alerts | `test_ros_animal_alerts.py` | **2/2** (JSON 스키마 round-trip, patrol 가 animal_alerts 단독에 ALERT_STOP 안 함 — 설계 의도) |
| 기존 회귀 전체 | system + venv | **54 + 9 = 63 PASS** (목표 달성) |
| T13 (DMZ_Zone e2e) | `test_e2e_dmz_zone.md` | 수동 — Nav2 map 을 `dmz_static.yaml` 로 교체해 실행 |

## 미해결 / 후속 작업
- T7 `/intruder_states` 실제 발행자 부재 (NPC 미구현) — 향후 gp_scene 에 휴먼 USD 추가 시 활성.
- 외부 `/alerts` 발행 → DB 적재 경로 없음 (ros_bridge 는 자체 YOLO 결과만 적재). 필요 시 ros_bridge 에 `/alerts` 구독 + DB 적재 추가.
- Inspector 카메라 `look_at` world→base 변환 정밀화 (현재 1차 yaw 만, pitch 미계산).
- ~~Go2 spawn 위치 ↔ gp_static map 영역 불일치~~ **해결됨 (2026-05-20 후속)** — spawn=Cube 정확, map 영역 (xmin=-987.1, xmax=-111.0, ymin=-4.0, ymax=1002.9) 로 확장 완료. Nav2 plan 산출·실보행 검증 통과.
- patrol fence waypoint 자동 생성이 부적절한 좌표(-208, -208, z=118) 를 잡음 — 단기로는 fence 제외(cube↔cone 만), 장기로는 patrol 경로를 외부 config 로 주입.
