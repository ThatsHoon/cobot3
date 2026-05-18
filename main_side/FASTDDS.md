# Isaac/시뮬(main_side) PC 측 설정 (2-PC LAN)

> sub1_side/FASTDDS.md 와 **대칭 문서 — 발행측(Isaac PC) 관점**.
> 이 PC 는 카메라/텔레메트리를 내보내고(D-확장 또는 ROS2), 2-PC 정공
> 시 C2 명령 토픽을 받는다. 환경/기동 총괄: `../dev-docs/project_requirments.md`.

## 0. 전송 경로 (ROS2 정공 단일 경로)

| 경로 | 용도 | main_side 설정 |
|---|---|---|
| **ROS2 정공 — 업링크** (구현·검증됨) | Isaac → C2 영상·텔레메트리 토픽 | OG+노드 발행(§3.1) + FastDDS(§2~§5). no-scrub 필수(§6.1) |
| **ROS2 정공 — 다운링크** (✅ 구현·검증됨) | C2 → Isaac **명령 토픽 → SpotController(RL 보행)** | OG `ROS2SubscribeTwist` → `SpotController.set_cmd_vel`(§6.2). `GP_SPOT_CONTROL` 토글(§6.3) |

HTTP `/ingest` 경로는 제거됨 — ROS2 정공 단일 경로(이중수신 문제 구조적 소멸).
다운링크(C2→Isaac) **양방향 정공 실증 완료 + SpotController(RL 보행 정책) 구현**.
ROS2 정공은 **no-scrub + 완전 8키 qosProfile + render=True** 가 필수(§6.1).

## 1. ROS2 정공 단일 경로 개요

HTTP `/ingest` 업링크 제거 — 영상·텔레메트리·명령 모두 ROS2 정공 단일 경로:
- **업링크** (Isaac → C2): OG `ROS2CameraHelper`(`/cam/realsense/rgb`) +
  OG `PublishJointState`·`PublishOdometry`(텔레메트리). `run_camera_pub*.sh` 기동.
- **다운링크** (C2 → Isaac): C2 `POST /robots/{rid}/cmd_vel` →
  `ros_bridge.pub_cmd_vel` → `/robot/cmd_vel`(Twist) →
  Isaac OG `ROS2SubscribeTwist` → `SpotController.set_cmd_vel` → RL 보행 정책.
- **IP/프로파일 단일소스**: `../common/site.env` → `common/site.sh` 로
  FastDDS 치환본 자동 생성. 배포지 변경 시 두 줄만 수정.

## 2. 환경변수 (Isaac PC, camera_publisher 프로세스)

| 변수 | 값 | 비고 |
|---|---|---|
| `RMW_IMPLEMENTATION` | `rmw_fastrtps_cpp` | C2 와 통일(필수) |
| `FASTRTPS_DEFAULT_PROFILES_FILE` | 치환된 `fastdds_main.xml` 절대경로 | §3 |
| `ROS_DOMAIN_ID` | `130` | 양 PC 동일 |
| `ROS_LOCALHOST_ONLY` | `0` | `1` 이면 크로스호스트 차단 |

`run_camera_pub*.sh` / bashrc `isaac`·`cobot3-isaacSim-gui` 가 설정.
2-PC 정공 시 프로파일을 §3 치환본으로 가리키게 한다.

## 3. 프로파일 자동 생성 — `common/site.env`(SSOT)

IP 는 **`../common/site.env`** 한 곳만 수정한다(`MAIN_SIDE_IP`/`SUB1_SIDE_IP`).
repo 의 [`fastdds_main.xml`](fastdds_main.xml) 은 placeholder 보관용이고,
런처(`run_camera_pub*.sh`)가 `../common/site.sh` 의
`cobot3_fastdds_profile main` 으로 **치환본을 `~/.config/cobot3/
fastdds_main.xml` 에 자동 생성**해 `FASTRTPS_DEFAULT_PROFILES_FILE` 로
가리킨다(repo·bashrc 하드코딩 없음, placeholder 파일 오염 없음).

수동으로 강제하려면(디버그 등):
```bash
source ~/dev_ws/isaac_sim/cobot3/common/site.sh
export FASTRTPS_DEFAULT_PROFILES_FILE="$(cobot3_fastdds_profile main)"
ip -4 addr show   # MAIN_SIDE_IP = 실제 LAN NIC IP (docker0/wlan 아님)
```
env 로 `FASTRTPS_DEFAULT_PROFILES_FILE` 를 직접 주면 그 값이 최우선.
멀티캐스트 허용 LAN 이면 `<initialPeersList>` 없이 `fastdds_no_shm.xml`
로도 충분 — 막힌 환경에서 Publisher 0 방지가 핵심.

