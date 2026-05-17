# Isaac/시뮬(main_side) PC 측 설정 (2-PC LAN)

> sub1_side/FASTDDS.md 와 **대칭 문서 — 발행측(Isaac PC) 관점**.
> 이 PC 는 카메라/텔레메트리를 내보내고(D-확장 또는 ROS2), 2-PC 정공
> 시 C2 명령 토픽을 받는다. 환경/기동 총괄: `../dev-docs/project_requirments.md`.

## 0. 전송 경로 2종 (둘 다 main_side 에서 출발)

| 경로 | 용도 | main_side 설정 |
|---|---|---|
| **D-확장 HTTP** (검증·운용중) | Isaac → C2 **영상·텔레메트리 관측**(단방향) | `C2_INGEST_URL` 만 C2 PC 로 (§1) |
| **ROS2 정공 — 업링크** (발행측 구현됨) | Isaac → C2 영상·텔레메트리 토픽 | OG+노드 발행(§3.1) + FastDDS 크로스호스트(§2~§5) |
| **ROS2 정공 — 다운링크** (미구현) | C2 → Isaac **명령 토픽** | 전송(§2~§5) 가능하나 **소비자 노드(§6) 미구현** |

업링크 텔레메트리는 D-확장(HTTP)·ROS2 정공 **둘 다 동작**(병행, §3.1).
영상만 관측하면 D-확장으로 충분. 단 C2 가 시뮬로 **명령 토픽 발송**(다운링크)
하려면 전송설정(§2~5)만으로는 부족하고 Isaac 측 **명령 구독·실행
노드(§6)** 가 있어야 실제 반영된다 — 이 부분은 여전히 미구현.

## 1. D-확장 업링크 대상 (영상 경로 — 현 운용)

`C2_INGEST_URL` = C2 웹서버. 같은-PC=localhost / 2-PC=C2 PC IP.
- **IP 단일소스 = `../common/site.env`**(`SUB1_SIDE_IP`). 런처가
  `../common/site.sh` 의 `cobot3_c2_ingest_url` 로 `http://$SUB1_SIDE_IP:8000`
  **자동 파생**(bashrc·repo 하드코딩 없음). env 로 직접 주면 그 값 최우선.
- 배포지 변경 시 `common/site.env` 두 줄만 수정 → 양측 자동 반영.
- 검증: Isaac PC 에서 `curl -s http://$SUB1_SIDE_IP:8000/ingest/stats` 의
  `frame`/`tele` 카운트 증가 + 메인 로그 `uplink ok/err` 의 ok 증가.

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

- 토글: `GP_ROS2_TELEM`(기본 `1`). `0` 이면 OG 텔레메트리 노드 미생성
  (HTTP `/ingest` D-확장만). 영상 OG 는 토글과 무관하게 항상 발행.
- QoS: C2 `ros_bridge` 가 state/gps/odom/arm/leg 를 **RELIABLE** 구독 →
  OG 발행·`telemetry_bridge` 발행 모두 RELIABLE 명시(매칭). 영상만 BEST_EFFORT.
- sim-GPS 기준점(`LAT0/LON0/ALT0`)은 `camera_publisher._sim_gps` 와
  `telemetry_bridge_node._sim_gps` 가 **동일**해야 HTTP·ROS2 좌표가 일치.
- 기동: `run_telemetry_bridge.sh`(`run_degrade.sh` 형제, 시스템 ROS2).
  `cobot3-cobot3_web-restart_full` 가 degrade 와 함께 자동 기동.
- D-확장 HTTP `/ingest` 경로(`_gather`/`_uplink_worker`)는 **무손상 병행** —
  같은-PC(디스커버리 불가) 환경에서도 영상/텔레메트리는 계속 HTTP 로 수신.
- ⚠ **2-PC 정공 + HTTP 동시 활성 주의**: ROS2 디스커버리가 성립하는 2-PC 에서
  `C2_INGEST_URL` 까지 C2 로 향하면 C2 가 동일 텔레메트리를 ROS2·HTTP **두
  경로로 중복 수신**(DB 이중 적재·WS 이중 emit 가능). 정공 운용 시에는
  `C2_INGEST_URL` 을 미설정(또는 localhost 로 두어 도달 실패)하거나
  `GP_ROS2_TELEM=0` 으로 한쪽만 쓰는 것을 권장. 같은-PC 는 ROS2 0 이라 무관.

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

## 6. ⚠ 명령 다운링크 소비자 — 미구현 (한계 명시)

§2~5 로 **전송**은 열려도, 현재 `camera_publisher.py` 는 카메라 발행만
하고 `/robot/nav/goal`·`/robot/speaker`·`/robot/fire` 등 **명령 토픽을
구독하지 않는다**. locomotion/명령 처리 노드(보행 FSM 포함)가 미구현이라
C2 가 토픽을 보내도 시뮬에서 **아무도 실행하지 않는다**. ROS2 정공으로
"C2→시뮬 제어"를 완성하려면 이 구독·실행 노드 구현이 별도로 필요.

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
| C2 ros_bridge `ingest=LIVE`, 영상 OK | D-확장 정상 | 영상 경로 완료 |
| 메인 `uplink ok/err=0/N` | `C2_INGEST_URL` 미설정/오설정 | §1 — C2 IP·:8000 도달성 확인 |
| C2 `ros2 topic list` 에 Isaac 토픽 없음 | 멀티캐스트 차단/IP 오설정 | §3 initialPeers·interfaceWhiteList, §5 방화벽 |
| 토픽은 보이나 명령 미반응 | 소비자 노드 미구현 | §6 — 구현 필요(설정 문제 아님) |
| `last read: 's'`/`getRenderSettings` 폭주 | standalone+OG 양성 | 무해, 런처가 raw 보존+콘솔 필터(project_requirments §6) |

---
관련: [`../sub1_side/FASTDDS.md`](../sub1_side/FASTDDS.md) ·
`../dev-docs/project_requirments.md` §5 · `../dev-docs/gp-quadruped-system-design.md` Appendix-D
