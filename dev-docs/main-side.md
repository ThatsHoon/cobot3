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
| `video_degrade_node.py` | 카메라 영상 5fps JPEG q50 압축 (rear/inspect/overhead + TP_A~D = 7 인스턴스). 2026-05-24: `DEGRADE_IN` env 필수 (front 카메라 잔재 default 제거) |
| `depth_degrade_node.py` (2026-05-24 신규) | TP depth 320×180 PNG 16UC1 압축 4 인스턴스. LAN depth 트래픽 9MB/s → ~0.4MB/s |
| `scene/assets/objects/` (2026-05-26 신규) | 접근 오브젝트 USDZ 6개 (boar_walk, wolf_animated, deer_low_poly_animated, drone, person, soldier). `.gitignore` 대상, `scene_pack.sh` 공유 |
| `camera_info_publisher.py` | 3-카메라 CameraInfo TRANSIENT_LOCAL latched. 2026-05-24: 1Hz timer 제거 → 1회 발행 + 60s 보호 |
| `mission_echo.py` | **(신규)** `/mission_command` rclpy 사이드카 — Isaac console.log echo (디버깅) |
| `npc_relay.py` | **(신규)** `/npc/*` 명령 릴레이 (NPC 스폰/제거) |
| `world_odom_tf_pub.py` | world→odom + **Go2→base** 2개 static TF 발행 (URDF 루트 매칭 fix) |
| `landmarks_pub.py` | `/scene/landmarks` JSON latched 발행 |
| `nav2_patrol.py` | PATROL/HOME/ROUTING FSM, ZoneRouter 라우팅 액션 클라이언트. 2026-05-24: `_sp_world` 캐시 + `_on_odom` 에서 odom→world 변환 (self._pose 일관) |
| `inspect_relay.py` | `/robot/inspect/command` 사이드카 — `/tmp/cobot3_inspect_cmd.json` dump (Isaac 5.1 OG String sub 미등록 우회) |
| `publish_robot_description.py` | /robot_description URDF 토픽 발행 (Foxglove 3D) |
| `run_urdf_server.sh` | URDF HTTP 서버 :8766 (CORS, Lichtblick urdf URL 소스) |
| `bake_gp_static_map.py` / `bake_go2_recon_map.sh` | Nav2 정적 맵 베이크 (PhysX raycast 0.5m/px) |
| `bake_friction.py` / `gp_path_tool.py` | 마찰/지면 도구 |
| `scene/go2_description/` | Go2 URDF + DAE 메시 (urdf_server 서빙 루트) |
| `scene/go2_policy/` | walk-these-ways JIT 정책 (adaptation_module · body) |
| `scene/go2_unitree/` | Unitree Go2 원본 자산 |
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
| `_GO2_HOME_XYZ` | Routing_Zones/StartingPoint (194.56, 837.70, 5.02) | `GP_GO2_SPAWN_X/Y/Z` | Go2 spawn/home. stage 로드 후 `/World/Routing_Zones/StartingPoint` Xform 을 읽어 자동 설정 (2026-05-22). |
| `_GO2_GOAL_XYZ` | Routing_Zones/Standard_Point (199.09, 892.60, 4.52) | `GP_GO2_GOAL_X/Y/Z` | 시동 시 이동 목표. `/World/Routing_Zones/Standard_Point` Xform 으로 자동 설정 (2026-05-22). arrive_box=2.0m. |
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
  - **2026-05-24 부호 컨벤션**: `q_user_base = _qz(-pan) * _qy(-tilt)` 로 변경.
    웹/DualSense 의 "오른쪽=+pan, 위=+tilt" 직관과 정합 (수학적 right-hand rule
    역방향 보정). `look_at` 절대 좌표는 `pan = -atan2(dy, dx)` 로 호환.