## 3.1 ROS2 정공 업링크 텔레메트리 (발행측 구현됨)

`rclpy` 를 Isaac(py3.11)에서 import 하면 시스템 ROS2(py3.10) ABI 충돌이라
`run_camera_pub.sh` 가 시스템 ROS 를 의도적으로 scrub 한다. 그래서 텔레메트리도
영상과 **동일하게 OG 내부 ROS2 브리지로만** 발행한다(rclpy 미사용).

| 토픽 | 타입 | 발행 주체 | 비고 |
|---|---|---|---|
| `/cam/realsense/rgb` | sensor_msgs/Image | camera_publisher OG (`ROS2CameraHelper`) | → `video_degrade_node` → `/c2/video/compressed` |
| `/dsr01/joint_states` | sensor_msgs/JointState | camera_publisher OG (`ROS2PublishJointState`, Spot 단일 아티큘레이션 전체) | RELIABLE |
| `/robot/leg_joint_states` | sensor_msgs/JointState | camera_publisher OG (Spot 동일 아티큘레이션) — arm/leg 의미분리는 HTTP `_gather` 가 조인트명 prefix 로 | RELIABLE |
| `/robot/odom` | nav_msgs/Odometry | camera_publisher OG (`ComputeOdometry`+`ROS2PublishOdometry`, Spot base `/World/Robot/base`) | RELIABLE |
| `/robot/gps` | sensor_msgs/NavSatFix | `telemetry_bridge_node` (odom→sim-GPS 파생) | OG 정규노드 없음 |
| `/robot/state` | std_msgs/String(JSON) | `telemetry_bridge_node` (mode/gait/battery/waypoint 합성) | `extra.synthetic=true` |

- 토글: `GP_ROS2_TELEM`(기본 `1`) — `0` 이면 OG 텔레메트리 노드 미생성.
  HTTP `/ingest` 경로는 제거(이중수신 문제 구조적 소멸). 영상 OG 는 토글 무관 항상 발행.
- QoS: C2 `ros_bridge` 가 state/gps/odom/arm/leg 를 **RELIABLE** 구독 →
  OG 발행·`telemetry_bridge` 발행 모두 RELIABLE 명시(매칭). 영상만 BEST_EFFORT.
- sim-GPS 기준점은 `telemetry_bridge_node._sim_gps` 와 동일 좌표계 유지.
- 기동: `run_telemetry_bridge.sh`(`run_degrade.sh` 형제, 시스템 ROS2).
  `cobot3-cobot3_web-restart_full` 가 degrade 와 함께 자동 기동.

## 4. OS 커널 버퍼 (Isaac PC, 1회·영구)

```bash
echo 'rokey1234' | sudo -S tee /etc/sysctl.d/60-dds.conf >/dev/null <<'EOF'
net.core.rmem_max=8388608
net.core.wmem_max=8388608
EOF
echo 'rokey1234' | sudo -S sysctl --system
```

## 5. 방화벽 (Isaac PC)

DDS UDP 포트는 도메인 기반 가변 → C2 서브넷 허용.

```bash
echo 'rokey1234' | sudo -S ufw allow from 192.168.10.0/24
```

## 6. 명령 다운링크 소비자 — ✅ 구현·검증됨 (양방향 정공 성립)

### 6.1 결론 — 이전 "정공 불가"는 오진, 근본원인 3종

엄밀 실험(`test_ros2_bridge.py` + production `camera_publisher.py`)으로
**시스템 ROS2 Humble ↔ Isaac 내부 OG 브리지 양방향 통신이 동작함을 실증**.
DDS 버전(3.47/2.14)·Python 3.10/3.11 rclpy·CycloneDDS articulation 은
**전부 무관**이었고, 진짜 원인은 다음 3가지:

| # | 근본원인 | 수정 |
|---|---|---|
| 1 | 루프가 `world.step(render=False)` → 타임라인 동결 → OnPlaybackTick 펄스 미발생 → OG ROS2 노드가 write/read 자체를 안 함 | `render=True` (camera_publisher.py 는 원래 이미 적용; test 하네스만 오류였음) |
| 2 | `run_camera_pub*.sh` 의 시스템 ROS scrub → C++ 브리지가 시스템 fastrtps 2.6.11(=C2 동일·와이어호환) 대신 internal/엉뚱 libs 사용(자해). camera_publisher.py 는 rclpy 미사용이라 scrub 전제가 성립 안 함 | 런처에서 scrub 제거, `source /opt/ros/humble/setup.bash` (no-scrub) |
| 3 | Isaac qosProfile JSON 파서는 8키 전부 요구(history/depth/reliability/durability/deadline/lifespan/liveliness/leaseDuration). 부분 JSON `_REL_QOS`·문자열 `"sensor_data"` → 거부 → 엔드포인트 미생성 + 25k 파서 스팸 | 완전 8키 JSON `_REL_QOS`(reliable)·`_SENSOR_QOS`(bestEffort) |

