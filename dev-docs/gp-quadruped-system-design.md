# GP 경계근무 4족보행(Spot+팔) 로봇 시스템 설계서

> ⚠ **로봇 스왑(2026-05-17)**: 로봇이 **anymal+m0609(2-아티큘레이션) →
> `spot_with_arm`(4족+팔 **단일 아티큘레이션**, `/World/Robot`, base
> `/World/Robot/base`, 카메라 `/World/Robot/arm0_link_wr1/realsense`, 팔
> 조인트 `arm0_*`, 다리 `fl_/fr_/hl_/hr_`)** 로 전면 교체됨. 현행 코드·
> 통신 계약은 `../main_side/FASTDDS.md §3.1`·`camera_publisher.py`·
> `telemetry_bridge_node.py`·`server/config.py` 가 권위. 아래 본문 중
> ANYmal-C/m0609/`link_6`/2-아티큘레이션 결합(fixed joint·stow)·ANYmal
> 정책 에셋 경로 등 **구체 메커니즘 서술은 구 설계(superseded)** — 토픽
> 규약(`/dsr01/joint_states`,`/robot/leg_joint_states`,`/robot/odom` 등)은
> 그대로 유효하나 발행 주체는 Spot 단일 아티큘레이션 OG 다.

> cobot3 프로젝트 — 창고 분류에서 **GP(경계초소) 경계근무 대체 로봇**으로 전환.
> 본 문서는 시스템 아키텍처 / 노드·통신 구조 / 구현 구체화 / 워크플로우를
> 실행 가능한 수준(P0~P1) + 아키텍처 수준(P2~P4)으로 정의한다.
>
> 작성 규약: 한국어 서술, 코드 식별자·토픽·스키마·명령은 영문, 다이어그램 ASCII.
> 기준 환경: Isaac Sim 5.1.0-rc.19 (소스 빌드), ROS 2 Humble, `ROS_DOMAIN_ID=130`.

---

## 목차

1. 프로젝트 개요
2. 확정 설계 결정 (D1~D11)
3. 시스템 아키텍처 (5계층 / 7서브시스템)
4. PC 토폴로지 & 네트워크
5. Isaac Sim 측 설계 (USD / prim 규약 / 물리)
6. S1 보행 (Locomotion + 번들 RL 정책)
7. S2 m0609 팔 결합 (URDF→USD / fixed joint / stow)
8. S3 인지 (C2 서버측 YOLO)
9. S4 다운링크 (영상·GPS·상태·로그 → C2)
10. S5 업링크 (음성·사격·위치지정 → 로봇)
11. S6 지형 (절차적 볼록 + 에셋 적용)
12. S7 ROS 2 노드·통신 카탈로그
13. 텔레메트리 & 로컬 Postgres 스키마
14. C2 웹 UI 설계
15. 개발 단계 워크플로우 (P0~P4)
16. 위험 요소 & 미해결
17. 부록 (재사용 자산 / 명령어 카드 / 용어집)

---

## 1. 프로젝트 개요

### 1.1 한 문장 목표

> Isaac Sim 안에서 **spot_with_arm(4족+팔 단일 아티큘레이션)이 사전학습 RL
> 정책으로 산지 지형을 실제 물리 보행**하며, 팔 끝 `arm0_link_wr1`
> 플랜지의 **RealSense RGB-D**
> 로 철조망 너머 생물체를 감시하고, 별도 PC의 **지휘통제실(C2) 웹 UI**가 데이터를
> 실시간 표시·YOLO 분석하며 사격·확성기·위치지정을 원격 조작하는 시스템.

### 1.2 범위 (In Scope)

- 절차적 볼록 산악 지형 + 철조망 구축 (에셋 조사·적용 포함)
- spot_with_arm 번들 RL 정책 기반 **실제 물리 보행** + 정해진 경로/목표점 추종
- 팔(`arm0_*`)은 Spot 단일 아티큘레이션에 포함, `arm0_link_wr1` 플랜지에 RealSense RGB-D
- 시뮬 데이터(GPS·로봇상태·rosout WARN·dsr01/joint_states·RGB-D) → C2 PC 전송
- C2 웹 UI: 실시간 직관 표시 + 웹서버측 YOLO 분석 + 사격·확성기·위치지정 조작
- Main PC(Isaac) ↔ C2 PC ROS 2 LAN 통신, 영상 화질저하·5fps 대역 절감

### 1.3 비범위 (Out of Scope)

- 실제 무기/탄도 시뮬 (시뮬 전용 raycast 히트판정으로 한정)
- 실 로봇 sim2real 배포 (설계만, P4 옵션)
- 다중 로봇 (단일 로봇 우선; 네임스페이스 규약은 확장 대비)
- rough-terrain 전용 RL 학습 (P4 옵션 — flat 정책 안정범위로 운용)

### 1.4 성공 지표

| 지표 | 목표 |
|---|---|
| 보행 사실성 | 키프레임/sleep 0건, RL 정책 physics callback 구동 |
| 경로 추종 | waypoint 도달 오차 < 0.5 m, 넘어짐 없이 경로 완주 |
| 영상 다운링크 | RGB ≤ 5 fps, JPEG q≈50, C2 수신 지연 < 300 ms |
| YOLO | C2 서버측 5 fps 입력에서 사람/동물 탐지 동작 |
| 통신 | Main↔C2 동일 `ROS_DOMAIN_ID=130`, 토픽 정상 수신 |

### 1.5 핵심 가정

- Main PC = Isaac Sim 구동(RTX 5080), C2 PC = 별도 물리 PC, 동일 LAN
- ANYmal-C 번들 정책은 **flat terrain** 학습본 → 지형 굴곡을 안정범위로 클램프(D2)
- m0609 결합은 base CoM 을 이동시켜 보행정책을 흔들 수 있음(D3a) → 명시적 완화

---

## 2. 확정 설계 결정 (D1~D11)