- **overhead 카메라**: world 직속(`/World/Overhead_Camera`) 으로 분리.
  매 step `_update_overhead_xform()` 가 Go2 base.xy 만 따라가고 yaw/roll/
  pitch 는 고정(North-up) — 들썩임 제거.
  - **2026-05-24 확장**: 고도 100→**200m**, VAP=`_HAP`=20.955mm (정방형
    640×640 ↔ 지상 ±262m 정합). TACTICAL MAP 배경으로 사용. 이전 VAP=11.79mm
    (16:9) 라 수직 74m·수평 131m 비대칭 + 캔버스 ±60m 미흡 문제 해결.

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

| 카메라 | prim 경로 | 위치 (xyz, base 기준) | 회전 | 초점거리 | 비고 |
|--------|-----------|---------------------|----|---------|------|
| 후방 (real) | `/World/Go2/base/camera_rear` | (-0.235, 0.0, **0.40**) (2026-05-24 z +30cm) | `_Q_REAR` (시선 -X, up +Z) | 10.5mm | rear MJPEG |
| 검사 (inspect) | `/World/Go2/base/camera_inspect` | (+0.235, 0.0, **0.40**) (2026-05-24 z +30cm) | `_Q_FRONT` + stabilization | 10.5mm | 짐벌 pan/tilt ±70°, YOLO 입력 |
| 오버헤드 (overhead) | `/World/Overhead_Camera` | base.xy + (0,0,**200**) (2026-05-24 100→200m) | North-up 고정, identity quat | focal=8mm, HAP=VAP=20.955mm | world 직속, ±262m 지상 정방형 |
| TP_A~D 전술 (2026-05-23) | `/World/Tactical_Fixed_Cameras/TP_*_Cam` | Tactical_Points + (0,0,8) | `_quat_camera_forward` | 6mm | 고정 관측, RGB+depth |

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
refs.AddReference(str(_HERE / "scene" / "go2_unitree" / "go2_unitree.usd"))
```
Unitree Go2 자산은 로컬 `main_side/scene/go2_unitree/go2_unitree.usd` 에서 직접 ref.
(walk-these-ways 정책과 함께 사용.)

### SingleArticulation 메인스레드 사전 초기화

GPU PhysX 모드에서 `physics callback 내 initialize()` 는 GPU PhysicsSimulationView 를
생성하지 못해 ~1000 step 후 `get_joint_positions()` → 0-dim array → `IndexError` 폭주.
`world.reset()` 직후 메인 스레드에서 미리 초기화하고 `_ctrl._art` 에 주입한다.

```python
_pre_art = SingleArticulation(prim_path=ART_PRIM)
_pre_art.initialize()
if len(list(_pre_art.dof_names)) >= 12:
    _ctrl._art = _pre_art   # 주입 성공 → 콜백 내 deferred-init 스킵
