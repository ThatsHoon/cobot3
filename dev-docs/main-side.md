# main_side — Isaac Sim PC

## 파일 목록

| 파일 | 역할 |
|------|------|
| `camera_publisher.py` | 메인 Isaac Sim standalone app; OG sensor_bridge 구성·실행 |
| `spot_controller.py` | SpotFlatTerrainPolicy 래퍼; 물리 콜백으로 RL 보행 구동 |
| `telemetry_bridge_node.py` | /robot/odom → /robot/gps + /robot/state 파생 (5Hz) |
| `video_degrade_node.py` | 카메라 영상 5fps JPEG q50 압축 (인스턴스 2개) |
| `publish_robot_description.py` | /robot_description URDF 토픽 발행 (Foxglove 3D) |
| `test_ros2_bridge.py` | ROS2 2-방향 통신 최소 검증 스크립트 |
| `spot_isaac.urdf` | Spot 12-DOF 다리 URDF (base + fl/fr/hl/hr × hx/hy/kn) |
| `scene/gp_scene.usd` | 루트 씬 (Spot ref, 산악 지형, 철조망 울타리) |
| `fastdds_no_shm.xml` | FastDDS UDP-only 프로파일 (SHM 비활성 — Isaac↔System 호환) |
| `fastdds_main.xml` | FastDDS 2-PC LAN 프로파일 템플릿 (__C2_PC_IP__ 치환 필요) |

---

## camera_publisher.py

### 주요 상수

| 상수 | 값 | 환경변수 | 목적 |
|------|----|---------|------|
| `_HEADLESS` | bool | `GP_HEADLESS` (0=GUI, 1=headless) | Isaac 창 표시 여부 |
| `SCENE` | `scene/gp_scene.usd` | `GP_SCENE` | 로드할 USD 씬 경로 |
| `SPOT_PRIM` | `/World/Robot` | — | Spot 루트 prim |
| `BASE_PRIM` | `/World/Robot/base` | — | Spot 기체 링크 |
| `CAM_FRONT_PATH` | `/World/Robot/base/camera_front` | — | 전방 카메라 prim |
| `CAM_REAR_PATH` | `/World/Robot/base/camera_rear` | — | 후방 카메라 prim |
| `GRAPH` | `/World/Graphs/sensor_bridge` | — | OmniGraph 경로 |
| `DOMAIN` | 130 | `ROS_DOMAIN_ID` | ROS2 도메인 |
| `_TELEM` | True | `GP_ROS2_TELEM=1` | 텔레메트리 OG 활성 |
| `_CMD` | True | `GP_ROS2_CMD=1` | cmd_vel 구독 활성 |
| `_SPOT_CTRL` | True | `GP_SPOT_CONTROL=1` | SpotController 활성 |

### OmniGraph 구조 (`/World/Graphs/sensor_bridge`)

```
OnTick (OnPlaybackTick)  — render_dt=1/50 → 50Hz 펄스
  ├─→ RPFront → CamFront          /cam/front/rgb (Image, BEST_EFFORT)
  ├─→ RPRear  → CamRear           /cam/rear/rgb  (Image, BEST_EFFORT)
  ├─→ LegJS                       /robot/leg_joint_states (JointState, RELIABLE)
  ├─→ Odo → OdoPub                /robot/odom (Odometry, RELIABLE)
  ├─→ TF                          /tf (TFMessage, BEST_EFFORT)
  └─→ SubCmd  ←                   /robot/cmd_vel (Twist, RELIABLE)
        ↓ in-process attribute read (_apply_cmd)
        → SpotController.set_cmd_vel()

Ctx (ROS2Context) — domain_id=130 → 모든 ROS2 노드에 공급
SimTime (IsaacReadSimulationTime) → LegJS/OdoPub/TF 타임스탬프 공급
Odo (IsaacComputeOdometry) — chassisPrim=/World/Robot/base
```

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

### 카메라 배치