| # | 항목 | 결정 | 근거/비고 |
|---|---|---|---|
| D1 | 보행 | ANYmal-C + 번들 `AnymalFlatTerrainPolicy` (실제 물리 RL) | 키프레임/임시방편 금지 충족 |
| D2 | 험지 | 지형 굴곡을 flat 정책 안정범위로 클램프, rough RL 은 P4 | 우회 아닌 명시 단계 |
| D3 | 팔 결합 | m0609 6축을 ANYmal base 에 fixed joint 결합 | URDF: `src/doosan-robot2/urdf/m0609_isaac_sim.urdf` |
| D3a | 결합 리스크 | m0609 질량/관성 → base CoM 이동 → 보행 불안정 가능 | 완화: 링크 질량 경감 + 보행 중 stow + P4 재학습 |
| D4 | 센서 위치 | RealSense = Spot 팔 끝 `arm0_link_wr1` 플랜지 자식 Camera | `/World/Robot/arm0_link_wr1/realsense` (gp_scene.usd 에 동봉 저장; 없을 때만 손목 하위 런타임 생성) |
| D5 | 무기 | 시뮬 전용: 조준 + raycast 히트 + 트레이서 + `FireEvent` | 실무기·탄도 없음 |
| D6 | YOLO 위치 | C2 웹서버 측 수신 프레임 추론 (in-sim 아님) | Main PC 부하 ↓ |
| D7 | C2 백엔드 | Next.js + **FastAPI**(server-bridge 재사용) + 로컬 Postgres. **영상=WebRTC(aiortc)**, 제어/상태=WS | Django 미채택(실시간 스트리밍 부적합); 비즈로직만 GP 교체 |
| D8 | 영상 다운링크 | rgb/depth → 해상도↓ + JPEG q↓ + 5fps (degrade 노드) | net-new |
| D9 | GPS | base world pose → sim-GPS 환산 발행 | net-new, `/robot/gps` |
| D10 | 통신 | 단일 `ROS_DOMAIN_ID=130`, Main↔C2 LAN | 멀티호스트 DDS |
| D11 | 지형 | 절차적 볼록 heightfield + PBR 텍스처(+선택 실 DEM) | 굴곡 D2 클램프 |

---

## 3. 시스템 아키텍처

### 3.1 5계층 모델

```
L5 Presentation  : C2 Next.js UI (영상벽 / 상태 / 로그 / 조작)
L4 C2-Comms      : web_server (FastAPI+rosbridge+YOLO), WS audio/cmd
L3 Telemetry     : telemetry_logger → 로컬 Postgres
L2 Cognition/Ctrl: locomotion / gps / video_degrade / c2_command 노드
L1 Simulation    : Isaac Sim Kit (USD stage, PhysX, OG ROS 브리지)
```

### 3.2 7 서브시스템

| ID | 서브시스템 | 핵심 산출 | 재사용/신규 |
|---|---|---|---|
| S1 | 보행 | ANYmal-C RL physics 보행 + waypoint follower | 번들정책 재사용 / follower 신규 |
| S2 | m0609 결합 | URDF→USD, base fixed, link_6 RealSense | usd-from-urdf 재사용 |
| S3 | 인지 | C2 서버측 YOLO 추론 | yolo-perception 패턴 이전 |
| S4 | 다운링크 | 영상 degrade + GPS + 상태 + rosout WARN | server-bridge 재사용 / degrade·gps 신규 |
| S5 | 업링크 | 양방향 음성 + 사격 + 위치지정 | 전부 신규 |
| S6 | 지형 | 절차적 볼록 메시 + 철조망 + 텍스처 | 신규 (에셋 조사 완료) |
| S7 | 통신 | 단일 도메인 ROS 2 + OG 브리지 | omnigraph-ros-bridge 재사용 |

### 3.3 전체 데이터 흐름

```
            [C2 PC — 지휘통제실]
 Next.js UI : 영상벽(YOLO 오버레이) · GPS/상태 패널 · rosout 로그 ·
              joint 차트 · 확성기메뉴 · 사격/발사 버튼 · 위치지정 맵
   │ REST :8000  │ WS /events (telemetry, log, detection)   ▲ WS audio/cmd
   ▼             ▼                                          │
   web_server (FastAPI + aiortc WebRTC[영상] + rosbridge + YOLOv8) ─┘
        │  ROS 2 DDS  (ROS_DOMAIN_ID=130, LAN)
════════╪═══════════════════════════════════════════════════════════
        ▼              [Main PC — Isaac Sim]
  ┌──────────────────────────────────────────────────────────────┐
  │ Isaac Sim Kit — stage: gp_quadruped.usd                       │
  │  /World/Terrain               볼록 heightfield (정적 충돌)     │
  │  /World/Fence                 철조망 (시각+충돌 proxy)         │
  │  /World/Path/route            정해진 경로 폴리라인             │
  │  /World/Robot                 spot_with_arm 단일 아티큘레이션  │
  │     ├ base                    Spot 몸체(odom·sim-GPS 기준)     │
  │     └ arm0_link_wr1/realsense RGB-D Camera (팔 끝 플랜지)      │
  │  /World/Graphs/sensor_bridge  OG: camera/jointstate/tf pub     │
  │  /World/Graphs/cmd_bridge     OG: nav goal sub                 │
  └───┬───────────────┬───────────────┬──────────────┬────────────┘
   physics cb       OG pub          OG pub         OG sub
      ▼               ▼               ▼              ▼
 locomotion_node   (camera→)     gps_node      c2_command_node
 (waypoint→cmd)  video_degrade_node            (fire/speaker/goal)
      └──────────────┬───────────────┴──────────────┘
                     ▼
            telemetry_logger_node ──→ 로컬 Postgres
```

---

## 4. PC 토폴로지 & 네트워크

### 4.1 역할 분리

