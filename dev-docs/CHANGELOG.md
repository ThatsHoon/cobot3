# CHANGELOG

이 파일은 cobot3 시스템의 주요 변경사항을 날짜 역순으로 기록합니다.
각 항목에는 변경된 파일, 변경 내용, 영향을 받는 컴포넌트를 기술합니다.

---

## 2026-05-20

### DMZ Sentry 기능 통합 (Nav2 자율 순찰 + YOLO alert + 검사 카메라 + 침입자 GT)

**변경 파일 (예고 — 마일스톤별 순차 적용):**

- `main_side/camera_publisher.py` (수정) — 단일 OG edit 안에 검사 카메라
  RGB+camera_info, `/robot/inspect/command` 구독, `/intruder_states` 발행,
  `/scene/landmarks` latched 1회 발행 추가. 헬퍼 `_spawn_intruders()`,
  `_publish_landmarks()` 신규.
- `main_side/bake_gp_static_map.py` (신규) — standalone Kit Python, gp_scene
  AABB top-down PhysX raycast 로 0.5 m/px 점유격자 베이크.
- `main_side/world_odom_tf_pub.py` (신규) — standalone rclpy,
  `world→odom` identity StaticTransformBroadcaster (Nav2 TF 트리 필수).
- `main_side/scene/maps/gp_static.{pgm,yaml}` (신규 산출물) — Nav2 정적 맵.
- `sub1_side/server/nav2_patrol.py` (신규) — mission_command 상태머신,
  /scene/landmarks 1회 수신 → waypoint 구성, alert 6s hold 후 자동 resume.
- `sub1_side/server/cmd_vel_safety_filter.py` (신규) — Nav2 출력
  `/cmd_vel_nav2_raw` → `/robot/cmd_vel` drive/turn 모드 안전 필터.
- `sub1_side/server/nav2_params.yaml`, `nav2_bringup.launch.py`,
  `run_nav2.sh` (신규) — standalone Nav2 stack (map_server, planner,
  controller, BT navigator, velocity_smoother). frame=world,
  odom_topic=/robot/odom, robot_radius=0.35 (Go2).
- `sub1_side/server/yolo_infer.py` (수정) — alert_conf=0.55, cooldown=3.0s
  상수 + `infer_with_alerts()` 반환. 신규 standalone YOLO 노드는 만들지 않음
  (기존 in-process 추론 재사용 — 게이트 결정).
- `sub1_side/server/ros_bridge.py` (수정) — `/alerts`·`/detections_text`
  String publisher, `_on_video` 콜백에서 정책 통과 시 발행 + WS `alert`
  emit, `/intruder_states`·`/patrol_state`·`/scene/landmarks` 구독.
- `sub1_side/server/app.py` (수정) — `POST /missions/command`,
  `POST /robots/{rid}/inspect` 엔드포인트 + `require_key` 가드.
- `sub1_side/server/config.py` (수정) — `TOPICS` 8개 신규 키
  (mission_cmd/patrol_state/alerts/detections/intruders/landmarks/
  inspect_cmd/cmd_nav_raw).
- `sub1_side/db/schema.sql` (수정) — `alerts`, `patrol_state_log`,
  `intruder_states_log` 3개 테이블 신규.
- `sub1_side/server/db_writer.py` (수정) — `COLUMNS` 확장 + intruder 1Hz
  다운샘플 핸들러.
- `sub1_side/web/lib/api.ts` (수정) — `C2Event` 유니온에 alert/patrol_state/
  intruder_state/landmarks 추가.
- `sub1_side/web/components/MapTrack.tsx` (수정) — landmarks/intruders/
  goalPending props + alert overlay, gp_scene EXTENT 보정.
- `sub1_side/web/components/EngagementConsole.tsx` (수정) — sortie/home/
  stop/resume 버튼 그룹.
- `sub1_side/web/components/{PatrolControls,InspectorCameraPanel,AlertsLog}.tsx`
  (신규) — patrol 제어/검사 카메라 pan·tilt·zoom·look_at/alert 스트림.
- `sub1_side/web/app/page.tsx` (수정) — onEvent switch 확장, 신규 컴포넌트
  마운트.
