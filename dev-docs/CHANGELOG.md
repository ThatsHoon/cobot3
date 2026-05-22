# CHANGELOG

이 파일은 cobot3 시스템의 주요 변경사항을 날짜 역순으로 기록합니다.
각 항목에는 변경된 파일, 변경 내용, 영향을 받는 컴포넌트를 기술합니다.

---

## 2026-05-22 (D)

### auto-nav 지연 근본 해결 — DRIVE/TURN 이진 분리 제거 + 속도 상향

**변경 파일:** `main_side/cmd_vel_safety_filter.py` (수정),
`main_side/nav2_params.yaml` (수정),
`tests/test_unit_safety_filter.py` (수정),
`tests/test_ros_safety_filter.py` (수정)

**cmd_vel_safety_filter.py:**
- DRIVE/TURN 이진 모드 분리 완전 제거. Go2 는 곡선 주행 가능하므로
  `linear.x` + `angular.z` 를 동시에 통과시킨다.
- 제거된 파라미터: `turn_enter_angular`, `turn_exit_angular`, `MODE_DRIVE/MODE_TURN`.
- 유지: `max_linear_x` / `max_angular_z` 클램프, `min_drive_linear` 노이즈 데드존,
  `MUTE_MODES={"PAUSED"}` mute 로직, NaN/Inf 가드.

**nav2_params.yaml:**
- `max_vel_x: 0.6 → 1.0` (WTW 학습 분포 경계, teleop 수준 근접)
- `max_speed_xy: 0.6 → 1.0`
- `max_vel_theta: 0.8 → 1.0`
- `acc_lim_x: 0.5 → 1.5`, `decel_lim_x: -0.5 → -1.5` (가속 응답성 향상)
- `acc_lim_theta: 1.0 → 1.5`, `decel_lim_theta: -1.0 → -1.5`
- `velocity_smoother.max_accel: [1.0,0,1.6] → [2.5,0,2.0]`, `max_decel` 대칭 상향

**테스트 갱신:**
- `test_simultaneous_linear_and_angular` 신규 (DRIVE/TURN 분리 제거 검증)
- 구 `test_turn_enter/exit_threshold`, `test_turn_mode_zeros_linear` 제거

---

## 2026-05-22 (C)

### 운용 문서 갱신 + auto-nav 지연 원인 분석

**변경 파일:** `dev-docs/ops.md` (갱신), `.gitignore` (수정)

- `ops.md` Main PC 기동 목록: `fall_relay.py` / `weapon_relay.py` / `wind_publisher.py` / `run_nav2.sh` / `cmd_vel_safety_filter.py` / `nav2_patrol.py` 누락 항목 추가 (2026-05-21 Main 측으로 이동 후 미반영).
- `ops.md` 로그 테이블: Nav2/cmd_vel_safety/nav2_patrol 가 C2 전용 → Main + C2 각각 실행으로 수정.
- `ops.md` 트러블슈팅: auto-nav 지연 원인 분석 추가 — DRIVE/TURN 이진 분리 + `max_vel_x=0.6` + `acc_lim_x=0.5` 가 복합 원인, 해결 방향 2가지 명시.
- `.gitignore`: `main_side/scene/gp_scene2.usd` 추가.

---

## 2026-05-22 (B)

### 씬 감사 + 지형 CollisionAPI 수정 + 철조망 재설치 + Go2 spawn/nav 경로점 연동

**변경 파일:** `main_side/scene/gp_scene.usd` (수정),
`main_side/camera_publisher.py` (수정),
`dev-docs/main-side.md`, `dev-docs/ops.md` (갱신)

**씬 감사 결과 수정 (gp_scene.usd):**
- `Hill_terrain1` (15 mesh) + `Hill_terrain2` (13 mesh): CollisionAPI 0% → 100%, physics_material 바인딩. 기존 `/World/Terrain` 삭제 이후 camera_publisher.py safety-net 이 `/World/Terrain` 만 체크하던 버그 수정.
- `Fence_Line` 완전 재설치: 기존 잘못된 에셋 경로(`scene/barbed_wire_fence.usdz` 미존재 → mesh 미렌더) → 올바른 경로(`scene/assets/barbed_wire_fence.usdz`) 로 재생성.
- `Fence_Line` 19 세그먼트: `Fence_Waypoints` 45 waypoint 궤적 추종, 높이 5.2m, 지면 아래 0.59m 임베드(지면에서 솟아남), xformOpOrder [translate:world, rotateZ, scale, rotateX, translate:inner] 순서 확정.
- `Fence_Line` 이전 xformOpOrder 버그: `SetXformOpOrder` 가 ops 를 역순으로 적용 → 펜스 위치 (-497, 0, -47) 로 오배치. 해결: AddXformOp 순서 자체를 outermost→innermost 로 정렬, SetXformOpOrder 제거.