| | Main PC | C2 PC |
|---|---|---|
| 구동 | Isaac Sim Kit, locomotion/gps/video_degrade/c2_command/telemetry 노드, 로컬 Postgres | web_server(FastAPI+rosbridge+YOLO), Next.js |
| GPU | RTX 5080 (sim + 물리) | YOLO 추론용 GPU(권장) |
| 부하 | 물리·렌더·OG | 영상 수신·추론·웹 |

### 4.2 멀티호스트 DDS

```bash
# 양 PC 공통 (~/.bashrc)
export ROS_DOMAIN_ID=130
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
# 동일 서브넷이면 기본 멀티캐스트 디스커버리로 충분.
# 서브넷 분리 시 FastDDS DISCOVERY_SERVER 또는 peers XML 사용(부록 참조).
```

### 4.3 보안

- server-bridge REST 의 변경계열(사격/확성기/모드/goto) = `X-API-Key` 필수
- CORS allowlist = C2 Next.js 오리진만
- 조회계열(상태/영상)은 키 없이 LAN 한정

---

## 5. Isaac Sim 측 설계

### 5.1 USD 스테이지 & prim 경로 규약

스테이지 파일: `gp_quadruped.usd` (defaultPrim `/World`, Z-up, meter)

```
/World
├── /World/PhysicsScene              gravity (0,0,-9.81), TGS, GPU
├── /World/DomeLight
├── /World/Terrain                   Mesh, 절차 볼록, 정적 삼각 collider
├── /World/Fence                     철조망 (post/wire Cylinder + 충돌 proxy)
├── /World/Path
│   └── /World/Path/route            BasisCurves/Points (waypoint 폴리라인)
└── /World/Robot                     ArticulationRoot (spot_with_arm, 단일)
    ├── base                         Spot 몸체(odom·sim-GPS 기준)
    ├── (다리) fl_/fr_/hl_/hr_ × hx/hy/kn
    ├── (팔)  arm0_* … arm0_link_wr1
    └── /World/Robot/arm0_link_wr1/realsense   Camera (+depth, 씬 동봉)
```

토픽 네임스페이스 규약:
- 센서/상태: `/robot/...` (단일 로봇; 확장 시 `/r{N}/...`)
- 팔(arm0) 조인트: `/dsr01/joint_states` (토픽명 규약 유지 — Spot 단일
  아티큘레이션이라 OG 는 전체 JointState 발행, arm/leg 의미분리는 소비측)
- C2 영상: `/c2/...`

### 5.2 물리 설정

- PhysicsScene: TGS solver, GPU pipeline, `physics_dt = 1/200 s`, `render_dt = 1/60 s`
  (번들 정책 표준; `anymal_standalone.py` 와 동일)
- 지형: 정적 삼각 메시 collider (`UsdPhysics.CollisionAPI` +
  `UsdPhysics.MeshCollisionAPI` approximation="none"), 마찰 0.8
- ANYmal: 번들 USD `anymal_c.usd` 기본 articulation 속성 (정책 env yaml 이 gain 설정)
- m0609: URDF 임포트 시 joint drive(position) — 보행 중 stow hold

### 5.3 OmniGraph 브리지

두 그래프로 분리(센서 발행 / 명령 구독):

**`/World/Graphs/sensor_bridge`** (OnPlaybackTick → ROS2Context →):
- `ROS2PublishJointState` ← Spot 단일 articulation → `/dsr01/joint_states`
- `ROS2PublishJointState` ← 동일 Spot articulation → `/robot/leg_joint_states`
  (Spot 단일 아티큘레이션이라 두 토픽 모두 전체 JointState; arm/leg 의미
  분리는 소비측/HTTP `_gather` 가 조인트명 prefix 로 — `FASTDDS.md §3.1`)
- `IsaacCreateRenderProduct`(realsense) → `ROS2CameraHelper` rgb → `/cam/realsense/rgb`
- 동 render product → `ROS2CameraHelper` depth → `/cam/realsense/depth`
- `ROS2PublishTransformTree` → `/tf`, `/tf_static`

**`/World/Graphs/cmd_bridge`**:
- `ROS2SubscribeTwist` 또는 커스텀 → c2_command_node 가 처리 (goal 은 노드측 구독)

> OG 노드 타입 주의: `isaacsim.core.nodes.*`, `isaacsim.ros2.bridge.*`,
> `omni.graph.action.OnPlaybackTick` (점 표기, 밑줄 아님).

---

## 6. S1 — 보행 (Locomotion + 번들 RL 정책)

### 6.1 정책 자산 (검증된 경로)

| 항목 | 경로 (assets_root + …) |
|---|---|
| 로봇 USD | `/Isaac/Robots/ANYbotics/anymal_c/anymal_c.usd` |
| 정책 | `/Isaac/Samples/Policies/Anymal_Policies/anymal_policy.pt` |
| env 설정 | `/Isaac/Samples/Policies/Anymal_Policies/anymal_env.yaml` |
| 액추에이터망 | `/Isaac/Samples/Policies/Anymal_Policies/sea_net_jit2.pt` |

클래스: `isaacsim.robot.policy.examples.robots.AnymalFlatTerrainPolicy`
(상속 `PolicyController`). `forward(dt, command)` 의 `command=[v_x, v_y, w_z]`
(body-frame 속도, v_x∈[-1,1] m/s, w_z∈[-1,1] rad/s).

### 6.2 구동 시퀀스 (sleep/키프레임 없음 — D1)

`anymal_standalone.py` 와 동일 패턴:

```
World(stage_units=1.0, physics_dt=1/200, rendering_dt=1/60)
world.reset()
robot = AnymalFlatTerrainPolicy(prim_path="/World/Robot/anymal",
                                position=route.first_xyz)
# 첫 physics step
on_physics_step(step):
    if first_step:        robot.initialize();  first_step=False
    elif reset_needed:    world.reset(True); ...
    else:                 robot.forward(step, base_command)
world.add_physics_callback("anymal", on_physics_step)
```

