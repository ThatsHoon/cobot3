# Isaac/시뮬(main_side) PC 측 설정 (2-PC LAN)

> sub1_side/FASTDDS.md 와 **대칭 문서 — 발행측(Isaac PC) 관점**.
> 이 PC 는 카메라/텔레메트리를 내보내고(D-확장 또는 ROS2), 2-PC 정공
> 시 C2 명령 토픽을 받는다. 환경/기동 총괄: `../dev-docs/project_requirments.md`.

## 0. 전송 경로 2종 (둘 다 main_side 에서 출발)

| 경로 | 용도 | main_side 설정 |
|---|---|---|
| **D-확장 HTTP** (검증·운용중) | Isaac → C2 **영상·텔레메트리 관측**(단방향) | `C2_INGEST_URL` 만 C2 PC 로 (§1) |
| **ROS2 정공** (전송 prep) | C2 ↔ Isaac **양방향 토픽**(명령 다운링크 포함) | FastDDS 크로스호스트 (§2~§5) + **소비자 노드(§6, 미구현)** |

영상만 필요하면 D-확장으로 충분(현재 동작). C2 가 시뮬로 **명령 토픽
발송**하려면 ROS2 정공이 필요한데, 전송설정(§2~5)만으로는 부족하고
Isaac 측 **명령 구독·실행 노드(§6)** 가 있어야 실제 반영된다.

## 1. D-확장 업링크 대상 (영상 경로 — 현 운용)

`C2_INGEST_URL` = C2 웹서버. 같은-PC=localhost / 2-PC=C2 PC IP.
- repo 의 `run_camera_pub*.sh` 는 기본 `localhost`(하드코딩 없음).
- 2-PC 사이트값은 `~/.bashrc` `cobot3-isaacSim-gui` 에서 주입
  (`export C2_INGEST_URL=http://<C2_IP>:8000`, env override 가능).
- 검증: Isaac PC 에서 `curl -s http://<C2_IP>:8000/ingest/stats` 의
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

## 7. 카메라 장착 (수정 반영됨)

RealSense 는 `/World/Robot/m0609/m0609/link_6/realsense`(진짜 관절
플랜지)에 런타임 생성된다. 과거 씬 로컬화로 평탄경로
`/World/Robot/m0609/link_6` 빈 스캐폴드에 카메라가 박혀 detached 였던
버그는 `gp_scene.usd` 에서 스캐폴드 제거로 해결(camera_publisher 의
link_6 탐색이 실 플랜지에 재생성, 팔 추종). 기동 로그에
`created RealSense camera at /World/Robot/m0609/m0609/link_6/realsense`
가 찍히면 정상.

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