- `~/.bashrc` 의 `cobot3-start_all` (수정) — Nav2 launch, nav2_patrol,
  cmd_vel_safety_filter, world_odom_tf_pub 자동 기동 추가.

**핵심 설계 게이트 (M0 확정):**

1. ALERT_STOP 자동 resume — 6초 hold 후 이전 모드(PATROL/HOME) 자동 복귀.
2. YOLO alert — 기존 `yolo_infer.py` in-process 추론에 정책(`alert_conf`,
   `cooldown`) 적용. DMZ 원본 standalone YOLO 노드는 도입하지 않음 (중복).
3. `world→odom` static TF 발행 주체 — Main 의 `world_odom_tf_pub.py`
   (camera_publisher 의 OG TF 가 `odom→base_link` 만 발행하므로 보강 필수).
4. waypoint 출처 — 코드 하드코딩 대신 씬의 `/World/Cube`,`/World/Cone`,
   `/World/Fence/*` 좌표를 Main 이 `/scene/landmarks` (RELIABLE +
   TRANSIENT_LOCAL latched) 로 1회 발행, C2 가 1회 수신.
5. 검사 카메라 명령 토픽 prefix — 데이터가 아닌 로봇 명령이므로
   `/cam/inspect/command` 가 아니라 `/robot/inspect/command`.
6. Nav2 `odom_topic` — cobot3 기존 `/robot/odom` 으로 통일.
7. Inspector 카메라 depth/PCL — Isaac 5.1 제한으로 RGB+camera_info 만 발행.
8. 폴더 평탄화 — `sub1_side/server/` 안에 patrol/safety/nav2 파일 직접
   배치 (별도 `nav2/` 디렉토리 신설 금지).

**신규 토픽 (10개):**

| 토픽 | 타입 | QoS | 방향 |
|---|---|---|---|
| `/cam/inspect/rgb`, `/cam/inspect/camera_info` | Image / CameraInfo | BEST_EFFORT | Main→ |
| `/robot/inspect/command` | String JSON | RELIABLE | C2→Main |
| `/intruder_states` | String JSON | RELIABLE | Main→C2 |
| `/scene/landmarks` | String JSON | RELIABLE + TRANSIENT_LOCAL | Main→C2 (latched) |
| `/alerts` | String JSON | RELIABLE | C2 내부+Web |
| `/detections_text` | String JSON | RELIABLE | C2 내부+Web |
| `/mission_command` | String | RELIABLE | Web/FastAPI→C2 |
| `/patrol_state` | String JSON | RELIABLE | C2→Web |
| `/navigate_to_pose` | nav2_msgs Action | — | Nav2 |
| `/cmd_vel_nav2_raw` | Twist | RELIABLE | Nav2→safety filter |

**신규 FastAPI 엔드포인트 (모두 `require_key`):**

- `POST /missions/command` — body `{"command":"sortie|home|stop|resume|idle"}`
- `POST /robots/{rid}/inspect` — body `{"pan":?,"tilt":?,"zoom":?,"look_at":[x,y,z]?}`
- WS `/events` 추가 타입: `alert`, `patrol_state`, `intruder_state`, `landmarks`.

**DB 신규 테이블:**

- `alerts(id, robot_id, ts, level, event, confidence, bbox_xyxy JSONB, count, ack)`
- `patrol_state_log(id, robot_id, ts, mode, current_waypoint, pose_x, pose_y, pose_yaw)`
- `intruder_states_log(id, ts, intruder_id, x, y, z, label)` — 1Hz 다운샘플.

**삭제 / 미도입:**

- DMZ 원본 `inspection_bridge.py` — 2-PC 환경 `/tmp` 파일 mailbox 무의미 → 도입 안 함.
- DMZ 원본 standalone `yolo_person_detector.py` — 기존 `yolo_infer.py` 확장으로 대체.
- DMZ 원본 ANYmal 의존 코드(`anymal_gp_terrain.py` 의 정책·지형 빌더) — 미이식.

**의존 마일스톤 그래프:**