**camera_publisher.py:**
- 지형 safety-net: `_TERR_ROOTS = ["/World/Hill_terrain1", "/World/Hill_terrain2", "/World/Terrain"]` (다중 지형 prim 지원).
- physics_material 탐색 우선순위: `/World/Physics_Materials/physics_material` → fallback `/World/Terrain/**` 순.
- Go2 spawn 위치: 하드코딩 → `/World/Routing_Zones/StartingPoint` Xform 자동 읽기 (fallback 194.56, 837.70, 5.02).
- Go2 시동 nav 목표: `/World/Routing_Zones/Standard_Point` Xform 자동 읽기 (fallback 199.09, 892.60, 4.52).
- arrive_box: 10.0m → **2.0m** (2m 이내 도달 = 목적지 도착 간주).
- overhead 카메라 초기 위치: 하드코딩 (212.8, 890.53) → `_GO2_HOME_XYZ` 기반 동적 설정.

**신규 환경변수:** `GP_GO2_GOAL_X/Y/Z` (Standard_Point 좌표 오버라이드).

---

## 2026-05-22

### 씬 정리 + 철조망 울타리 설치 + MCP 서버 교체

**변경 파일:** `main_side/scene/gp_scene.usd` (수정),
`main_side/scene/overrides/gp_scene_overrides.usda` (수정),
`main_side/camera_publisher.py` (수정),
`main_side/scripts/cobot3_env.sh` (수정),
`dev-docs/main-side.md`, `dev-docs/scene-overrides.md`, `dev-docs/ops.md` (갱신)

**씬 정리 (gp_scene.usd):**
- 삭제: Cube (디버그 잔재), radar_tower / Watchtowers / Fence (기존 정적 props), spike_ball / banana_obstacle / Landmine (동적 장애물). 총 7개 prim 제거.
- 추가: `Fence_Line` — `barbed_wire_fence.usdz` 49개 세그먼트를 `Fence_Waypoints` Xform 배열을 따라 배치 (2026-05-22 MCP로 직접 생성). 높이 9m, RotateX=+90° (Y-up→Z-up 변환).
- `gp_scene_overrides.usda` — 삭제된 prim 의 `over` 항목 전부 제거. 현재 override 대상: Go2_starting_point / militarybase / Doro 3개.

**camera_publisher.py:**
- `_build_dmz_zone()` 함수 및 관련 DMZ 상수 전체 제거 (DMZ_Zone prim 삭제에 따른 정리).
- `_EXTRA_PRIMS` = `["/World/spike_ball", "/World/banana_obstacle", "/World/Landmine", "/World/Doro"]` → `["/World/Doro"]` 로 축소.
- `_MARKER_PRIMS` 제거 (radar_tower 포함 시각 마커 prim 삭제).

**MCP 서버 교체:**
- 구 `~/dev_ws/isaac-sim-mcp/` (9도구) → `~/dev_ws/isaacsim-mcp-server/` (whats2000/isaacsim-mcp-server, 42도구).
- `cobot3_env.sh` `--ext-folder` 경로 변경.

---

## 2026-05-21

### Nav2 lifecycle race 해결 — Isaac /clock 대기 후 nav2 기동

**변경 파일:** `~/.bashrc` (수정), `dev-docs/ops.md` (수정).

**증상**: `cobot3-start_all` 후 teleop 은 정상이나 sortie/Nav2 자동 주행 안 됨. nav2_patrol 이 `WAITING_FOR_NAV2` 무한 대기. lifecycle 상태 점검 시 map_server/planner_server/controller_server/smoother_server 는 `inactive` (configured 만), bt_navigator/behavior_server/velocity_smoother/waypoint_follower 는 `unconfigured`.

