# ROS2 정공 양방향 통신 + SpotController 설계

날짜: 2026-05-18  
범위: main_side · sub1_side · 문서 정합 오버홀

---

## 1. 배경 및 목표

ROS2 정공(시스템 ROS2 Humble ↔ Isaac Sim 내부 OmniGraph C++ 브리지) 양방향
통신이 실증됨(업링크 63Hz, 다운링크 637회/10s). 이전 "정공 불가" 전제는 오진.
이 설계는 검증된 경로로 메인·서브 통신을 정상 구현하고 HTTP /ingest 경로를
제거한다.

---

## 2. 근본원인 (이전 "정공 불가" 오진의 3가지 원인)

| # | 근본원인 | 수정 |
|---|---|---|
| 1 | `world.step(render=False)` → 타임라인 동결 → OnPlaybackTick 미발생 → OG 노드 미실행 | `render=True` |
| 2 | 런처 scrub(`unset AMENT_PREFIX_PATH` 등) → Isaac C++ 브리지가 시스템 fastrtps 2.6.11 대신 internal libs 로드(자해). camera_publisher.py 는 rclpy 미사용이라 scrub 전제 자체가 불성립 | no-scrub + `source /opt/ros/humble/setup.bash` |
| 3 | Isaac qosProfile JSON 파서는 8키 전부 요구(부분 JSON → "Missing key: deadline" 거부 → 엔드포인트 미생성 + 25k 스팸) | 완전 8키 JSON |

---

## 3. 아키텍처

### 3.1 통신 경로 (단순화 후)

```
[Isaac Sim, Main PC]
  camera_publisher.py
    ├─ OG ROS2CameraHelper      → /cam/realsense/rgb (best_effort)
    ├─ OG ROS2PublishJointState → /dsr01/joint_states, /robot/leg_joint_states (reliable)
    ├─ OG IsaacComputeOdometry + ROS2PublishOdometry → /robot/odom (reliable)
    ├─ OG ROS2SubscribeTwist    ← /robot/cmd_vel (reliable) ← C2 pub_cmd_vel
    │     ↓ _apply_cmd() → SpotController.set_cmd_vel(vx, vy, wz)
    └─ world.add_physics_callback("spot_ctrl", SpotController.on_physics_step)
         ↓ SpotFlatTerrainPolicy.forward(dt, [vx,vy,wz]) → 12-DOF leg position targets
         └─ arm DOF stow/aim → single apply_action call

[C2 PC, sub1_side]
  ros_bridge.py
    ├─ 구독: /dsr01/joint_states, /robot/leg_joint_states, /robot/odom (reliable)
    ├─ 구독: /robot/gps, /robot/state, /rosout, /c2/video/compressed
    └─ 발행: /robot/cmd_vel (Twist, reliable) ← POST /robots/{rid}/cmd_vel

  app.py
    └─ POST /robots/{rid}/cmd_vel → ros.pub_cmd_vel(linear, angular)
```

### 3.2 제거된 경로

- HTTP `/ingest/frame`, `/ingest/telemetry`, `/ingest/stats` (app.py)
- `_uplink_worker`, `_gather`, annotator (camera_publisher.py)
- `C2_INGEST_REPUBLISH`, `_republish_tick`, `_rp_*` publishers (ros_bridge.py)
- `C2_INGEST_URL`, `GP_HTTP_UPLINK` 환경변수 (런처)

---

## 4. SpotController 설계

### 4.1 DOF 분리 (spot_with_arm = 12-DOF legs + N-DOF arm)

`SpotFlatTerrainPolicy` 는 12-DOF 다리용으로 학습됨. `spot_with_arm` 은
추가 arm DOF를 가지므로 관측/행동 벡터 차원 불일치 발생. 해결:

- `_setup_dof_layout()`: 로봇 DOF 이름에서 `fl_/fr_/hl_/hr_` prefix → `leg_idx`,
  `arm0_` prefix → `arm_idx` 로 분리
- `_obs_legs()`: 48-dim 관측 벡터에 leg DOF(12개)만 사용 (정책 호환)
- `_forward()`: 단일 `apply_action` 호출로 leg 타깃(정책) + arm 타깃(stow/aim) 동시 설정

### 4.2 arm DOF 게인 패치

`initialize()` 후 `spot_env.yaml` 이 arm DOF를 모르므로 stiffness=0, damping=0.
`_patch_arm_gains()` 로 K=1000, D=50 (N·m/rad) 수동 설정.

### 4.3 명령 중재

```
teleop (0.5s 타임아웃) > nav_goal P-제어 > idle (zeros)
```

- `set_cmd_vel(vx, vy, wz)`: 타임스탬프 갱신 + `_vel_cmd` 업데이트
- `_nav_p_ctrl()`: 목표까지 거리 기반 vx, 헤딩 오차 기반 wz (P게인: 0.5, 2.0)

### 4.4 바인딩 안전성

`PolicyController.__init__` 은 prim 유효성 확인 후 유효하면 `AddReference` 스킵.
기존 `/World/Robot` prim → USD 레퍼런스 추가 없이 `SingleArticulation` 래핑만.

---

## 5. 환경변수 요약 (main_side)

| 변수 | 기본 | 설명 |
|---|---|---|
| `GP_ROS2_TELEM` | `1` | OG 텔레메트리 노드 활성 |
| `GP_ROS2_CMD` | `1` | `/robot/cmd_vel` OG 구독 |
| `GP_SPOT_CONTROL` | `1` | SpotController physics_callback 활성 |
| `GP_CMD_TOPIC` | `/robot/cmd_vel` | 구독 토픽명 재정의 |

---

## 6. 검증 체크리스트

- [ ] `run_camera_pub_gui.sh` 기동 → 로그: `SpotController 등록`, `[spot_ctrl] ready`
- [ ] `ros2 topic hz /robot/odom` → 63Hz (physics_dt=1/500, rendering_dt=1/50)
- [ ] `ros2 topic pub /robot/cmd_vel geometry_msgs/msg/Twist '{linear: {x: 0.6}}'` → Spot 전진
- [ ] `POST /robots/gp0/cmd_vel {"linear": 0.3}` → Spot 전진
- [ ] `GP_SPOT_CONTROL=0` → 텔레메트리 63Hz 유지(보행 없음)
- [ ] C2 DB: joint_snapshots 단일경로 적재, 중복행 없음

---

## 7. 위험 / 미결 사항

| 항목 | 상태 | 비고 |
|---|---|---|
| spot_policy.pt 최초 다운로드 | 네트워크 필요 | Isaac 자산 캐시에 저장됨 |
| spot_with_arm arm stow 값 | 근사값 사용 | 실제 기동 후 미세 조정 필요 |
| nav_goal OG Subscribe | 미구현 | PoseStamped OG 노드 없음; API 호출로 대체 가능 |
| physics_dt 변경(1/500) 효과 | 재측정 필요 | 기존 1/120에서 변경 → 카메라 Hz 재확인 |