> MCP 환경에서는 `time.sleep`/장기 루프를 `execute_script` 안에 두지 않는다
> (Kit thread block). physics callback 으로만 구동.

### 6.3 waypoint follower (net-new, classical P 제어)

`/World/Path/route` 폴리라인을 읽어 순차 추종. 매 physics step:

```
pos, quat = robot.robot.get_world_pose()
yaw       = yaw_from_quat(quat)
tgt       = route[idx]
d         = dist(pos.xy, tgt.xy)
brg       = atan2(tgt.y-pos.y, tgt.x-pos.x)
hd_err    = wrap(brg - yaw)
v_x = clip(Kp_v * d, 0, V_MAX) * cos_gate(hd_err)   # 큰 heading 오차 시 전진 억제
w_z = clip(Kp_w * hd_err, -W_MAX, W_MAX)
if d < ARRIVE_R: idx += 1   # 다음 waypoint, 마지막이면 정지(cmd=0)
base_command = [v_x, 0.0, w_z]
```

- C2 가 goal 을 주면(`/robot/nav/goal`) route 를 (현위치→goal) 직선 또는 사전
  정의 경로 그래프로 갱신. "정해진 길" = route prim 으로 사전 정의, goal 은 그 위 지점.
- 도착·이탈·정지 상태를 `/robot/state` 로 발행.

---

## 7. S2 — m0609 팔 결합 (D3 / D3a)

### 7.1 URDF→USD 임포트

- 입력: `/home/rokey/dev_ws/isaac_sim/src/doosan-robot2/urdf/m0609_isaac_sim.urdf`
  (links: `base, base_link, link_1..link_6, tool0`; joints: `joint_1..joint_6`)
- Isaac URDF Importer (usd-from-urdf.md 패턴): fixed base, position drive,
  self-collision off, convexHull collider → `/World/Robot/m0609`

### 7.2 ANYmal 결합

- `m0609/base_link` ↔ `anymal/base` 사이 **fixed joint** (USD `PhysicsFixedJoint`),
  ANYmal 등판 위 오프셋 배치
- **D3a 완화 (근본 대응, 우회 아님)**:
  1. 시뮬 m0609 링크 질량을 경량 페이로드 수준으로 스케일(관성도 동반 조정) —
     base CoM 이동 최소화
  2. 보행 중 m0609 6축을 **stow 자세**(접힌 정자세)로 position drive hold —
     동적 토크 외란 제거
  3. 그래도 보행 불안정 시 P4 에서 payload 포함 rough-terrain 정책 재학습
- 조준 시(정지 상태)만 link_6 를 타깃 지향(간이 IK / 직접 joint 목표) — 보행과 분리

### 7.3 RealSense 장착 (D4)

- `/World/Robot/arm0_link_wr1/realsense` Camera prim (focal·aperture →
  K 행렬), depth annotator 활성. gp_scene.usd 에 동봉 저장; `camera_
  publisher.py` 는 이를 그대로 쓰고 없을 때만 손목(`arm0_link_wr1`) 하위
  런타임 생성·CAM_PATH 자동 갱신.
- OG `IsaacCreateRenderProduct` → `ROS2CameraHelper` rgb/depth
  → `/cam/realsense/rgb`, `/cam/realsense/depth`

### 7.4 조인트 상태 발행

- OG `ROS2PublishJointState`(m0609 articulation) → **`/dsr01/joint_states`**
  (dsr_controller2 네이밍 유지 → 실로봇 호환)

---

## 8. S3 — 인지 (C2 서버측 YOLO, D6)

- Isaac/Main PC 는 추론하지 않음 — RGB 만 degrade 하여 전송
- C2 `web_server` 가 수신 프레임을 YOLOv8 in-process 추론
  (yolo-perception.md 패턴을 **서버측으로 이전**: 모델 singleton, FP16 TensorRT 권장)
- 입력 5 fps degrade 프레임 → 사람/동물 클래스 bbox + conf
- 출력:
  - UI 영상벽에 bbox 오버레이(WebSocket push)
  - `intruder_detections` 테이블 기록(텔레메트리)
  - 철조망 너머 판정: depth + `/World/Fence` 위치로 거리/측 계산(서버측 메타 사용)

---

## 9. S4 — 다운링크 (영상·GPS·상태·로그 → C2)

### 9.1 video_degrade_node (net-new)

```
sub /cam/realsense/rgb (sensor_qos)         sub /cam/realsense/depth
   │  throttle 5 fps                            │  throttle 5 fps
   │  cv2.resize(½) + imencode JPEG q≈50         │  16bit→8bit 스케일 + PNG/JPEG
   ▼                                            ▼
pub /c2/video/compressed (CompressedImage)   pub /c2/depth/compressed
```

- 대역 절감: 1280×720 → 640×360, JPEG q≈50, 5 fps (≈ 원본의 수십분의 1)
- QoS: BEST_EFFORT depth 5 (프레임 드랍 허용)
- **전송**: rgb 는 web_server 의 **WebRTC(aiortc) VideoStreamTrack** 로 송출
  (SRTP·혼잡제어·최저지연). video_degrade_node 는 프레임 생산만, WebRTC SDP
  협상은 web_server 담당. depth/저대역 폴백은 `/c2/depth/compressed` 토픽 유지
- **영상은 DB 저장 안 함** (전송 전용). 탐지 메타데이터만 psql 기록(§13)

### 9.2 gps_node (net-new, D9)

- Spot base(`/World/Robot/base`) world pose(x,y,z) 취득 → sim 원점 기준 ENU → 기준 위경도(설정값)에
  로컬접평면 환산 → `sensor_msgs/NavSatFix` 풍 `/robot/gps` 발행 (RELIABLE)
- 동시에 `/robot/odom`(보행 노드) 와 일관

### 9.3 robot state