| 카메라 | prim 경로 | 위치 (xyz) | 회전 (rotateXYZ) | 초점거리 |
|--------|-----------|-----------|----------------|---------|
| 전방 | `/World/Robot/base/camera_front` | (0.35, 0.0, 0.10) | (0.0, -90.0, 0.0) | 1.93mm |
| 후방 | `/World/Robot/base/camera_rear`  | (-0.35, 0.0, 0.10) | (0.0, 90.0, 0.0)  | 1.93mm |

**UsdGeom.Camera** API로 생성 (rsd455.usd 시각 메시 불필요).

### 로봇 USD 교체 로직

```python
_robot_prim = stage.GetPrimAtPath("/World/Robot")
refs = _robot_prim.GetReferences()
refs.ClearReferences()
refs.AddReference(
    "https://omniverse-content-production.s3-us-west-2.amazonaws.com"
    "/Assets/Isaac/5.1/Isaac/Robots/BostonDynamics/spot/spot.usd"
)
```
첫 실행 시 S3에서 다운로드 후 Isaac 캐시에 저장. 이후 오프라인 사용 가능.

---

## spot_controller.py

### 클래스: `SpotController`

| 메서드 | 설명 |
|--------|------|
| `__init__(prim_path)` | SpotFlatTerrainPolicy 바인딩, 내부 상태 초기화 |
| `set_cmd_vel(vx, vy, wz)` | 텔레오퍼레이션 속도 명령 설정 + 타임스탬프 |
| `set_nav_goal(x, y)` | 내비게이션 목표점 설정 (world 좌표계) |
| `clear_nav_goal()` | 내비게이션 목표 해제 |
| `on_physics_step(dt)` | physics 콜백 (500Hz); 초기화→대기→중재→정책실행 |
| `_arbitrate()` | **우선순위: teleop(0.5s TTL) > nav_goal P제어 > idle** |
| `_nav_p_ctrl()` | 단순 P 제어 (vx_max=0.6, wz_sat=±1.2, 도착=0.15m) |
| `_forward(dt, cmd)` | RL 정책 스텝 → ArticulationAction 적용 (12-DOF) |

**DOF 레이아웃:**
- 12-DOF (4다리 × hx/hy/kn)
- `_LEG_PREFIXES = ("fl_", "fr_", "hl_", "hr_")`
- `initialize(set_gains=True, set_limits=True)`

**중재 로직:**
```
teleop (cmd TTL < 0.5s) → 직접 사용
nav_goal 설정됨          → P제어로 속도 계산
                        → vx = kp_dist * dist (max 0.6)
                        → wz = kp_yaw * yaw_err (sat ±1.2)
                        → 도착 0.15m 이내 → clear_nav_goal()
idle                    → [0, 0, 0]
```

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

**인스턴스 2개** (run_degrade.sh에서 환경변수로 분기):

| 인스턴스 | DEGRADE_IN | DEGRADE_OUT | 용도 |
|---------|-----------|------------|------|
| front | `/cam/front/rgb` | `/c2/front/compressed` | 전방 카메라 |
| rear  | `/cam/rear/rgb`  | `/c2/rear/compressed`  | 후방 카메라 |

**처리 파이프라인:**
1. 수신: `sensor_msgs/Image` (BEST_EFFORT, depth=5)
2. numpy 변환 (rgb8/bgr8/rgba8/bgra8 처리)
3. 리사이즈 640×360 (INTER_AREA)
4. JPEG 인코딩 (quality=50)
5. 발행: `sensor_msgs/CompressedImage` (BEST_EFFORT)
6. 스로틀: TARGET_FPS=5.0 Hz

---

## 씬 구조 (`scene/gp_scene.usd`)

```
/World
├── Terrain         ← terrain.usdz (산악, PBR 텍스처)
├── Fence           ← barbed_wire_fence.usdz × 복수 세그먼트
├── Robot           ← spot.usd (S3 ref, 첫 로드 시 다운로드)
│   └── base
│       ├── camera_front   (UsdGeom.Camera, 전방)
│       └── camera_rear    (UsdGeom.Camera, 후방)
└── Graphs
    └── sensor_bridge  (OmniGraph)
```

**에셋 경로 규칙:** 모두 `scene/` 상대 경로. `/home/...` 절대경로 금지.
예외: Spot USD = S3 URL (Isaac 캐시에 저장됨).