```

`dof_names < 12` 이면 콜백 폴백(기존 방식). `go2_nav_inject.py` 와 동일 패턴.

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
| `set_home_xyz(x, y, z)` | StartingPoint 좌표 등록 (camera_publisher 가 부트 시 호출) |
| `_tick_oob_check()` | 매 정책 tick — 물리폭발(angular>50rad/s, linear>30m/s) 또는 수직탈출(Z<-5 또는 Z>100) 감지 시 `_teleport_home()` |
| `_teleport_home()` | StartingPoint 로 비물리 teleport + 전체 정책/fall 상태 초기화 (10s cooldown) |

**DOF / 정책 사양:**
- 12-DOF (Go2: FL/FR/RL/RR × hip/thigh/calf)
- obs=42, history_len=15 → MLP body 입력 630-dim
- action_scale=0.25, hip ×0.5
- 경사면 보행 가능 (D2 clamp 없음)

**`_CMD_BASE` 튜닝 (2026-05-24 단차 통과 사양):**
| idx | 이름 | 값 | 효과 |
|-----|------|-----|------|
| 3 | body_height | **0.05** (← 0.0) | 몸체 +5cm, 발 클리어런스 ↑ |
| 4 | step_freq | **3.0** (← 3.6) | 스텝 주기 ↓ → 발 들기 시간 ↑ |
| 5 | gait phase | 0.5 | trot (대각쌍 교대) |
| 9 | footswing | **0.22** (← 0.15) | 발 들기 15→22cm. 22cm 단차까지 통과 |
| 12 | stance_w | 0.33 | 좌우 다리 간격 |
| 13 | stance_l | 0.45 | 앞뒤 다리 간격 (base 중심 회전) |

WHY: Nav2 명령 0.91 m/s 보내도 도로 단차 모서리에 발 걸려 실제 이동 0.09 m/s (90% 손실). 모두 walk-these-ways 학습 분포 끝단 내. 평탄지형 속도 ≈10% ↓ trade-off.

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

## 씬 구조 (`scene/gp_scene.usd`, 2026-05-22)

```
/World
├── Hill_terrain1 / Hill_terrain2  ← 산악 지형 (CollisionAPI 100%, physics_material dynFric=0.8)
├── DomeLight_01    ← HDRI 환경광
├── Sun             ← 방향성 광원
├── WeatherEffects  ← 날씨 파티클
├── Looks / Physics_Materials  (material 컨테이너)
├── Doro            ← 정적 props (12 mesh) — MaterialBindingAPI sublayer 적용
├── Go2_starting_point / militarybase  ← 시각화 마커 (collisionEnabled=false)
├── Fence_Waypoints ← 울타리 경로점 Xform 45개 (정렬: Xform → Xform_05 → ... → Xform_50)
├── Fence_Line      ← 철조망 19 세그먼트 (scene/assets/barbed_wire_fence.usdz, 2026-05-22)
│                      길이 5.9~11.9m, 높이 5.2m, Fence_Waypoints 궤적 추종
│                      xformOpOrder: [translate:world, rotateZ, scale, rotateX, translate:inner]
│                      GATE_THRESH=55m (Xform_50→Xform 162m 자연 장벽 스킵)
├── Routing_Zones   ← 경로 구역 Xform (총 16개, 2026-05-24 ComputeLocalToWorldTransform 추출)
│   ├── StartingPoint  @ (194.56, 837.70, 5.02) — Go2 spawn 기본값
│   └── Standard_Point @ (199.09, 892.60, 4.52) — 시동 시 Nav 목표 (arrive_box=2.0m)
├── Tactical_Points (2026-05-23) ← TP_A~D 4개 (전술 고정 카메라 위치)
├── Go2             ← go2.usd (로컬 main_side/scene/go2_unitree/go2.usd ref) @ spawn = StartingPoint
│   ├── base
│   │   ├── camera_rear      (UsdGeom.Camera, 후방, z=0.40 from 2026-05-24)
│   │   └── camera_inspect   (UsdGeom.Camera, 짐벌 stabilization, z=0.40)
│   └── radar (2026-05-24 추가)  ← visuals + collisions
├── Overhead_Camera (UsdGeom.Camera, world 직속 — Go2 child 아님, 200m + ±262m 정방형)
├── Tactical_Fixed_Cameras (2026-05-23) ← TP_A_Cam ~ TP_D_Cam (8m guard tower 상부)
├── scene_01 (2026-05-24 추가)         ← Forest Clearing Top Skybox (payload)
├── Extended_field (2026-05-24 추가)   ← Coast Road + Stylized Bush (89 자손)
├── Crouched_Walking (2026-05-24 추가) ← NPC 애니메이션 (16 자손)
├── traffic_sign (2026-05-24 추가)     ← 한국 도로 표지판 39종 (1110 자손)
└── Graphs
    └── sensor_bridge  (OmniGraph — Clock 50Hz, OdoPub, LegJS, TF [BASE_PRIM])