- 집계: 모드(IDLE/PATROL/AIM/FIRE), 보행상태, 배터리(sim 모델), m0609 6축 각,
  현 waypoint idx → `/robot/state` (커스텀 msg, RELIABLE)

### 9.4 rosout WARN 중계

- `/rosout`(rcl_interfaces/Log) 구독, `level >= 30`(WARN) 필터
- server-bridge 가 WS `/events` 로 `{type:"log", level, name, msg, ts}` 멀티캐스트
- `rosout_warn` 테이블 기록

### 9.5 server-bridge 재사용 + 신규 엔드포인트

| 엔드포인트 | 메서드 | 인증 | 내용 |
|---|---|---|---|
| `/robots/{id}/state` | GET | - | 최신 `/robot/state` 캐시 |
| `/robots/{id}/gps` | GET | - | 최신 `/robot/gps` |
| `/c2/webrtc/offer` | POST | - | WebRTC SDP 협상(aiortc) → rgb 영상 트랙 |
| `/c2/video/mjpeg` | GET | - | 저대역 폴백 MJPEG(`/c2/video/compressed`) |
| `/events` | WS | - | telemetry·log·detection 멀티캐스트 |
| `/robots/{id}/goto` | POST | X-API-Key | 위치지정 → `/robot/nav/goal` |
| `/robots/{id}/fire` | POST | X-API-Key | 사격 트리거 |
| `/robots/{id}/speaker` | POST/WS | X-API-Key | 확성기 음성/프리셋 |

---

## 10. S5 — 업링크 (음성·사격·위치지정 → 로봇)

### 10.1 양방향 음성 (net-new)

```
C2 mic → 브라우저 캡처(Opus/PCM) → WS 바이너리 → server_bridge
       → ROS /robot/speaker/audio (audio chunk) → speaker_handler
       → (시뮬: 실제 음향 불가) 로깅 + UI 자막 "송출중: …" + FireEvent 류 기록
```
- 프리셋("엎드려", "손들어")은 텍스트 명령으로도 전송(저대역 폴백)
- 로봇→C2 방향(현장음)은 시뮬에 음원 없으므로 P3 에서 합성/생략 명시

### 10.2 사격 / 발사 (net-new, D5 — 시뮬 전용)

```
C2 사격버튼 → POST /robots/{id}/fire (X-API-Key, 타깃 detection id 또는 pose)
   → ROS service /robot/weapon/fire
   → c2_command_node: m0609 link_6 를 타깃 pose 지향(정지 상태에서만)
   → raycast(총구→타깃) 히트 판정 → 시각 트레이서 prim 1회 표시
   → FireEvent {ts, target, hit:bool, distance} 발행/기록
```
- 명령 불이행 타이머: 확성기 명령 후 N 초 내 미반응 → UI 에 "사격 허가" 활성
  (실 발사는 항상 운용자 버튼 명시 트리거 — 자동 발사 없음)

### 10.3 위치 지정

```
C2 맵 클릭(x,y) → POST /robots/{id}/goto → /robot/nav/goal (PoseStamped)
   → locomotion_node: route 갱신(현위치→goal, 사전 경로그래프 우선) → S1 추종
```

---

## 11. S6 — 지형 (절차적 볼록 + 에셋 적용, D11)

### 11.1 에셋 조사 결론

- Isaac 5.1 라이브러리 전수 조사 결과: 실 산악/철조망/군초소 에셋 **없음**
  (`Environments/Terrains` = flat/rough/slope/stairs 프리미티브뿐)
- USD Search(클라우드)는 `NVIDIA_API_KEY` 필요 — 미설정 시 사용 불가
- **결론: 절차적 생성이 정석** (무한 변형 + 충돌 메시 자동 + 보행정책 안정범위 제어)

### 11.2 절차적 볼록 지형 생성

- numpy heightfield: 다중 가우시안 산괴(전체 볼록 윤곽) + fBm/ridged 멀티프랙탈
  (울퉁불퉁 잔굴곡), `z -= z.min()` (바닥 0)
- **D2 클램프**: 국소 경사·굴곡 진폭을 flat 정책 안정범위로 제한
  (예: 셀간 경사 ≲ 15°, 진폭은 ANYmal foot clearance 이내) — 우회가 아니라
  "flat 정책 운용 조건" 명시
- USD `UsdGeom.Mesh` 제자리 작성(이전 검증: RemovePrim+Define 동일경로 레이스
  회피 — 기존 메시 points/topology 덮어쓰기)
- 정적 삼각 collider: `UsdPhysics.CollisionAPI` + `MeshCollisionAPI`
  approximation="none"

### 11.3 텍스처/머티리얼

- OmniPBR + Poly Haven / ambientCG (CC0) 적설·암벽 텍스처, 또는 GUI Materials 드래그
- 옵션(P4): 국토지리정보원 실 DMZ DEM(수치표고모델) → heightfield 임포트(현실성↑)

### 11.4 철조망

- `/World/Fence` (기존 생성: post/wire Cylinder). 시각 메시는 디테일,
  **충돌은 단순 박스/실린더 proxy 로 분리**(폴리곤 폭발 방지)

---

## 12. S7 — ROS 2 노드·통신 카탈로그

### 12.1 노드 매트릭스

| 노드 | PC | 구독 | 발행 | 서비스 |
|---|---|---|---|---|
| locomotion_node | Main | `/robot/nav/goal` | physics cb, `/robot/odom`, `/robot/state` | - |
| gps_node | Main | (world pose) | `/robot/gps` | - |
| telemetry_bridge_node | Main | `/robot/odom` | `/robot/gps`, `/robot/state` | - |
| video_degrade_node | Main | `/cam/realsense/rgb`,`/depth` | `/c2/video/compressed`,`/c2/depth/compressed` | - |
| c2_command_node | Main | `/robot/speaker/audio` | `/robot/m0609/cmd`, `FireEvent`, 트레이서 | `/robot/weapon/fire` |
| telemetry_logger_node | Main | 전 토픽 | (DB write) | - |
| web_server | C2 | 전 토픽 + rgb | FastAPI:8000 REST/WS + aiortc WebRTC + YOLO | - |