**근본 원인**: Isaac 가 씬/OG 로드 중 (60–90초) CPU 점유율이 매우 높을 때, 같은 시점에 nav2 가 시작되면 lifecycle service RMW response (`/planner_server/change_state` 등) 가 손실 → lifecycle_manager autostart sequence 가 planner_server 단계에서 정지 → 후속 노드들 활성화 안 됨 → `navigate_to_pose` action server 미존재.

**해결**: `cobot3-start_all` MAIN 분기에서 nav2 기동 전 `ros2 topic echo /clock --once` (90초 timeout) 로 Isaac OG 빌드 완료 대기 후, +5초 마진 → nav2 → +8초 → nav2_patrol. /clock 첫 메시지 = camera_publisher.py 의 ROS2PublishClock 이 OG 빌드 완료 후 발행 시작한 시점.

복구 절차는 [ops.md § Nav2 lifecycle race 해결](ops.md) 참고.

### `cobot3-restart_all` 별칭 추가

**변경 파일:** `~/.bashrc` (수정), `dev-docs/ops.md` (수정).

- `cobot3-restart_all [mcp]` 함수 추가 — `cobot3-clear` → `cobot3-start_all` (또는 `-with_mcp`) 순차. 시연 중 코드/씬 변경 후 빠른 재기동 용.
- `ops.md` § 빠른 재기동 절 신설.

### 씬 4축 고도화 — USD 효율 직접 수정 + 물리 sublayer 분리

`gp_scene.usd` 4축 감사 (구조/효율/물리/통합) 결과 발견된 P0 결함 일괄 처리.
상세 보고서: [physics-scene-audit.md](physics-scene-audit.md).

**변경 파일:** `main_side/scene/gp_scene.usd` (수정 + .bak.20260521_173334),
`main_side/scene/overrides/gp_scene_overrides.usda` (신규),
`main_side/camera_publisher.py` (수정 — sublayer load + spawn env + Clock rate + safety-net 분기),
`dev-docs/physics-scene-audit.md` (신규), `dev-docs/scene-overrides.md` (신규),
`dev-docs/main-side.md` (씬 구조 / camera_publisher 상수 표 갱신).

- **USD 직접 수정 (효율성)**: `/World/Cube` (정찰선 밖 디버그 잔재) `active=false` 적용 후 `save_stage()`.
- **신규 sublayer** `gp_scene_overrides.usda` — 9개 신규 prim 의 root 속성 보강:
  - 동적 (spike_ball / banana_obstacle / Landmine): `collisionEnabled=true` + `mass=2.0/0.3/1.0` + Collision/Mass/MaterialBindingAPI schema
  - 시각 마커 (Go2_starting_point / militarybase / radar_tower): `collisionEnabled=false`
  - 정적 props (Watchtowers / Fence / Doro): `MaterialBindingAPI` schema 사전 적용
  - 로드 메커니즘: stage open 직후 `subLayerPaths.insert(0, …)` (강한 opinion).
- **camera_publisher.py 4건 수정**:
  - sublayer prepend 코드 (`GP_USE_OVERRIDES=0` 으로 끄기 가능)
  - `_GO2_HOME_XYZ` 에 `GP_GO2_SPAWN_X/Y/Z` env 추가 (world_odom_tf_pub.py 와 SSOT)
  - Clock 노드 — 별도 `publishRate` input 없음 (라이브 검증 후 정정: ROS2PublishClock 에 해당 속성 부재 → OmniGraphError). OnPlaybackTick render_dt=1/50 → 50Hz 발행
  - 9-prim safety-net 의 leaf Mesh approximation 을 dynamic(`convexHull`) / 정적(`none`) 분기 — PhysX 가 dynamic rigidBody 에 trimesh-none 금지 위반 해소
- **검증 (offline pxr composition)**: spike_ball `rb=True ce=True mass=2.0`, Cube `active=False`, PrimStack 최상단 = overrides 레이어 — 모두 통과.
- **롤백**: `GP_USE_OVERRIDES=0` env 또는 sublayer 파일 삭제. USD 변경 자체는 `gp_scene.usd.bak.20260521_173334` 복원으로 원복.
- **알려진 제약**: 라이브 stage 에 `subLayerPaths.insert()` 호출 시 full recomposition 으로 kit thread 행 위험 — 항상 stage open 시점에만 prepend.

### 무기 사격 (HITL) + 날씨/바람 시뮬레이션 통합

