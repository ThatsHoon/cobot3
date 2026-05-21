# main_side — Isaac Sim PC

> 2026-05 Spot+팔 → **Unitree Go2** 전환 완료. spot_controller.py 와
> spot_isaac.urdf 는 legacy 잔재(미사용). 현재 활성 컨트롤러는
> `go2_controller.py` (walk-these-ways RL locomotion).

## 파일 목록

| 파일 | 역할 |
|------|------|
| `camera_publisher.py` | 메인 Isaac Sim standalone app; OG sensor_bridge 구성·실행, Go2 spawn, 3-카메라(rear/inspect/overhead) |
| `go2_controller.py` | Go2WtwController (walk-these-ways RL JIT) 래퍼; physics 콜백으로 12-DOF 보행 구동 + standstill clamp |
| `go2_wtw_mcp.py` | walk-these-ways MCP 제어 보조 (개발용) |
| `import_go2_unitree.py` | Unitree go2.usd 임포트 헬퍼 (1회 사용) |
| `telemetry_bridge_node.py` | /robot/odom → /robot/gps + /robot/state 파생 (5Hz) |
| `video_degrade_node.py` | 카메라 영상 5fps JPEG q50 압축 (rear/inspect/overhead 3 인스턴스) |
| `camera_info_publisher.py` | **(신규)** 3-카메라 CameraInfo 1Hz latched(TRANSIENT_LOCAL) — Lichtblick 3D 카메라 frustum/투영 |
| `mission_echo.py` | **(신규)** `/mission_command` rclpy 사이드카 — Isaac console.log echo (디버깅) |
| `npc_relay.py` | **(신규)** `/npc/*` 명령 릴레이 (NPC 스폰/제거) |
| `world_odom_tf_pub.py` | world→odom + **Go2→base** 2개 static TF 발행 (URDF 루트 매칭 fix) |
| `landmarks_pub.py` | `/scene/landmarks` JSON latched 발행 |
| `inspect_relay.py` | `/robot/inspect/command` 사이드카 — `/tmp/cobot3_inspect_cmd.json` dump (Isaac 5.1 OG String sub 미등록 우회) |
| `publish_robot_description.py` | /robot_description URDF 토픽 발행 (Foxglove 3D) |
| `run_urdf_server.sh` | URDF HTTP 서버 :8766 (CORS, Lichtblick urdf URL 소스) |
| `bake_gp_static_map.py` / `bake_go2_recon_map.sh` | Nav2 정적 맵 베이크 (PhysX raycast 0.5m/px) |
| `bake_friction.py` / `gp_path_tool.py` | 마찰/지면 도구 |
| `go2_description/` | Go2 URDF + DAE 메시 (urdf_server 서빙 루트) |
| `go2_policy/` | walk-these-ways JIT 정책 (adaptation_module · body) |
| `go2_unitree/` | Unitree Go2 원본 자산 |
| `go2_nav_inject.py` | Nav2 goal 직접 주입 헬퍼 |
| `scene/gp_scene.usd` | 루트 씬 (Go2 ref, 산악 지형, 철조망 울타리) |
| `scene/maps/gp_static.{pgm,yaml}` | Nav2 정적 맵 (재베이크 산출물) |
| `fastdds_no_shm.xml` | FastDDS UDP-only 프로파일 (SHM 비활성 — Isaac↔System 호환) |
| `fastdds_main.xml` | FastDDS 2-PC LAN 프로파일 템플릿 (__C2_PC_IP__ 치환 필요) |
| `spot_controller.py` / `spot_isaac.urdf` | **legacy** (Spot 잔재, 미참조) |

---

## camera_publisher.py

### 주요 상수