```
M0(게이트) → M1(map) → M2(Nav2) → M3(safety+Go2) → M4(patrol) → M7(web) → M9(start_all)
                            ├─ M5(yolo alert)  ─┤
                            ├─ M6(inspect+intr) ┤
                            └─ M8(DB schema)   ─┘
```

상세 계획: `~/.claude/plans/staged-marinating-spring.md`.

### DMZ Sentry 통합 검증 + 4건 버그 수정

**변경 파일 (테스트 + 통합 보강):**

- `tests/` (신규) — 12개 파일, pytest 56 자동 + e2e 안내
  - `conftest.py`, `_ros_helpers.py`, `run_all.sh`, `iteration_log.md`
  - 단위 4: `test_unit_{yolo_alert,patrol_state,safety_filter,map_bake}.py` (32 PASS)
  - ROS round-trip 4: `test_ros_{world_odom_tf,landmarks,safety_filter,alerts}.py` (8 PASS)
  - DB+API: `test_db_schema.py` (5), `test_api_endpoints.py` (9, venv 필요)
- `main_side/inspect_relay.py` (신규) — `/robot/inspect/command` 사이드카(rclpy)
- `main_side/camera_publisher.py` (수정)
  - SubInspect OG 노드 제거 (Isaac 5.1 ROS2SubscribeString 미등록 우회 — **B2**)
  - `_apply_inspect_cmd` 가 OG attribute 대신 `/tmp/cobot3_inspect_cmd.json` mtime 폴
  - OG TF `qosProfile = _REL_QOS` (Nav2 TransformListener 호환 — **B3**)
  - OdoPub `chassisFrameId = "Go2"` (OG TF frame 일치 — **B4**)
- `sub1_side/server/cmd_vel_safety_filter.py` (수정) — `isfinite` NaN 가드를 clamp 전으로 (**B1**)
- `sub1_side/server/nav2_params.yaml` (수정) — `robot_base_frame: Go2` 4곳 (**B4**)
- `~/.bashrc` `cobot3-start_all` (수정) — `inspect_relay.py` 자동 기동 추가
- `dev-docs/testing.md` (신규) — 테스트 구조·실행·도메인 격리·기능 매핑
- `dev-docs/ops.md` (수정) — 트러블슈팅 표 + 로그 파일 표에 신규 항목 추가

**라이브 검증 결과 (Isaac 5.1 + Nav2 humble):**

- `ros2 topic list` 14개 정상 (`/cam/{front,rear,inspect}/rgb`, `/robot/*`, `/scene/landmarks`, `/tf`, `/tf_static`)
- Nav2 lifecycle 8개 ACTIVE, `/navigate_to_pose` action 등장
- mission_command 시나리오: `sortie`→PATROL, `home`→HOME, `/alerts`→ALERT_STOP 전환 ✓
- 검사 카메라 명령 round-trip: `/robot/inspect/command` → `inspect_relay` → `/tmp/cobot3_inspect_cmd.json` → camera_publisher `_apply_inspect_cmd` pan 0.5 적용 ✓
- FastAPI: `POST /missions/command` `POST /robots/{rid}/inspect` `GET /missions/state` 모두 200
- DB `patrol_state_log` 적재 확인

**4건 통합 버그 (B1–B4) 상세:** `tests/iteration_log.md` + `dev-docs/ops.md § 5` 참조.

**토픽 hz + chain wiring + 다운링크 video/web backend 추가 검증 (2026-05-20 후속):**
- `/cam/{front,rear,inspect}/rgb` 각 11–14Hz, `/robot/{odom,leg_joint_states}` 21Hz, `/tf` 21.7Hz 발행 확인
- `/c2/{front,rear}/compressed` 4.1/4.2Hz (video_degrade 작동), MJPEG `/c2/video/mjpeg` 345KB/8s JPEG 정상
- REST 5개(`/healthz`, `/robots/gp0/{state,gps}`, `/missions/state`, `/telemetry/patrol_state`) 전부 HTTP 200
- WS `/events` 4초 메시지 카운트: `patrol_state`×20·`state`×18·`gps`×19·`diag`×1 (실시간 푸시 라이브)
- Nav2→safety_filter→/robot/cmd_vel chain wiring 정적 검증 (publishers/subscribers 일치)
- `/scene/landmarks` → patrol controller `landmarks_received=True`, home=(-714.3, 952.9) Cube 좌표 정확 적용
- 알려진 한계: Go2 spawn pose 가 gp_static map 영역 밖일 때 Nav2 planner 거부 → ops.md § 5 트러블슈팅 신규 항목 (보행 부분은 사용자 요청으로 검증 생략)