**Feature 1: 총기 부착 + HITL 사격 시퀀스**

- `main_side/camera_publisher.py` — `inspect_gimbal` 구조 안 weapon_mount 신규
  procedural prim (barrel cylinder + receiver/stock cube), muzzle Xform.
  `_update_weapon_xform` 가 inspect pan/tilt 와 동기 회전 (HITL: 운용자가
  inspect 영상 보고 조준 → weapon 자동 정렬).
- `main_side/camera_publisher.py` — `_fire` state machine 신규:
  IDLE → RAMP_DOWN(0.2s body_height -0.08, stance_w +0.05) → FIRE(1-step
  2500N impulse along inspect dir) → HOLD(0.5s) → RAMP_UP(0.2s) →
  COOLDOWN(2s). Margolis WTW 2022 stance widening 학습 근거 활용.
- `main_side/go2_controller.py` — `set_stance_override(body_height, stance_w,
  stance_l)` 외부 ramp hook, `_command()` 에 _CMD_BASE 가산. 또한
  `apply_external_impulse(force, position, torque)` dynamic_control 기반.
- `main_side/weapon_relay.py` (신규) — `/robot/weapon/fire` Trigger server,
  fire_id UUID 발급, `/tmp/cobot3_fire_cmd.json` IPC + result polling,
  `/robot/weapon/state` (String JSON 1Hz latched) 발행.
- `main_side/camera_publisher.py` `_apply_inspect_cmd` — `look_at_pixel`
  키 신규: bbox 중심 픽셀 → inspect intrinsics 로 pan/tilt delta 계산
  (HITL [TRACK] 버튼이 사용).
- `sub1_side/db/schema.sql` — fire_events 4 컬럼 추가 (fire_id UUID,
  target_alert_id, miss_reason, result_set_at) + 멱등 ALTER.
- `sub1_side/server/db_writer.py` — COLUMNS 갱신 + `update_fire_result()`
  async UPDATE 메서드 신규.
- `sub1_side/server/ros_bridge.py` — `call_fire()` 새 규약 (fire_id|state)
  반환, `record_fire_result()` 메서드, `/robot/weapon/state` subscribe +
  WS `weapon_state` emit.
- `sub1_side/server/app.py` — `POST /robots/{rid}/fire/result` 신규
  (운용자 hit/miss 입력), `POST /robots/{rid}/inspect` 에 look_at_pixel
  body 키 확장, `POST /weather` 신규.
- `sub1_side/web/components/WeaponFireControl.tsx` (신규) — inspect MJPEG +
  crosshair overlay + FIRE 버튼 + cooldown 표시 + 결과 모달 (Hit/Miss/Cancel).
- `sub1_side/web/components/AlertsLog.tsx` — 각 alert 행에 [TRACK] 버튼
  신규: bbox 중심 픽셀로 inspect 카메라 회전.

**Feature 2: 날씨 + 랜덤 바람 + 시각효과 (hi 브랜치 포팅)**

- `main_side/weather_visuals.py` (신규) — ThatsHoon/cobot3 'hi' 브랜치
  `isaacsim/anymal_gp_terrain.py` 의 TIME_OF_DAY_PRESETS (morning/noon/
  evening/night) + WEATHER_PRESETS (clear/cloudy/fog/rain/snow) +
  `_add_weather_effects` / `_apply_environment_visuals` /
  `_update_weather_effects` 발췌·재구성. RainStreaks 220 BasisCurves,
  FogBands 54 BasisCurves, SnowFlakes 260 Points procedural geometry.
  DomeLight `/World/DomeLight_01` 재사용 + 신규 DistantLight `/World/Sun`.
- `main_side/wind_publisher.py` (신규) — von Mises (κ=4) 방위각 + Weibull
  (k=2) 풍속 + AR(1) α=0.85 smoothing, 5 mode preset (calm~storm), gust
  Bernoulli(p_dt) 1.5× 1초 spike. 풍속 상한 18 m/s (WTW max_push_vel_xy
  =1.0 학습 분포 등가). `/wind/state` Vector3Stamped 20Hz + IPC dump.