| 상수 | 값 | 환경변수 | 목적 |
|------|----|---------|------|
| `_HEADLESS` | bool | `GP_HEADLESS` (0=GUI, 1=headless) | Isaac 창 표시 여부 |
| `SCENE` | `scene/gp_scene.usd` | `GP_SCENE` | 로드할 USD 씬 경로 |
| `_OVERRIDES_USD` | `scene/overrides/gp_scene_overrides.usda` | `GP_USE_OVERRIDES` (1=on, 0=off) | 물리 보강 sublayer (2026-05-21). 자세한 항목은 [scene-overrides.md](scene-overrides.md). |
| `GO2_PRIM` | `/World/Go2` | — | Go2 루트 prim |
| `BASE_PRIM` | `/World/Go2/base` | — | Go2 기체 링크 |
| `CAM_REAR_PATH` | `/World/Go2/base/camera_rear` | — | 후방 카메라 prim |
| `CAM_INSPECT_PATH` | `/World/Go2/base/camera_inspect` | — | 검사(짐벌) 카메라 prim |
| `CAM_OVERHEAD_PATH` | `/World/Overhead_Camera` | — | 오버헤드 카메라 (world 직속, Go2 child 아님) |
| `GRAPH` | `/World/Graphs/sensor_bridge` | — | OmniGraph 경로 |
| `DOMAIN` | 130 | `ROS_DOMAIN_ID` | ROS2 도메인 |
| `_TELEM` | True | `GP_ROS2_TELEM=1` | 텔레메트리 OG 활성 |
| `_CMD` | True | `GP_ROS2_CMD=1` | cmd_vel 구독 활성 |
| `GP_GO2_NAV` | 0 | env | 1=set_nav_goal 활성, 0=Nav2 외부 단독 사용 |
| `GP_GO2_SETTLE` | 500 | env | spawn 후 NAV P-ctrl 진입 settle step 수 |
| `GP_GO2_CMD_MODE` | (없음) | env | "cal"=캘리브레이션 (vx=0.5 고정 + nav P) |
| `_GO2_HOME_XYZ` | (212.8, 890.53, 5.0) | `GP_GO2_SPAWN_X/Y/Z` (2026-05-21) | Go2 spawn/home (world 좌표). `world_odom_tf_pub.py` 와 동일 env — SSOT. |
| `Clock` 발행 주기 | 50 Hz (OnPlaybackTick 의 render_dt=1/50 기반) | — | `ROS2PublishClock` 은 자체 publishRate input 없음 — tick 펄스로 구동. Nav2 controller 10Hz 의 5× 마진. |

### OmniGraph 구조 (`/World/Graphs/sensor_bridge`)

```
OnTick (OnPlaybackTick)  — render_dt=1/50 → 50Hz 펄스
  ├─→ RPRear    → CamRear         /cam/rear/rgb     (Image, BEST_EFFORT)
  │              → CamRearDepth    /cam/rear/depth   (Image 32FC1, BEST_EFFORT)
  │              → CamRearPCL      /cam/rear/points  (PointCloud2, BEST_EFFORT)
  ├─→ RPInspect → CamInspect      /cam/inspect/rgb  (Image, BEST_EFFORT) ★YOLO 입력
  ├─→ RPOverhead→ CamOverhead     /cam/overhead/rgb (Image, BEST_EFFORT)
  ├─→ LegJS                       /robot/leg_joint_states (JointState, RELIABLE)
  ├─→ Odo → OdoPub                /robot/odom (Odometry, RELIABLE)
  ├─→ TF                          /tf (TFMessage, RELIABLE — Nav2 호환)
  └─→ SubCmd  ←                   /robot/cmd_vel (Twist, RELIABLE)
        ↓ in-process attribute read (_apply_cmd)
        → Go2WtwController.set_cmd_vel()

Ctx (ROS2Context) — domain_id=130 → 모든 ROS2 노드에 공급
SimTime (IsaacReadSimulationTime) → LegJS/OdoPub/TF 타임스탬프 공급
Odo (IsaacComputeOdometry) — chassisPrim=/World/Go2/base, chassisFrameId=Go2
```

> 사이드카가 CameraInfo 1Hz latched 발행 — `main_side/camera_info_publisher.py`
> (TRANSIENT_LOCAL). `fx = (W/aperture_mm) × focal_mm`, plumb_bob D=0.

### 카메라 짐벌 / 안정화 (2026-05-21)

- **inspect 카메라**: 매 step `_update_inspect_xform()` 가 base body roll/
  pitch 를 보정 (`q_stab = qy(-pitch)*qx(-roll)`). pan/tilt 명령은 base
  frame 의 yaw/pitch 로 적용: `q_total = q_stab * q_user_base * _Q_FRONT`.
  pan/tilt 각각 ±70° clamp.