### gp_static map 정합 + Nav2 보행 검증 완료 (2026-05-20 추가)

**변경 파일:**
- `main_side/scene/maps/gp_static.{pgm,yaml}` (재베이크 — 1753×2014 px, 3.37MB)
- `sub1_side/server/nav2_patrol.py` (수정 — fence 항목 제외, cube↔cone 만 patrol — **B5**)
- `dev-docs/ops.md` 트러블슈팅 표 보강 (3개 행)
- `tests/iteration_log.md` 결과 단락 추가

**핵심 발견 (B5):**
- 이전 "spawn 위치 (-161, 46) 가 map 영역 밖" 은 잘못 — `/robot/odom` 은 IsaacComputeOdometry **누적값**, world 좌표 아님. 실제 world spawn = `tf2_echo world Go2` = **Cube(-714.32, 952.93, 30.57)** 정확.
- 진짜 plan 실패 원인: patrol 가 `/scene/landmarks` 의 fence 좌표 (-208, -208, z=118) 를 patrol_waypoint 로 잡아 map 밖 goal 발행 → planner 거부.
- 수정 후 patrol_waypoints = [Cube, Cone] 만 → sortie 시 Cone goal 산출 성공.

**보행 검증 (실측):**
- AABB: x∈[-987.1, -111.0], y∈[-4.0, 1002.9] ± 80m padding (spawn, Cube, Cone 모두 free 셀)
- Cone goal → `/cmd_vel_nav2_raw` **9.98Hz**, `/robot/cmd_vel` **10Hz**, planner WARN 0건
- 30초 보행: `/robot/odom` 누적 (0.45, -0.52) → (-1.92, -4.02), linear.x 0.12~1.61 m/s
- alert → ALERT_STOP 2s, 자동 복귀 ~4s
- DB `patrol_state_log` 10행 적재

이로써 cobot3 통합의 모든 핵심 흐름(spawn→sortie→이동→alert→정지→복귀→home)이 실보행으로 입증됨.

### DMZ_Zone + jsy YOLO/웹 완전 통합 (P1~P5, 2026-05-20 후속)

**변경 파일:**

P1 외부 자산:
- `main_side/scripts/yolo_train/{convert_replicator_to_yolo.py,train_2class_yolo.sh,README.md}` (신규)
- `main_side/scene/maps/dmz_demo.{pgm,yaml}` (신규)
- `main_side/scene/assets/dmz/LICENSE.txt` (신규)
- `sub1_side/web/_jsy_reference/{index.html,app.js,style.css}` (신규, build 제외)

P2 DMZ_Zone:
- `main_side/camera_publisher.py` (수정 — `_build_dmz_zone`, `GP_GO2_SPAWN_ZONE` 분기, landmarks dmz_* 키 추가)
- `main_side/bake_gp_static_map.py` (수정 — `--zone dmz` 옵션)
- `sub1_side/server/nav2_patrol.py` (수정 — zone 분기 dmz vs cube)

P3 YOLO 동물:
- `sub1_side/server/models/{README.md,.gitignore}` (신규)
- `sub1_side/server/config.py` (수정 — `_pick_model()`, `YOLO_CLASSES` 11종, animal alert 정책, `animal_alerts` 토픽)
- `sub1_side/server/yolo_infer.py` (수정 — 3-tuple 반환, 독립 cooldown, animal label)
- `sub1_side/server/ros_bridge.py` (수정 — `_animal_pub`, animal_alert WS emit, DB 적재)