```

**에셋 경로 규칙:** 모두 `scene/` 상대 경로. `/home/...` 절대경로 금지.
Go2 USD = 로컬 ref (`main_side/scene/go2_unitree/go2.usd`).

### prim 별 sublayer override 정책 (2026-05-22)

`scene/overrides/gp_scene_overrides.usda` sublayer + `camera_publisher.py` safety-net 분담. 상세는 [scene-overrides.md](scene-overrides.md).

| Prim | 분류 | root 속성 (sublayer) | leaf Mesh (safety-net) |
|---|---|---|---|
| Doro | 정적 props | `MaterialBindingAPI` schema 사전 적용 | `MeshCollisionAPI(none)` + physics material binding |
| Go2_starting_point | 시각 마커 | `collisionEnabled=false` | (skip) |
| militarybase | 시각 마커 | `collisionEnabled=false` | (skip) |
| Fence_Line | 철조망 (정적) | 해당 없음 (MCP 직접 생성) | root prim CollisionAPI 적용 |

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

---

## M_Medical_01 캐릭터 애니메이션 (2026-05-22)

### 파이프라인 구조

NVIDIA Isaac Sim 의 SkelAnimation-based 캐릭터는 3개 레이어가 모두 있어야 동작한다:

```
SkelAnimation (Root/Pelvis/Spine_01/… 81 joints)
      ↓  Animation Graph 경유 (StateMachine: Idle/Walk/Sit/Talk)
ControlRig  (controlRig:retargetTags  — 소스→타깃 조인트 이름 매핑)
      ↓  리타게팅
Skeleton    (RL_BoneRoot/RL_Hip_L/… 101 joints)
```

`skel:animationSource` 에 SkelAnimation 을 직접 연결하면 Animation Graph 를 우회하므로
SkelAnimation 조인트(Root/Pelvis) 와 Skeleton 조인트(RL_BoneRoot) 가 0개 매칭 → 무동작.

### Biped_Setup.usd 레퍼런스 방식 (권장)

NVIDIA 공식 레퍼런스 캐릭터(`Isaac/People/Characters/Biped_Setup.usd`)를 현재 씬에
USD reference 로 추가하면 AnimationGraph + ControlRig + Skeleton 이 일체형으로 로드된다.

```python
# MCP execute_script 또는 Isaac Script Editor
import omni.usd
from pxr import Sdf, UsdGeom

stage = omni.usd.get_context().get_stage()
prim = stage.DefinePrim("/World/BipedSetup", "Xform")
prim.GetReferences().AddReference(
    "omniverse://localhost/NVIDIA/Assets/Isaac/4.5/Isaac/People/Characters/Biped_Setup.usd")
UsdGeom.XformCommonAPI(prim).SetTranslate((194.5, 837.7, 5.0))
```

USD reference 해석 규칙:
- 참조 USD 의 `defaultPrim = "World"` 이므로 `/World/CharacterAnimation/AnimationGraph` 가
  `/World/BipedSetup/CharacterAnimation/AnimationGraph` 로 마운트됨.

### Animation Graph 연결 (UI)

1. Stage 트리에서 M_Medical_01 (또는 BipedSetup) 의 **SkelRoot prim** 선택.
2. 상단 메뉴 **Add → Animation Graph** (omni.anim.graph.ui 확장 필요 — 없으면 아래 참조).
3. 다이얼로그에서 `/World/BipedSetup/CharacterAnimation/AnimationGraph` 선택.
4. 재생(Play) → 캐릭터가 Idle 자세 유지 → Walk 클립으로 전환 가능.

> **Add → Animation Graph 메뉴가 없으면:** `isaacsim.exp.full.kit` 에 omni.anim.* 7개
> 확장이 누락된 것 (ops.md 트러블슈팅 참조). Isaac Sim 재시작 필요.

### 확장 요구사항 (`isaacsim.exp.full.kit`)

Animation Graph UI·리타게팅이 동작하려면 아래 7개가 `.kit` 파일에 있어야 한다
(CLI `--enable` 플래그는 UI 확장에 불신뢰):

```toml
"omni.anim.graph.core" = {}
"omni.anim.graph.bundle" = {}
"omni.anim.graph.ui" = {}
"omni.anim.retarget.core" = {}
"omni.anim.retarget.bundle" = {}
"omni.anim.retarget.ui" = {}
"omni.anim.people" = {}
```

`~/dev_ws/isaac_sim/isaacsim/_build/linux-x86_64/release/apps/isaacsim.exp.full.kit` 에
2026-05-22 기준 추가 완료.