- **overhead 카메라**: world 직속(`/World/Overhead_Camera`) 으로 분리.
  매 step `_update_overhead_xform()` 가 Go2 base.xy 만 따라가고 yaw/roll/
  pitch 는 고정(North-up) — 들썩임 제거.

**단일 빌드 원칙:** 모든 OG 노드를 하나의 `og.Controller.edit()` 호출로 생성.
증분 edit 시 OmniGraphError 발생 → 금지.

**render=True 필수:** `world.step(render=True)` 로 타임라인을 구동해야
OnPlaybackTick 펄스가 발생하고 OG ROS2 노드가 실행됨.

### QoS 프로파일 (8-key JSON, 필수)

```python
_REL_QOS    = '{"history":"keepLast","depth":10,"reliability":"reliable",\
                "durability":"volatile","deadline":0.0,"lifespan":0.0,\
                "liveliness":"systemDefault","leaseDuration":0.0}'
_SENSOR_QOS = '{"history":"keepLast","depth":5,"reliability":"bestEffort",\
                "durability":"volatile","deadline":0.0,"lifespan":0.0,\
                "liveliness":"systemDefault","leaseDuration":0.0}'
```

**주의:** 8개 키 모두 필수. 일부 생략 시 파서 거부 → 엔드포인트 미생성.

### 카메라 배치 (2026-05-21, 3-카메라)

| 카메라 | prim 경로 | 위치 (xyz) | 회전 (rotateXYZ) | 초점거리 | 비고 |
|--------|-----------|-----------|----------------|---------|------|
| 후방 (real) | `/World/Go2/base/camera_rear` | (-0.22, 0.0, 0.06) | (0.0, 90.0, 0.0) | 10.5mm | rear MJPEG, 실시간 영상 |
| 검사 (inspect) | `/World/Go2/base/camera_inspect` | (+0.22, 0.0, 0.10) | stabilization | 10.5mm | 짐벌 pan/tilt ±70°, YOLO 입력 |
| 오버헤드 (overhead) | `/World/Overhead_Camera` | base.xy + (0,0,Δz) | North-up 고정 | (광각) | world 직속, Go2 child 아님 |

> 카메라 내부파라미터 D455 (focalLength 10.5mm + horizontalAperture 20.955
> → ~90° FOV). 구 front 카메라는 제거 — inspect 가 YOLO 입력 역할 인수.
> 구 Spot 잔재 1.93mm 초광각도 제거.

**UsdGeom.Camera** API로 생성 (rsd455.usd 시각 메시 불필요).
**CameraInfo** 발행은 OG 대신 사이드카 `camera_info_publisher.py` 1Hz
latched.

### 로봇 USD 교체 로직 (Go2)

```python
_robot_prim = stage.GetPrimAtPath("/World/Go2")
refs = _robot_prim.GetReferences()
refs.ClearReferences()
refs.AddReference(str(_HERE / "go2_unitree" / "go2.usd"))
```
Unitree Go2 자산은 로컬 `main_side/go2_unitree/go2.usd` 에서 직접 ref.
(walk-these-ways 정책과 함께 사용.)

---

## go2_controller.py

### 클래스: `Go2WtwController` (walk-these-ways RL JIT)

| 메서드 | 설명 |
|--------|------|
| `__init__(prim_path)` | go2_policy JIT(adaptation_module + body) 로드, 12-DOF 바인딩 |
| `set_cmd_vel(vx, vy, wz)` | 텔레오퍼레이션 속도 명령 + 타임스탬프 |
| `set_nav_goal(x, y)` | 내비게이션 목표 (GP_GO2_NAV=1 시) |
| `clear_nav_goal()` | 내비게이션 목표 해제 |
| `on_physics_step(dt)` | physics 콜백 — 초기화→settle→중재→정책 |
| `_command()` | cmd 9-12 벡터 생성 (vx/vy/wz + 게이트 + step_freq/footswing 등) |
| `_arbitrate()` | **active_teleop(±1e-6, TTL 0.5s) > nav P 제어(settle 후) > standstill** |
| `_nav_p_ctrl()` | 단순 P 제어 (vx_max, wz_sat, 도착 임계) |
| `_forward(dt, cmd)` | 42-dim obs × 15-step history → JIT 정책 → torque (PD kp=25/kd=0.6) |