> **구현 현황(2026-05-18)**: `locomotion_node` 역할은 **`SpotController`**
> (`main_side/spot_controller.py`)로 구현됨. `camera_publisher.py` 가
> `world.add_physics_callback("spot_ctrl", ctrl.on_physics_step)` 으로 등록,
> `SpotFlatTerrainPolicy`(RL 보행) + arm DOF stow/aim 제어. `/robot/cmd_vel`
> 수신 → `ctrl.set_cmd_vel` → 보행 정책 적용(teleop 0.5s 타임아웃 → nav_goal
> P-제어 → idle). 업링크 텔레메트리: arm/leg `JointState`·`/robot/odom` 은
> OG ROS2 노드 발행, `/robot/gps`·`/robot/state` 는 `telemetry_bridge_node.py`
> 가 파생. HTTP `/ingest` 경로는 제거 — ROS2 정공 단일 경로.

### 12.2 토픽·QoS 매트릭스

| 토픽 | 타입 | QoS |
|---|---|---|
| `/dsr01/joint_states` | sensor_msgs/JointState | RELIABLE depth10 |
| `/robot/leg_joint_states` | sensor_msgs/JointState | RELIABLE depth10 |
| `/cam/realsense/rgb` | sensor_msgs/Image | BEST_EFFORT depth5 |
| `/cam/realsense/depth` | sensor_msgs/Image | BEST_EFFORT depth5 |
| `/c2/video/compressed` | sensor_msgs/CompressedImage | BEST_EFFORT depth5 |
| `/robot/gps` | sensor_msgs/NavSatFix | RELIABLE depth10 |
| `/robot/odom` | nav_msgs/Odometry | RELIABLE depth10 |
| `/robot/state` | (custom) RobotState | RELIABLE depth10 |
| `/robot/nav/goal` | geometry_msgs/PoseStamped | RELIABLE depth5 |
| `/robot/speaker/audio` | (custom) AudioChunk | RELIABLE depth20 |
| `/rosout` | rcl_interfaces/Log | (기본, level≥30 필터) |
| `/tf_static` | tf2_msgs/TFMessage | RELIABLE TRANSIENT_LOCAL |

> 영상 rgb 는 ROS 토픽이 아닌 **web_server↔브라우저 WebRTC(SRTP)** 로 전달(저지연).
> depth/폴백만 `/c2/*compressed` 토픽 사용. **영상 외 전 데이터는 psql 저장**(§13).

### 12.3 launch 구조

- Main PC: `bringup_main.launch.py` (locomotion, gps, video_degrade,
  c2_command, telemetry_logger) — Isaac Sim 은 별도 기동(`isaac-mcp`)
- C2 PC: `bringup_c2.launch.py` (web_server) + Next.js 별도

---

## 13. 텔레메트리 & 로컬 Postgres 스키마

> **저장 정책 (확정)**: **영상 프레임을 제외한 모든 데이터는 로컬 PostgreSQL 에
> 저장한다.** 즉 GPS·로봇상태·`/dsr01/joint_states`·leg joint·rosout WARN·
> 침입탐지 메타·사격 이벤트·순찰 이벤트는 전부 psql 적재. RealSense rgb/depth
> 원본 프레임은 DB 에 넣지 않고 WebRTC/토픽으로 전송만 한다(탐지 결과 메타데이터는
> 저장). telemetry_logger_node 가 단일 적재 경로(asyncpg COPY 배치).

기존 cobot3 9테이블(`0001_telemetry_schema.sql`) 구조 재사용, GP용 적응
(`0003_gp_schema.sql`):

| 신규/적응 테이블 | 출처 | 핵심 컬럼 |
|---|---|---|
| `intruder_detections` | ← detections | id, ts, class_name, conf, bbox, world_xyz, beyond_fence(bool) |
| `patrol_runs` | ← cycles (UUID) | id, start_ts, end_ts, route_id, success, dist_m |
| `patrol_events` | ← cycle_events | run_id, ts, event_type(START\|WAYPOINT\|ARRIVE\|AIM\|FIRE\|RETURN), meta JSONB |
| `gps_track` | 신규 | id, ts, lat, lon, alt, x, y (BRIN(ts)) |
| `fire_events` | 신규 | id, ts, target_ref, hit bool, distance_m, operator |
| `rosout_warn` | 신규 | id, ts, level, node_name, msg |
| `joint_snapshots` | 재사용 | ts, q[6](m0609), leg_q[12], (10Hz 다운샘플, BRIN) |
| `robots` | 재사용 | robot_id, name |

- 인입: rclpy 구독 → asyncio queue → asyncpg `copy_records_to_table` 1초 배치
  (telemetry-supabase.md 패턴)
- 보관: gps_track/joint_snapshots 14일, detections 30일, patrol_* /fire_events 1년

---

## 14. C2 웹 UI 설계

기존 Next.js 14 + Tailwind + WebSocket 스택 재사용. 페이지:

```
┌─ 대시보드 ──────────────────────────────────────────────┐
│ [영상벽] RealSense RGB + YOLO bbox 오버레이 (5fps)        │
│ [지도]   GPS 트랙 + 경로 route + 클릭→goto                │
│ [상태]   모드/배터리/보행상태/m0609 6축/현 waypoint       │
│ [로그]   rosout WARN 스트림 (level 색상)                  │
│ [차트]   joint_states (m0609 q, leg q) 실시간             │
│ [조작]   확성기 메뉴(프리셋+PTT 마이크) · 사격/발사 버튼  │
└──────────────────────────────────────────────────────────┘
```

- 컴포넌트: `VideoWall` / `MapTrack` / `StatePanel` / `LogStream` /
  `JointChart` / `CommandBar`