- `main_side/camera_publisher.py` — `WeatherVisuals` init + 메인 루프 안
  `_apply_weather_cmd()` (IPC poll), `vis.update(dt)`, `_apply_wind_force()`
  (dc.apply_body_force 매 step Go2 base 에 `F = ½ρCdA|v_rel|·v_rel`).
  PhysxForceFieldWindAPI 회피 (articulation 적용 시 PxArticulationLink
  경고 보고 다수 — NVIDIA 포럼 확인).
- `sub1_side/server/config.py` — TOPICS: weather_cmd, wind_state,
  weapon_state, weapon_fire 추가.
- `sub1_side/server/ros_bridge.py` — `/wind/state` Vector3Stamped subscribe
  (5Hz throttled WS emit, dir_deg/speed derivation), `pub_weather_cmd()`
  메서드 + publisher.
- `sub1_side/web/components/WeatherControl.tsx` (신규) — 4×5 time/weather
  버튼 + wind mode dropdown + RND DIR/SPD OVR 토글 + 슬라이더.
- `sub1_side/web/components/WindGauge.tsx` (신규) — StatusHeader 옆 SVG
  화살표 + 보퍼트 라벨 + 풍속 m/s + 풍향°.

**ROS2 신규 토픽 (5개):**
| 토픽 | 타입 | QoS | 방향 |
|---|---|---|---|
| `/robot/weapon/fire` | std_srvs/Trigger | RELIABLE | C2→Main (service) |
| `/robot/weapon/state` | std_msgs/String | RELIABLE+TRANSIENT_LOCAL 1Hz | Main→C2 |
| `/weather/command` | std_msgs/String | RELIABLE | C2→Main |
| `/wind/state` | geometry_msgs/Vector3Stamped | RELIABLE 20Hz | Main→C2 |

**환경변수 신규:**
- `GP_GO2_MASS` — Go2 base mass 보정 (기본 12.0 kg, Unitree 실측)

**핵심 설계 결정:**
- 명중 판정 = HITL (인간이 inspect 영상 보고 결정) — raycast 자동 판정 제거
- weapon = inspect 카메라와 동일 회전 (별도 gimbal 없음 — 부착 위치 동일)
- 풍속 상한 18 m/s = WTW `max_push_vel_xy=1.0` 등가 임펄스 한계
- 시각효과 ↔ 물리바람 분리 — 시각효과는 hi 그대로, 물리는 신규
- PhysxForceFieldWindAPI 회피 — dc.apply_body_force 명령형

**핵심 리서치 근거:**
- Margolis et al. "Walk These Ways" CoRL 2022 (arXiv:2212.03238) — stance
  widening + body drop 이 leg shove 강건성 증가
- Ghost Robotics Vision-60 + SPUR — 등판 마운트, 4발 정역학 흡수 (별도
  자세 변경 안 함, 우리는 데모 가시성 위해 WTW 안전 stance 채택)
- ETH `rotors_simulator/gazebo_wind_plugin` — wind force apply 패턴

---

### Go2 zero-cmd drift 근본 원인 수정 — walk-these-ways standstill clamp

**변경 파일:** `main_side/go2_controller.py` (수정)
- **증상:** Nav2/teleop 둘 다 미발행 상태에서 Go2 가 평면상 작은 원을 그리며
  드리프트. cmd_rx 가 동결돼 있음에도 보행이 멈추지 않음.
- **근본 원인:** `_command()` fallback `_CMD_BASE` 가 step_freq=3.6,
  footswing=0.15 으로 채워져 있어 vx/vy/wz=0 이라도 walk-these-ways 정책이
  계속 step 페달링 → 정책 noise 가 yaw drift 로 누적.
- **수정:** `active_teleop=False` 이면 `cmd[4]=0.0`(step_freq),
  `cmd[9]=0.0`(footswing) 강제 — standstill clamp.
- 영향 확인: zero-cmd 보행 정지, teleop/nav 입력 시 정상 보행.

### Foxglove Python SDK 사이드카 + Immersive Camera + DualSense 통합

**신규 사이드카(서버):**
- `sub1_side/server/foxglove_sdk_publisher.py` (신규) — rclpy + foxglove SDK
  동거. `foxglove.start_server(host="0.0.0.0", port=8767)` 자체 WS 서버.
  ROS String JSON 토픽 5종을 native schema 채널로 변환·발행:
  - `/sdk/intruder_markers` (SceneUpdate · SpherePrimitive, level=ALERT 빨강)
  - `/sdk/landmark_markers` (SceneUpdate · home/goal CubePrimitive + arrive_box
    CylinderPrimitive + TextPrimitive)
  - `/sdk/patrol_goal_pose` (PoseInFrame)
  - `/sdk/inspect_annotations` (ImageAnnotations · YOLO bbox LINE_STRIP)
  - `/sdk/alert_log` (Log · WARNING)