P4 웹 컴포넌트:
- `sub1_side/web/components/{DualCameraView,AnimalAlertsLog,EventLog}.tsx` (신규)
- `sub1_side/web/components/MapTrack.tsx` (수정 — DMZ marker, fence 점선)
- `sub1_side/web/app/page.tsx` (수정 — 3 신규 컴포넌트 마운트, animal_alert 핸들러)
- `sub1_side/web/lib/api.ts` (수정 — `animal_alert` C2Event, `LandmarksPayload.zone/dmz_*`)

P5 테스트:
- `tests/test_unit_yolo_animal_classes.py` (신규, 4 케이스)
- `tests/test_unit_dmz_zone_landmarks.py` (신규, 3 케이스)
- `tests/test_ros_animal_alerts.py` (신규, 2 케이스)
- `tests/test_e2e_dmz_zone.md` (신규, T13 수동 시나리오)
- `tests/test_unit_yolo_alert.py` (수정 — 3-tuple 마이그레이션, 기존 8 PASS 유지)
- `tests/{iteration_log.md, run_all.sh}` (수정)

**테스트 결과:** 전체 회귀 **63 PASS** (시스템 python 54 + venv API 9).
- yolo_alert(8) + safety_filter(7) + patrol_state(13) + map_bake(4) + **yolo_animal_classes(4)** + **dmz_zone_landmarks(3)** = 39 단위
- ros_alerts(2) + ros_landmarks(2) + ros_safety_filter(3) + ros_world_odom_tf(1) + **ros_animal_alerts(2)** = 10 ROS
- db_schema(5) + api_endpoints(9) = 14 DB/API