검증 수치(no-scrub + fastdds_no_shm.xml + domain 130, 같은 PC 2프로세스):
`/robot/odom`·`/dsr01/joint_states` 업링크 **63Hz**, `/clock` 최소테스트
**122Hz**, `/robot/cmd_vel` 다운링크 Isaac 측 **RX 637회/10s** 수신.

### 6.2 구현된 다운링크 소비자 + SpotController

`camera_publisher.py` 단일 OG 빌드에 `ROS2SubscribeTwist`(SubCmd) 통합
(OnTick/Ctx 재사용; 증분 `og.Controller.edit` 는 그래프 재-wrap 실패하므로
메인 빌드에 포함). 토글·동작:

| env | 기본 | 효과 |
|---|---|---|
| `GP_ROS2_CMD` | `1` | `/robot/cmd_vel`(geometry_msgs/Twist) RELIABLE 구독 |
| `GP_CMD_TOPIC` | `/robot/cmd_vel` | 구독 토픽명 |
| `GP_SPOT_CONTROL` | `1` | `SpotController` (RL 보행 정책) 활성. 0=관측 전용 |

매 스텝 `_apply_cmd()`: SubCmd 출력(lin/ang)을 읽어 `SpotController.
set_cmd_vel(vx, vy, wz)` 로 전달. `SpotController` 는 physics_callback 에서
`SpotFlatTerrainPolicy.forward(dt, [vx,vy,wz])` 로 RL 보행 정책 실행
(teleop 0.5s 타임아웃 → nav_goal P-제어 → idle 순 우선순위 중재).
팔(arm0_* DOFs) 은 stow/aim 포즈로 독립 제어.

`World(physics_dt=1/500, rendering_dt=1/50)` — `spot_env.yaml` 요구 주기.

### 6.3 SpotController 토글/확장

| env | 기본 | 효과 |
|---|---|---|
| `GP_SPOT_CONTROL` | `1` | SpotController + physics_callback 활성 |
| `GP_SPOT_CONTROL=0` | — | 보행 정책 비활성, 관측(OG 텔레메트리)만 동작 |

nav_goal · speaker · fire 는 `SpotController.{set_nav_goal,set_speaker,trigger_fire}` API 로 확장 가능(현재 로그 출력 구현). OG Subscribe 추가 없이 camera_publisher 측 Python 코드에서 직접 호출하거나, PoseStamped/String OG 구독 노드 추가 후 핸들러에서 호출.

## 7. 카메라 장착 (Spot 기준)

로봇은 **spot_with_arm**(4족+팔 단일 아티큘레이션, S3 레퍼런스).
RealSense 는 `gp_scene.usd` 에 Spot 팔 끝
`/World/Robot/arm0_link_wr1/realsense` 로 **이미 저장**돼 있다
(전방 hand-eye: 손목 로컬 +X 0.06 이동·−Z→+X 회전). 마이크/확성기/
GPS 표식도 같은 손목(`arm0_link_wr1`) 하위. camera_publisher 는 이
경로를 그대로 쓰고, 없을 때만(구 씬) 손목 하위에 재생성한다. 기동 로그
`created RealSense camera at /World/Robot/arm0_link_wr1/realsense`
(또는 `RealSense camera present: …`) 가 정상.

## 8. 검증 / 트러블슈팅

| 증상 | 원인 | 조치 |
|---|---|---|
| C2 `ros2 topic list` 에 Isaac 토픽 없음 | 멀티캐스트 차단/IP 오설정 | §3 initialPeers·interfaceWhiteList, §5 방화벽 |
| 토픽은 보이나 cmd_vel 미반응 | SpotController 미기동 또는 GP_SPOT_CONTROL=0 | 로그 `SpotController 등록` 확인, `[spot_ctrl] ready` 로그 확인 |
| SpotController policy init 실패 | spot_policy.pt 다운로드 실패(최초 실행) | 네트워크 확인, `~/.cache/ov/asset` 캐시 확인 |
| `last read: 's'`/`getRenderSettings` 폭주 | standalone+OG 양성 | 무해, 런처가 raw 보존+콘솔 필터(project_requirments §6) |

---
관련: [`../sub1_side/FASTDDS.md`](../sub1_side/FASTDDS.md) ·
`../dev-docs/project_requirments.md` §5 · `../dev-docs/gp-quadruped-system-design.md` Appendix-D