- 데이터: 영상=**WebRTC**(`RTCPeerConnection`, `POST /c2/webrtc/offer`) /
  텔레메트리·로그·탐지=WS `/events` / REST 폴백 (MJPEG 폴백 가능)
- 사격/확성기/goto = `X-API-Key` 보호, 확인 모달
- chrome-devtools MCP 로 라이브 검증(web-slide live-preview 패턴)

---

## 15. 개발 단계 워크플로우 (P0~P4)

### P0 — 환경 (1일)

- `gp_quadruped.usd` 신규 스테이지, `ROS_DOMAIN_ID=130` 양 PC 확인
- m0609 URDF→USD 임포트 검증(링크/조인트 매핑 확인)
- DB 마이그레이션 `0003_gp_schema.sql` 적용
- Next.js scaffold 재사용 확인, server-bridge 기동 확인

### P1 — 보행 + 지형 + 팔결합 (실행 핵심 · 검증 데모)

1. `setup_terrain.py`: 절차적 볼록 지형(굴곡 D2 클램프) + 정적 collider
2. `setup_anymal_policy.py`: ANYmal-C + 번들 정책, World/reset/initialize/
   physics callback (sleep 없음)
3. `setup_m0609_mount.py`: URDF→USD, base fixed joint, stow hold,
   질량 경감(D3a)
4. `locomotion_node.py`: `/World/Path/route` waypoint follower + `/robot/nav/goal`
5. **검증**: Isaac play → ANYmal 이 넘어지지 않고 경로 완주, C2 goto 로 목표 이동

### P2 — 센서 + 다운링크 (2~3일)

- link_6 RealSense OG 발행, `gps_node`, `video_degrade_node`(5fps)
- C2 영상벽(**WebRTC/aiortc**) + 서버측 YOLO 오버레이, GPS/상태 패널
- psql 적재 경로 확인: 영상 외 전 토픽 → telemetry_logger → 로컬 Postgres

### P3 — 업링크 + 텔레메트리 (3~5일)

- 양방향 음성(WS), 사격/발사(raycast+트레이서+FireEvent),
  rosout WARN 중계, telemetry_logger 전체, server-bridge 전 엔드포인트,
  UI 조작·로그·차트 완성

### P4 — 옵션

- 열화상 정밀화, rough-terrain Isaac Lab 학습(D2/D3a 근본 해소),
  실 DMZ DEM, m0609 동적 매니퓰레이션

---

## 16. 위험 요소 & 미해결

| 위험 | 영향 | 대응 |
|---|---|---|
| flat 정책 + 험지(D2) | 거친 굴곡서 보행 불안정 | 굴곡 클램프, P4 rough 학습 |
| m0609 결합 CoM(D3a) | 보행 넘어짐 | 질량 경감 + stow + P4 재학습 |
| 열화상 미지원 | 수색 충실도 | P1~2 는 RGB-D+semantic, 열은 P4 |
| 시뮬 음향 부재 | 양방향 음성 사실성 | "송출" 상태/자막 표현, 합성 P4 |
| MCP execute_script 래퍼 버그 | 결과 확인 우회 필요 | /tmp 파일 write→read 패턴 |
| 영상 대역 | LAN 부하 | degrade(640×360,q50,5fps) + WebRTC 혼잡제어 |
| WebRTC 복잡도 | aiortc 협상/트랙 구현 부담 | LAN 내라 STUN/TURN 불필요(호스트 후보 직결), P2 도입 |

---

## 17. 부록

### 17.1 재사용 자산 (수정 안 함, cite)

- `~/dev_ws/isaac_sim/isaacsim/source/extensions/isaacsim.robot.policy.examples/`
  `isaacsim/robot/policy/examples/robots/anymal.py`, `controllers/policy_controller.py`,
  `utils/actuator_network.py`
- `~/dev_ws/isaac_sim/isaacsim/source/standalone_examples/api/isaacsim.robot.policy.examples/anymal_standalone.py`
- `/home/rokey/dev_ws/isaac_sim/src/doosan-robot2/urdf/m0609_isaac_sim.urdf`
- `~/.claude/skills/isaac-sim-bridge/references/{server-bridge,telemetry-supabase,omnigraph-ros-bridge,yolo-perception,usd-from-urdf}.md`
- 기존 `cobot3/dev-docs/cobot3-system-design.md`, `cobot_ws/db/migrations/0001_telemetry_schema.sql`, `0002_retention_policy.sql`

### 17.2 신규/수정 파일 (구현 단계)

- ~~`cobot3/scenes/`: `setup_terrain.py`, `setup_anymal_policy.py`,
  `setup_m0609_mount.py`, `build_og_factory.py`(적응)~~ — **구현 단계에서
  방침 변경**: scenes/ 모듈 대신 저장된 씬 USD(`GP_SCENE`) + `main_side/
  camera_publisher.py` 인라인 구성으로 단일화. 구 scenes/ 는
  `dev-docs/legacy_scenes/` 로 아카이브(Appendix-D 참조).
- `cobot3_nav/locomotion_node.py`
- `cobot3_c2/`: `gps_node.py`, `video_degrade_node.py`, `c2_command_node.py`
- `cobot3_telemetry/logger_node.py`(적응)
- `cobot3_web/web_server.py`(server-bridge + aiortc WebRTC + YOLO 적응)
- `cobot_ws/db/migrations/0003_gp_schema.sql`

### 17.3 명령어 카드

```bash
# Isaac Sim (MCP 포함) 기동
setsid bash -c '~/dev_ws/isaac_sim/isaacsim/_build/linux-x86_64/release/isaac-sim.sh \
  --ext-folder /home/rokey/dev_ws/isaac-sim-mcp/ --enable isaac.sim.mcp_extension' \
  </dev/null >/tmp/isaac.log 2>&1 & disown

# ROS 환경 (양 PC 공통)
export ROS_DOMAIN_ID=130 ROS_LOCALHOST_ONLY=0

# DB 마이그레이션
psql -d cobot3 -f cobot_ws/db/migrations/0003_gp_schema.sql

# 토픽 확인
ros2 topic list | grep -E 'robot|cam|c2|dsr01'
ros2 topic hz /c2/video/compressed     # ≈5
```