**DOF / 정책 사양:**
- 12-DOF (Go2: FL/FR/RL/RR × hip/thigh/calf)
- obs=42, history_len=15 → MLP body 입력 630-dim
- action_scale=0.25, hip ×0.5
- 경사면 보행 가능 (D2 clamp 없음)

**중재 로직 + standstill clamp (2026-05-21):**
```
active_teleop = (TTL<0.5s) AND (|vel_cmd| > 1e-6) → 직접 사용
nav_goal 설정됨 AND settle 완료                    → P제어로 속도 계산
그 외                                              → 정지 의도
  → if not active_teleop: cmd[4]=0 (step_freq), cmd[9]=0 (footswing)
  → walk-these-ways 가 멈춤 (drift 방지)
```

**환경 변수 분기:**
- `GP_GO2_CMD_MODE=cal` — vx=0.5 고정, nav P 도 함께 (보행 캘리브레이션).
- `GP_GO2_NAV=0` (기본) — 컨트롤러 내부 NAV 비활성화 (Nav2 stack 단독).
- `GP_GO2_SETTLE=500` — spawn 후 NAV P-ctrl 가 발동되기까지의 step 수.

> **legacy** `spot_controller.py` 는 더 이상 호출되지 않음. 동일 위치 보존만.

---

## telemetry_bridge_node.py

**구독:** `/robot/odom` (Odometry, RELIABLE)
**발행:** `/robot/gps` (NavSatFix, 5Hz), `/robot/state` (String JSON, 5Hz)

### sim-GPS 변환 (WGS84)
```
원점: LAT0=38.30°N, LON0=127.50°E, ALT0=200m
dlat = (y_m / 6378137) × (180/π)
dlon = (x_m / (6378137 × cos(LAT0°))) × (180/π)
```

### /robot/state JSON 스키마
```json
{
  "mode": "patrol",
  "gait": "walk",
  "battery": 95.3,
  "waypoint": 0,
  "extra": {}
}
```
- `gait`: 속도 0.05m/s 미만 → "stand", 이상 → "walk"
- `battery`: 100% - (경과분 × 0.1%/분), 최소 20%
- `mode`: 항상 "patrol" (고정)

---

## video_degrade_node.py

**인스턴스 3개** (run_degrade.sh에서 환경변수로 분기, 2026-05-21):

| 인스턴스 | DEGRADE_IN | DEGRADE_OUT | 용도 |
|---------|-----------|------------|------|
| rear     | `/cam/rear/rgb`     | `/c2/rear/compressed`     | 후방 카메라 (real) |
| inspect  | `/cam/inspect/rgb`  | `/c2/inspect/compressed`  | 검사 카메라 (YOLO 입력) |
| overhead | `/cam/overhead/rgb` | `/c2/overhead/compressed` | 오버헤드 카메라 (North-up) |

**처리 파이프라인:**
1. 수신: `sensor_msgs/Image` (BEST_EFFORT, depth=5)
2. numpy 변환 (rgb8/bgr8/rgba8/bgra8 처리)
3. 리사이즈 640×360 (INTER_AREA)
4. JPEG 인코딩 (quality=50)
5. 발행: `sensor_msgs/CompressedImage` (BEST_EFFORT)
6. 스로틀: TARGET_FPS=5.0 Hz

---

## 씬 구조 (`scene/gp_scene.usd`, 2026-05-21)

```
/World
├── Terrain         ← terrain.usdz (산악, PBR 텍스처) — physics_material dynFric=0.8
├── DomeLight_01    ← HDRI 환경광
├── Looks / Physics_Materials  (material 컨테이너)
├── Cube            ← (비활성, 디버그 잔재)
├── Watchtowers     ← 정적 props (6 mesh)
├── Fence           ← 정적 props (1650 mesh — instancing 후보)
├── Doro            ← 정적 props (12 mesh)
├── spike_ball / banana_obstacle / Landmine  ← 동적 장애물 (rigidBody, mass 2.0/0.3/1.0)
├── Go2_starting_point / militarybase / radar_tower  ← 시각화 마커 (collisionEnabled=false)
├── Go2             ← go2.usd (로컬 main_side/go2_unitree/go2.usd ref) @ spawn (212.8, 890.53, 5.0)
│   └── base
│       ├── camera_rear      (UsdGeom.Camera, 후방)
│       └── camera_inspect   (UsdGeom.Camera, 짐벌 stabilization)
├── Overhead_Camera (UsdGeom.Camera, world 직속 — Go2 child 아님)
└── Graphs
    └── sensor_bridge  (OmniGraph — Clock 60Hz, OdoPub, LegJS, TF [BASE_PRIM])
```