- `sub1_side/server/dualsense_worker.py` (신규) — pygame.joystick PS5 컨트롤러
  폴링(50Hz). L-stick → INSPECT pan/tilt(±70°), L2/R2 → zoom, D-pad → 전·후·
  좌·우 strafe, R-stick L/R → yaw, ×=stop_toggle, △=sortie, ○=home.
- `main_side/camera_info_publisher.py` (신규) — 3-카메라(rear/inspect/overhead)
  CameraInfo 1Hz latched(TRANSIENT_LOCAL). `fx=(W/aperture_mm)*focal_mm`
  공식, plumb_bob D=0.
- `main_side/mission_echo.py` (신규) — `/mission_command` rclpy 사이드카,
  Isaac console.log 에 명령 수신 echo (사용자 디버깅 요청 #7).
- `main_side/npc_relay.py` (신규) — `/npc/spawn` 등 NPC 명령 릴레이.
- `main_side/world_odom_tf_pub.py` (확장) — 기존 world→odom 외에 Go2→base
  identity static TF 추가 발행 (URDF 루트 link "base" 와 OG TF frame "Go2"
  매칭 — Lichtblick URDF 렌더링 실패 근본 원인).

**Go2 전환 (camera_publisher / go2_controller):**
- `main_side/camera_publisher.py` (대수정)
  - SPOT_PRIM/SpotController 제거 → `/World/Go2` + Go2WtwController 호출.
  - 카메라: front 제거, **rear/inspect/overhead 3-카메라** 구성.
    rear=`/World/Go2/base/camera_rear`(-0.22, 0, 0.06),
    inspect=`/World/Go2/base/camera_inspect` (gimbal, pan/tilt ±70° clamp,
    base body roll/pitch 보정 stabilization),
    overhead=`/World/Overhead_Camera` (Go2 child 가 아닌 world 직속,
    매 step `_update_overhead_xform()` 으로 xy 동기 + North-up 고정).
  - `_update_inspect_xform()` — `q_stab = qy(-pitch)*qx(-roll)`,
    `q_total = q_stab * q_user_base * _Q_FRONT` (base frame yaw/pitch).
  - 자동 명시 spawn (212.8, 890.53, 5.0), `GP_GO2_NAV=0` 가드로 NAV 분리.
- `main_side/go2_controller.py` (Go2WtwController) — walk-these-ways RL 정책
  (42-dim obs × 15-step history = 630, JIT adaptation_module+body,
  PD kp=25/kd=0.6, action_scale 0.25, hip ×0.5). standstill clamp 포함.

**Web (next.js 14):**
- `sub1_side/web/components/ImmersiveCameraView.tsx` (신규) — `ssr:false`
  next/dynamic wrapper.
- `sub1_side/web/components/ImmersiveCameraViewClient.tsx` (신규) — Spot SDK
  fisheye sphere wrapping 패턴 차용. `@react-three/fiber@8.18` +
  `@react-three/drei@9.122` + `three@0.184` (R18 호환 핀). SphereGeometry
  inside-out(BackSide) 에 3-카메라 VideoTexture 섹터 매핑 (rear:180°,
  inspect:0°, overhead:88° pitch), 중앙 Go2 silhouette (box+legs+head 노랑),
  OrbitControls, scanline overlay.
- `sub1_side/web/components/BaseMovementPanel.tsx` (신규) — quadruped_example
  base_command 누적 패턴, 8-방향 + WASD/QE/Space + 속도 슬라이더 (100ms POST).
- `sub1_side/web/components/DualSenseStatus.tsx` (신규) — 게임패드 연결/키맵.
- `sub1_side/web/components/TripleCameraView.tsx` (신규, 메인) — rear/inspect/
  overhead MJPEG 3-panel.
- `sub1_side/web/components/{TopicHealthMonitor,RawJsonInspector}.tsx` (신규,
  debug 페이지) — `/c2/sample` 1Hz 폴링 → rx 카운터·publishers·env·hint 표시
  + raw JSON 인스펙터.
- `sub1_side/web/components/NpcSpawnButton.tsx` (신규) — NPC fwd/drop/count
  + 소환.
- `sub1_side/web/lib/api.ts` — `getApiBase()` 런타임 함수(SSR `typeof window`
  guard), `LICHTBLICK_URL` export 추가.
- `sub1_side/web/app/page.tsx` — DualCameraView/ImmersiveCameraView 분리,
  ROBOT CONTROL 컨테이너 안에 INSPECT CAM + BASE MOVEMENT 가로 2-column.
- `sub1_side/web/app/debug/page.tsx` — Lichtblick iframe 8col + Immersive
  4col + TopicHealthMonitor + RawJsonInspector + DualSenseStatus +
  DiagnosticsStrip + EventLog 12-column grid.

**Lichtblick layout (`sub1_side/lichtblick/layout.json`):**
- 12 패널 + 4 userNodes (patrol_mode_extractor, battery_extractor,
  intruders_to_scene, landmarks_to_scene) — String JSON → SceneUpdate.
- `3D!go2` 레이어: go2-urdf (http://192.168.10.94:8766/go2_description/
  urdf/go2.urdf), follow base, /tf, /robot/odom, /cam/front/points
  PointCloud Z-turbo.
- 두 데이터 소스 동시 연결 가능: `ws://host:8765` (foxglove_bridge — 모든
  ROS topic) + `ws://host:8767` (SDK — native 시각화).

**ros_bridge / safety_filter 변경:**
- `sub1_side/server/ros_bridge.py` — pub_cmd_vel 에 PAUSED 가드 (race fix),
  front 카메라 구독 제거, inspect/overhead 추가, YOLO 추론을 front→inspect
  카메라로 이동.
- `sub1_side/server/cmd_vel_safety_filter.py` — `MUTE_MODES = {"PAUSED"}`
  (IDLE 제거 — teleop freedom 회복).

**Patrol / 기본 좌표:**
- `sub1_side/server/nav2_patrol.py` — DEFAULT_HOME=(212.8, 890.53),
  **DEFAULT_GOAL=(287.59, 1129.728)** (구 620.36, 499.72 폐기).
- `main_side/bake_go2_recon_map.sh` — 신 AABB 재베이크 헬퍼.

**환경/스크립트:**
- `~/.bashrc` `cobot3-start_all` — 신규 사이드카 추가 (mission_echo,
  npc_relay, urdf_server, camera_info_publisher, foxglove_sdk_publisher,
  dualsense_worker). 강력 좀비 정리 (SIGTERM→2s→SIGKILL 2-pass). env:
  `GP_GO2_NAV=0`, `GP_GO2_SETTLE=500`.
- `~/.bashrc` `sb` 별칭 — `source ~/.bashrc`.
- `~/.config/cobot3/fastdds_web.xml` — __MAIN_PC_IP__ 치환 + 127.0.0.1
  interfaceWhiteList 추가 (cross-PC discovery 실패 fix).

**핵심 결함 수정 모음:**
- inspect 카메라 보행 중 흔들림 → `_update_inspect_xform()` stabilization.
- inspect pan/tilt 가 roll 로 보임 → base frame yaw/pitch 합성.
- URDF mesh Lichtblick 미렌더 → Go2→base identity static TF 추가.
- `/c2/sample` 토픽 rx all=0 → `ros.br._node._rx` 잘못된 path → `ros._node._rx`.
- SSR 빌드 `window not defined` → `getApiBase()` typeof window guard.
- R3F 9.x 런타임 "Cannot read 'S'" → 8.18 + drei 9.122 (R18 호환) 다운그레이드.
- 정지/재개 버튼 race → ros_bridge PAUSED 가드 + safety_filter mute set
  재설계.

---

## 2026-05-20

### 웹 메인 페이지 레이아웃 시각 위계 재정렬
**변경 파일:** `sub1_side/web/app/page.tsx` (수정), `dev-docs/sub1-side.md` (수정)
- 좌·우 2-column → 4 섹션 stack (HERO / CONTROLS / ALERTS / FOOTER)
- HERO: DualCameraView + MapTrack (xl 2-column, min-h 420px) — 시각적 dominant
- CONTROLS: mission · movement · inspector 3-column (xl breakpoint)
- legacy TELEOP/BASE MOVEMENT 토글 버튼은 푸터로 이동
- AlertsLog + AnimalAlertsLog 단일 row (lg 2-column) 로 통합 표시
- 다른 컴포넌트 내부 변경 없음, panel/panel-hd/phos 변수 유지
- `npm run build` 통과 (page 9.32 kB / First Load 96.4 kB)

### Go2 정찰 신사양 통합 (단일 미션 4-mode FSM + BaseMovement + YOLO 0.7)

**사용자 요구사항 (8개):**
1. spawn/home=(212.8, 890.53, 5.0)
2. 수색지=(620.36, 499.72, 52.138)
3. 도착 판정: 사각형 ±10m 박스
4. 웹 teleop 추가 보행 (8-방향, quadruped_example 패턴 차용)
5. 기존 검증된 통신 그대로
6. 비동기 명령 수신 (이동중 home/stop/resume 즉시 반응)
7. 명령 수신 시 Isaac console echo (디버깅)
8. YOLO conf 0.7 + COCO 80 클래스 bbox 표시

**변경 파일:**

- `sub1_side/server/nav2_patrol.py` (재작성) — 4-mode FSM
  (IDLE/PATROL/HOME/PAUSED), HOME/GOAL/ARRIVE_HALF 파라미터, 도착 ±10m 사각
  판정, stop_burst timer 10Hz×2s, resume 시 보존된 mode·goal 재전송.
- `sub1_side/server/cmd_vel_safety_filter.py` (수정) — `/patrol_state` 구독,
  PAUSED/IDLE 진입 시 Nav2 입력 무시 + Twist(0) 강제(velocity_smoother 잔여 차단).
- `main_side/camera_publisher.py` (수정) — 명시 spawn (212.8, 890.53, 5.0),
  zone 분기 제거, landmarks dump 가 home/goal/arrive_box 단일 미션 포맷.
  메인 루프 100 step 마다 timeline.is_playing() 자가 복원.
- `main_side/mission_echo.py` (신규) — `/mission_command` rclpy 사이드카, stdout
  → Isaac console.log 캡처 (사용자 #7).
- `main_side/bake_go2_recon_map.sh` (신규) — 새 AABB(112.8-720.36 × 399.72-990.53,
  0.5 m/px) 로 gp_static 베이크 헬퍼.
- `sub1_side/server/config.py` (수정) — YOLO_CLASSES = COCO 80 전체,
  YOLO_ALERT_CONF=0.7, YOLO_ANIMAL_CLASS_IDS 추가.
- `sub1_side/server/yolo_infer.py` (수정) — predict conf=YOLO_ALERT_CONF (0.7).
- `sub1_side/server/app.py` (수정) — `/robots/{rid}/cmd_vel` 가 linear_y(strafe)
  도 수신 (quadruped 8-방향).
- `sub1_side/server/ros_bridge.py` (수정) — pub_cmd_vel(vy=0.0) 시그니처 확장,
  Twist.linear.y 발행.
- `sub1_side/web/components/BaseMovementPanel.tsx` (신규) — quadruped_example
  의 base_command 누적 패턴 차용, 8-방향 버튼 + WASD/QE/Space 키보드, 100ms
  POST 주기.
- `sub1_side/web/app/page.tsx` (수정) — BaseMovementPanel 기본 노출, TeleopPad
  은 legacy 토글로 유지.
- `~/.bashrc` (수정) — MAIN 분기 cobot3-start_all 에 mission_echo·urdf_server
  자동 기동 추가, down_all PAT 에 동일 패턴 추가.

**WHY (핵심 결함 수정):**
- 정지 버튼 무동작: velocity_smoother 가 nav2_patrol 의 1-shot Twist(0) 통과
  후 20Hz 잔여 발행 → safety_filter 가 그대로 통과시킴 → robot 보행 지속.
  **Fix**: nav2_patrol PAUSED 모드 + 10Hz×2s stop_burst, safety_filter 가
  /patrol_state 구독해 PAUSED/IDLE 시 입력 무시 + Twist(0) 강제.
- simTime 동결: world.reset() 후 timeline.play() 1회만 호출, GUI 일시정지
  영향. **Fix**: 100 step 마다 is_playing() 확인 → 자동 재시작.

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