### 17.4 용어집

- **AnymalFlatTerrainPolicy**: Isaac Sim 번들 사전학습 RL 보행 정책(평지 학습)
- **stow 자세**: 보행 중 팔을 접어 고정해 CoM 외란을 최소화한 자세
- **degrade**: 발행측에서 해상도·화질·fps 를 낮춰 대역을 줄이는 처리
- **sim-GPS**: 실제 GPS 가 없는 시뮬에서 base world pose 를 위경도로 환산한 값
- **route**: USD 에 사전 정의된 "정해진 길" 폴리라인(waypoint 시퀀스)

---

## Appendix-D. 임시 같은-PC D-확장 우회 (ROS2 미사용)

> 본문(§4·§9·§12)의 ROS2 토픽 경로는 **실배포 2-PC LAN** 기준이다. 같은-PC
> 임시 검증에서 **Isaac 번들 내부 ROS2(Python 3.11) ↔ 시스템 ROS 2
> Humble(Python 3.10) 가 같은 호스트에서 DDS 디스커버리 불통**임이 확인됐다
> (cyclone 통일 / LD_LIBRARY_PATH=Isaac 번들 humble lib / 시스템 ROS env
> scrub / FastDDS UDP-only 프로파일 = NVIDIA 공식 `humble_ws/fastdds.xml`
> — 전부 무효; Isaac 측은 발행하나 외부 Publisher 0). 머신 분리 시 DDS
> 와이어는 ABI 무관이라 2-PC LAN 은 지원 경로 — 즉 이건 *같은-호스트 한정
> 병리*이다. 단, D-확장 우회는 같은-PC 전용이 아니라 **HTTP(TCP)라 2-PC
> LAN 에서도 그대로 동작**한다(POST 타깃을 웹PC IP 로). 같은-PC 는 D-확장이
> *유일 선택지*, 2-PC 는 D-확장·ROS2 *둘 다 가능* — D.4 선택 규칙 참조.

### D.1 데이터 경로 (DDS 완전 우회)
```
Isaac(camera_publisher.py, 단일 프로세스, in-process)
 ├ replicator annotator rgb/depth  (OG render product 에 attach)
 ├ isaacsim.core.prims.Articulation get_joint_positions (Spot 단일 — arm0_*/다리, 조인트명 prefix 로 분리)
 └ XformCache(/World/Robot/base) → base pose → sim-GPS 환산
        └ 백그라운드 스레드 HTTP POST(urllib, Kit 루프 비차단)
             → web_server  POST /ingest/frame   (raw RGB 640x360)
             → web_server  POST /ingest/telemetry (JSON)
   web_server: ros._set_video_frame(WebRTC/MJPEG 그대로 소비) + ros.latest +
               WS /events + DB — 기존 UI 무변경
```

### D.2 ingest 계약 (web_server `sub1_side/server/app.py`)
| 엔드포인트 | 입력 | 처리 |
|---|---|---|
| `POST /ingest/frame?w=&h=&enc=rgb` | raw HxWx3 uint8 바이트 | RGB→BGR, (선택)YOLO 오버레이+탐지 emit/DB, `ros._set_video_frame` |
| `POST /ingest/telemetry` | JSON `{ts,arm_q,leg_q,gps,odom,state,logs}` | `ros.latest` 갱신 + WS state/gps + DB(gps_track/joint_snapshots/robot_state_log/rosout_warn) + `ros.ingest_ts` |
| `GET /ingest/stats` | — | `{frame,tele}` 누적 수신 카운트 |

- ingest 경로는 **rclpy 불요**(ros_bridge 와 독립). ros_bridge 헬스는
  `ingest_ts` 인지 → 최근 ingest 시 구 ROS2 video WARN 대신
  `ingest=LIVE` INFO + diag hint "ingest 활성(ROS2 우회)".
- 영상은 어떤 경로로도 **DB 저장 안 함**(불변식 4 유지).
- 한계: `robot_state` 의 mode/battery/waypoint 는 보행 FSM 미구현 →
  전송수단 무관하게 빈 값(locomotion 노드 구현 시 충족).

### D.3 적용 파일 (검증 완료)
- `main_side/camera_publisher.py` (uplink 워커 + annotator + Articulation + sim-GPS)
- `main_side/run_camera_pub.sh` / `run_camera_pub_gui.sh` (ROS env scrub +
  Isaac 번들 ROS2 격리; GUI 는 사용자 `!` 기동)
- `sub1_side/server/app.py` (`/ingest/*`), `ros_bridge.py`(ingest-인지 헬스)

### D.4 모드 선택 규칙 (택1 강제 아님)
- **같은 PC** → D-확장 **강제**(이 부록). ROS2 경로는 같은-호스트 DDS
  불통으로 **불가**.
- **2-PC LAN** → D-확장·ROS2 **둘 다 가능**, 요구사항으로 선택:
  - 영상+텔레메트리만 빠르게/확실하게, 단일 소비자, Isaac 의존 최소
    → **D-확장**(POST 타깃을 웹PC IP 로; 가장 단순·검증됨).
  - `ros2 topic`/rosbag/rqt·다중 구독자·DDS QoS·실로봇 확장
    → **ROS2 정공**(본문 경로 + `fastdds_no_shm.xml`).
- 사전설정/기동 절차·선택표는 [`project_requirments.md`](project_requirments.md) §5.

---

*문서 끝. 구현은 P0 → P1 순으로 진행하며, 각 단계 산출물은 17.2 경로에 작성한다.*
*(같은-PC 임시 검증은 Appendix-D 의 D-확장 우회로 영상+텔레메트리 웹 수신 검증됨.)*