**에셋 경로 규칙:** 모두 `scene/` 상대 경로. `/home/...` 절대경로 금지.
Go2 USD = 로컬 ref (`main_side/go2_unitree/go2.usd`).

### 9개 신규 prim 의 collider/material binding 정책 (2026-05-21)

`scene/overrides/gp_scene_overrides.usda` sublayer + `camera_publisher.py` safety-net 가 분담. 상세는 [scene-overrides.md](scene-overrides.md) / [physics-scene-audit.md](physics-scene-audit.md).

| Prim | 분류 | root 속성 (sublayer) | leaf Mesh (safety-net) | mass |
|---|---|---|---|---|
| spike_ball | 동적 | `collisionEnabled=true` | `MeshCollisionAPI(convexHull)` + Terrain material binding | 2.0 kg |
| banana_obstacle | 동적 | `collisionEnabled=true` | `convexHull` + binding | 0.3 kg |
| Landmine | 동적 | `collisionEnabled=true` | `convexHull` + binding | 1.0 kg |
| Watchtowers | 정적 | `MaterialBindingAPI` schema | `MeshCollisionAPI(none)` + binding | — |
| Fence | 정적 | 동일 | `none` + binding | — |
| Doro | 정적 | 동일 | `none` + binding | — |
| Go2_starting_point | 시각 마커 | `collisionEnabled=false` | (collider 생성 안 함) | — |
| militarybase | 시각 마커 | 동일 | (skip) | — |
| radar_tower | 시각 마커 | 동일 | (skip) | — |

> Cube 는 정찰선 밖 디버그 잔재 — sublayer + gp_scene.usd 양쪽에 `active=false` 적용 (2026-05-21).

## camera_info_publisher.py (2026-05-21 신규)

3-카메라 CameraInfo 1Hz latched(TRANSIENT_LOCAL) 발행. Isaac OG ROS2 노드는
fx/fy 계산 잡음이 있어 사이드카로 분리.

```python
fx = (W / aperture_mm) * focal_mm   # focal 10.5mm, aperture 20.955mm
fy = (H / aperture_mm) * focal_mm
cx, cy = W/2, H/2
D  = [0]*5            # plumb_bob, 왜곡 없음 (Isaac pinhole)
```

토픽: `/cam/{rear,inspect,overhead}/camera_info` (CameraInfo, RELIABLE +
TRANSIENT_LOCAL). Lichtblick 3D `cameraInfoTopic` 으로 frustum 렌더.

## mission_echo.py · npc_relay.py · world_odom_tf_pub.py · inspect_relay.py

- `mission_echo.py` — `/mission_command` 구독, stdout 으로 Isaac console 에
  미션 명령 echo (사용자 디버깅 요청). rclpy 사이드카.
- `npc_relay.py` — `/npc/spawn` 등 NPC 명령을 카메라 publisher 의 내부
  스폰 함수로 릴레이.
- `world_odom_tf_pub.py` — 2개 static TF 발행 (모두 RELIABLE +
  TRANSIENT_LOCAL):
  - `world → odom` (identity) — Nav2 tf_buffer 가 요구
  - `Go2 → base` (identity) — URDF 루트 link "base" 와 OG TF frame "Go2"
    매칭 (Lichtblick URDF 렌더링 정상화)
- `inspect_relay.py` — `/robot/inspect/command` String JSON 구독, mtime poll
  형식으로 `/tmp/cobot3_inspect_cmd.json` 에 dump → camera_publisher 가 매
  step 폴 (Isaac 5.1 OG ROS2SubscribeString 미등록 우회).