**핵심 설계:**
- DMZ_Zone 은 `/World/DMZ_Zone/*` 런타임 prim — gp_scene.usd binary 불편집, OG sensor_bridge 와 prim 경로 분리로 충돌 없음. idempotent (RemovePrim → 재생성).
- spawn 분기: `GP_GO2_SPAWN_ZONE=cube|dmz` env. cube=기존 Cube(-714,952) nearest-vertex, dmz=DMZ_Zone home(0,0) nearest-vertex (없으면 Ground plane +0.05+CLEAR).
- YOLO 모델 슬롯: env > models/*.pt > yolov8n.pt 자동 다운로드.
- person/animal alert 독립 cooldown: `_last_person_alert_ts`, `_last_animal_alert_ts` 분리. animal alert 는 `/animal_alerts` 별도 토픽 + WS `animal_alert` event.
- `nav2_patrol` 은 `/alerts` (person) 만 ALERT_STOP 트리거 — animal 은 monitor only (사용자 정책 별도 변경 가능).
- 웹 `MapTrack`: zone="dmz" 시 자동 센터링 + amber DMZ marker + fence 점선.
- `DualCameraView`: FRONT + INSPECT MJPEG 2-panel (server `/c2/video/mjpeg?camera=...` 활용).

**알려진 한계:**
- Guard_Tower / chainlink_fence USDZ 라이선스 TBD — 데모 한정 (`scene/assets/dmz/LICENSE.txt` 명시).
- jsy fine-tuned `.pt` 부재 시 COCO 기본 — 사슴 직접 클래스 없음, bear/sheep 등으로 fallback 감지.
- DMZ_Zone 보행 e2e 는 T13 수동 시나리오로 검증 (Nav2 map 을 `dmz_static.yaml` 로 교체 필요).

### sub1_side 웹 데이터 정합 재구조화 + Lichtblick 디버그 고도화 (2026-05-20)

**변경 파일:**
- `sub1_side/web/components/{StatusHeader,TelemetryStrip}.tsx` (신규)
- `sub1_side/web/app/page.tsx` (재작성 — 8 컴포넌트 import 제거 + 2 신규 + 새 grid)
- `sub1_side/web/app/debug/page.tsx` (단순화 — SpotSurroundView 제거, Lichtblick iframe only)
- `sub1_side/lichtblick/layout.json` (재작성 — 3D!go2 + Plot!joint_position(12 라인) + Plot!foot_position(4 라인) + Plot!cmd_vel + Image!cam_front)
- 삭제: `sub1_side/web/components/{ThreatBar,EngagementConsole,ContactsPanel,OpsLedger,ReadinessStrip,VideoWall,SpotSurroundView}.tsx` (7 컴포넌트)
- `dev-docs/sub1-side.md` 컴포넌트 표 갱신

**메인 페이지 (`/`):** 실 데이터(/cam, /robot/{odom,state,gps,leg_joint_states}, /alerts, /animal_alerts, /patrol_state, /scene/landmarks, /tf) 중심 11 컴포넌트 2-col grid. StatusHeader (h-12) + TelemetryStrip (h-16, mode·gait·battery·waypoint·pose·gps) + Hero(DualCameraView · MapTrack) + 컨트롤(PatrolControls · TeleopPad 토글 · InspectorCameraPanel) + 알람(AlertsLog · AnimalAlertsLog) + DiagnosticsStrip + EventLog. 위협 등급·사격·중복 컴포넌트 제거.

**디버그 페이지 (`/debug`):** SpotSurroundView Three.js 3D 제거, Lichtblick iframe 100vh + 헤더만. 패널은 layout.json 의 default-layout 으로 자동 로드 — 이미지 #5 (Lichtblick 표준) 와 동일 구조: 좌 3D 보울(URDF Go2 + PointCloud Z-turbo + TF + odom follow) 50% + 우 Plot×3(joint_position 12 line · foot_position 4 line · cmd_vel linear/angular) + Image!cam_front.

**검증:**
- `tsc --noEmit` 무에러
- `next build`: `/` 7.52kB (이전 9.89kB ↓2.4kB), `/debug` 867B (이전 1.97kB ↓1.1kB), shared 87.1kB
- 회귀 전체 **63 PASS** 유지 (web 변경, 서버/ROS 무관)
- Lichtblick 컨테이너는 `-v layout.json:/lichtblick/default-layout.json:ro` 마운트로 자동 적용, `cobot3-down_all && cobot3-start_all` 한 번 재기동 시 신 layout 활성

**Supabase:** 미사용 (이전 정책 유지).

---

## 2026-05-19

### Go2 Foxglove "볼록렌즈/보울" 카메라 PointCloud 시각화

**변경 파일:** `main_side/camera_publisher.py` (수정),
`main_side/go2_description/{urdf/go2.urdf,dae/*.dae}` (신규),
`sub1_side/lichtblick/layout.json` (수정)
- Isaac OG 단일 `og.Controller.edit()` 에 `CamDepth`/`CamInfo`/`CamPCL`
  추가 — 기존 `RPFront` 렌더프로덕트 공유, frameId=camera_front.
  신규 토픽 `/cam/front/depth`(Image 32FC1), `/cam/front/camera_info`
  (CameraInfo), `/cam/front/points`(PointCloud2, type=depth_pcl).
- 전/후 카메라 내부파라미터 D455 보정: focalLength 1.93→10.5mm +
  horizontalAperture 20.955 (~90° FOV) — 보울 스케일 정합.
- Go2 URDF/메시(go2.urdf + dae 7) 를 `main_side/go2_description/` 에
  스테이징 → `run_urdf_server.sh`(:8766, 무수정) 가 CORS 서빙.
- Lichtblick `layout.json` 전체 교체: `3D!spot`→`3D!go2`
  (go2.urdf + `/cam/front/points` Z-turbo 보울 + /tf + /robot/odom,
  follow base) + `Image!depth` 추가. 토픽명 불변 → ros_bridge/web 무수정.
- 영향: foxglove_bridge 가 신규 PointCloud2 자동 노출. depth_pcl
  미지원 빌드 시 depth+camera_info 기반 Lichtblick 투영 fallback.

### 듀얼 카메라 MJPEG 스트림 + GP 씬 에셋 추가

**변경 파일:** `sub1_side/web/components/VideoWall.tsx` (수정)
- WebRTC/MJPEG 폴백 로직 제거 → 전방·후방 MJPEG 이미지 직접 렌더링으로 단순화
- `/c2/video/mjpeg?camera=front` (메인 패널) + `?camera=rear` (하단 1/3 패널) 듀얼 레이아웃

**변경 파일:** `sub1_side/server/app.py` (수정)
- `GET /c2/video/mjpeg` 에 `camera: str = "front"` 쿼리 파라미터 추가 (front|rear)

**변경 파일:** `sub1_side/server/ros_bridge.py` (수정)
- DB 저장 시 waypoint 타입 안전 처리: `isinstance(wp, int)` 체크 후 None 폴백

**변경 파일:** `main_side/scene/gp_scene.usd` (수정), `gp_scene2.usd`, `terrain_hellokitty.usd` (신규)
- GP 씬 업데이트 및 헬로키티 터레인 추가

**변경 파일:** `main_side/scene/assets/dmz_scene_flat.usda`, `assets/materials/`, `assets/props/` (신규)
- DMZ 씬 에셋, Ground 재질 텍스처, 펜스/탑 프롭 추가

**변경 파일:** `main_side/go2_wtw_mcp.py` (신규)
- Go2 WTW MCP 제어 스크립트 추가

---

### Next.js API 호스트 고정 버그 수정 (SSR freeze)

**변경 파일:** `sub1_side/web/lib/api.ts` (수정)
- **원인:** `API_BASE = process.env.NEXT_PUBLIC_C2_API || "http://localhost:8000"` 가 모듈 레벨 상수로 선언 → Next.js SSR 시점(window 없음)에 `"http://localhost:8000"` 으로 고정됨
- **수정:** `getApiBase()` 런타임 함수로 교체 (`window.location.hostname` 기반, `"use client"` 보장)
- **효과:** 브라우저에서 C2 PC IP(192.168.10.105:8000)로 올바르게 요청

**변경 파일:** `sub1_side/web/components/VideoWall.tsx` (수정)
- `import { API_BASE }` → `import { getApiBase }` 로 교체
- WebRTC offer URL, MJPEG src, HUD 레이블 등 4곳 `API_BASE` → `getApiBase()` 치환

### WebSocket /events 연결 오류 수정 (uvicorn websockets 라이브러리 누락)

**변경 파일:** `sub1_side/server/.venv` (재생성)
- **원인:** `uvicorn` 단독 설치 → WebSocket 지원 라이브러리(`websockets`/`wsproto`) 없음 → `WARNING: No supported WebSocket library detected` → WS 연결 404
- **수정:** `pip install "uvicorn[standard]" websockets` (C2 PC .venv에 적용)
- **참고:** 이후 rsync는 반드시 `--exclude='.venv'` 사용 (venv shebang 경로 사용자별 상이)

### CORS 차단 수정

**변경 파일:** `sub1_side/server/config.py` (수정)
- `C2_WEB_ORIGINS` 미설정 시 `["*"]` (LAN 전체 허용) — 개발 모드 기본값
- 기존: 고정 `localhost:3000` 목록 → C2 IP(192.168.10.105:3000) 차단

### Three.js Object.assign 버그 수정

**변경 파일:** `sub1_side/web/components/SpotSurroundView.tsx` (수정)
- **원인:** `Object.assign(new THREE.DirectionalLight(...), { position: new THREE.Vector3(...) })` → Three.js `Object3D.position` 은 non-replaceable `Vector3` 인스턴스, `Object.assign` 으로 교체 불가
- **수정:** `const blueLight = new THREE.DirectionalLight(0x0044cc, 0.4); blueLight.position.set(-4, 2, -4);`

---

## 2026-05-18

### debug 페이지 Three.js 3D 패널 추가
**변경 파일:** `sub1_side/web/components/SpotSurroundView.tsx` (신규),
              `sub1_side/web/app/debug/page.tsx` (수정)
- Three.js 3D 시각화 패널을 debug 페이지 상단에 추가 (height 280px)
- 로봇 바디 (주황색 박스 + 4다리), 전방 75° FOV 황색 frustum, 후방 75° FOV 청록 frustum,
  2.5m 녹색 커버리지 링 시각화
- 마우스 드래그 시점 회전 (spherical coords), 스크롤 줌
- `/robots/gp0/state` 200ms 폴링으로 odom yaw 실시간 반영 → robotGroup.rotation.y
- `import type * as THREE` 패턴으로 TypeScript 타입 안전 + SSR 안전 동시 달성

**변경 파일:** `sub1_side/server/ros_bridge.py` (수정)
- `_on_odom()` quaternion → yaw 변환 추가 (`math.atan2` 공식)
- `latest["odom"]`에 `"yaw"` 필드 추가: `{"x":…,"y":…,"z":…,"yaw":…}`

**변경 파일:** `sub1_side/server/app.py` (수정)
- `GET /robots/{rid}/state` 응답에서 잔재 `arm_q` 키 제거 (KeyError 방지)

**변경 파일:** `sub1_side/web/package.json` (수정)
- `three@^0.184.0`, `@types/three@^0.184.1` 의존성 추가

### 개발문서 체계 구축
**변경 파일:** `dev-docs/README.md`, `architecture.md`, `main-side.md`, `sub1-side.md`,
              `ros2-interface.md`, `ops.md`, `CHANGELOG.md` (신규)
**변경 파일:** `CLAUDE.md` (프로젝트 루트, 신규)
- main_side·sub1_side 전체 아키텍처/기능/통신 문서화
- source→doc 매핑 + CLAUDE.md로 코드 변경 시 자동 문서 갱신 체계 수립

---

## 2026-05-17

### spot_with_arm → spot 전환 + 2-카메라 시스템

**변경 파일:** `main_side/camera_publisher.py` (수정)
- 로봇 교체: spot_with_arm → spot (팔 없음, 12-DOF 다리만)
- 카메라 변경: 손목 카메라 1개 → 기체 전/후방 카메라 2개
- OmniGraph: 단일 카메라 노드 → RPFront/CamFront + RPRear/CamRear 이중 파이프라인
- ArmJS (arm joint states 발행) 제거
- 상수 변경: `CAM_PATH` → `CAM_FRONT_PATH` + `CAM_REAR_PATH`

**변경 파일:** `main_side/spot_controller.py` (수정)
- arm 관련 코드 전면 제거 (_STOW, _AIM, arm_idx, _patch_arm_gains, trigger_fire, set_speaker)
- 12-DOF 단순화: `_forward()` 순수 RL 정책 적용
- `initialize(set_gains=True, set_limits=True)`

**변경 파일:** `main_side/spot_isaac.urdf` (수정)
- arm0_* 링크 7개 + 관절 7개 제거
- 13링크(base+12다리), 12관절(3/다리×4)

**변경 파일:** `main_side/video_degrade_node.py` (수정)
- 하드코딩 토픽 → 환경변수 (`DEGRADE_IN`, `DEGRADE_OUT`)

**변경 파일:** `main_side/run_degrade.sh` (수정)
- 단일 인스턴스 → front/rear 2인스턴스 병렬 실행

**변경 파일:** `sub1_side/server/config.py` (수정)
- `arm_joint` 토픽 제거, `video` 단일 → `video_front` + `video_rear` 이중

**변경 파일:** `sub1_side/server/ros_bridge.py` (수정)
- arm_q 구독/저장 제거
- 단일 video → front/rear 이중 구독

**변경 파일:** `sub1_side/lichtblick/layout.json` (수정)
- Plot!arm 패널 제거
- Image!cam 단일 → Image!cam_front + Image!cam_rear 이중

---

## 2026-05-15

### isaac-sim-mcp 타임아웃 수정

**변경 파일:** `/home/rokey/dev_ws/isaac-sim-mcp/isaac_mcp/server.py` (수정)
- 연결 타임아웃 추가 (5초): `sock.settimeout(5.0)` before `connect()`
- 수신 타임아웃 단축 (300s → 60s): 무한 로딩 방지

---

## 2026-05-14 (이전)

### Spot 기반 시스템 전환 및 기반 구축
- ANYmal-C + m0609 2-아티큘레이션 → spot_with_arm 단일 아티큘레이션
- OmniGraph 기반 ROS2 브리지 구축 (render=True 필수 발견)
- FastDDS UDP-only 설정으로 Isaac↔System ROS2 크로스호스트 통신 해결
- C2 web_server FastAPI + Next.js 전술 콘솔 구축
- Lichtblick Foxglove 3D 시각화 구성
- PostgreSQL 텔레메트리 저장 체계 구축
