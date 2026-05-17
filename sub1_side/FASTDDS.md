# 웹/C2 PC 측 FastDDS 설정 (2-PC LAN ROS2 정공)

> 이 문서는 **실배포 2-PC LAN** 에서 C2 PC 의 web_server(`ros_bridge.py`)가
> 시뮬 PC(Isaac)의 ROS2 토픽을 안정적으로 수신하기 위한 설정을 다룬다.
> 같은-PC 의 **Isaac↔web_server 텔레메트리**는 D-확장 HTTP `/ingest` 우회라
> 그 홉은 DDS 무관. 단 같은-PC **M1 재발행→foxglove_bridge** 는 같은 호스트
> 안의 DDS 홉이므로 DDS 설정이 **필요**하다(2-PC web 프로파일은 SHM off+
> 단일 peer+단일 NIC whitelist 라 같은-PC 디스커버리를 막음 → 그 경우
> FastDDS 기본 빌트인(SHM/멀티캐스트/loopback) 사용 = 프로파일 미지정).
> (`../dev-docs/gp-quadruped-system-design.md` Appendix-D, `project_requirments.md` §5).

## 왜 FastDDS 인가 (CycloneDDS 아님)

- Isaac Sim 은 NVIDIA 동봉 **FastDDS** 로 발행 → 받는 C2 PC 도 같은
  RMW 여야 함. 크로스-벤더(FastDDS↔Cyclone) RMW 혼용은 ROS2 가 **비지원**.
- "크로스-호스트는 Cyclone 이 손 덜 간다"는 평은 사실이나, FastDDS 는
  아래 4가지를 프로파일에 **명시**하면 Cyclone 수준으로 안정화됨.
  Cyclone 이 암묵적으로 해주던 걸 FastDDS 는 적어줘야 하는 차이일 뿐.

## 1. 환경변수 (C2 PC, web_server 프로세스)

`server/run.sh` 가 자동 설정. 핵심값:

| 변수 | 값 | 비고 |
|---|---|---|
| `RMW_IMPLEMENTATION` | `rmw_fastrtps_cpp` | Isaac 과 통일(필수) |
| `FASTRTPS_DEFAULT_PROFILES_FILE` | site.env 자동 치환본 | **§3** |
| `ROS_DOMAIN_ID` | `130` | 양 PC 동일 |
| `ROS_LOCALHOST_ONLY` | `0` | `1` 이면 크로스호스트 차단 |

`server/run.sh` 는 `../../common/site.sh` 를 source 하여 미지정 시
`cobot3_fastdds_profile web`(= `~/.config/cobot3/fastdds_web.xml`,
`common/site.env` IP 자동 치환)을 사용하고, site.sh 없으면 placeholder
`sub1_side/fastdds_web.xml` 로 폴백. env 로 직접 주면 그 값 최우선
(main_side 런처와 대칭 — IP 단일소스).

## 2. 코드 측 QoS (이미 반영됨 — 수정 불필요)

`server/ros_bridge.py` 가 이미 올바르게 설정:

- 영상(`CompressedImage`) → `BEST_EFFORT`(sensor_qos). Isaac 이미지
  토픽은 BEST_EFFORT 라 구독자가 RELIABLE 이면 **연결돼도 0 메시지**.
- state/gps/odom/arm/leg/rosout → `RELIABLE`.

QoS 불일치는 DDS 벤더 무관 함정이므로 변경 시 이 매칭을 깨지 말 것.

## 3. 프로파일 `fastdds_web.xml` — 배포 전 치환 필수

같은 폴더의 [`fastdds_web.xml`](fastdds_web.xml). 핵심 4요소:

1. **SHM 제거 + UDPv4 only** (`useBuiltinTransports=false` + UDPv4
   transport) — 호스트 못 넘는 전송 배제(NVIDIA 문서 해법).
2. **initialPeers 유니캐스트** — `__MAIN_PC_IP__` 를 시뮬 PC LAN IP 로.
   사내 스위치가 멀티캐스트(IGMP 스누핑)를 막아도 디스커버리 성공.
   → 크로스-호스트 "Publisher 0" 의 1순위 원인 차단.
3. **interfaceWhiteList** — `__C2_LAN_IP__` 를 이 PC LAN NIC IP 로.
   `docker0`/`br-…`/wifi 로 잘못 announce 하는 함정 차단.
4. **버퍼 4MB** — 압축영상 프레임 단편화 드랍 방지(아래 OS 버퍼와 함께).

**IP 단일소스 = `../common/site.env`** (`MAIN_SIDE_IP`/`SUB1_SIDE_IP`).
`fastdds_web.xml` 은 placeholder 보관용. 치환본은 `common/site.sh` 로 생성:

```bash
source /home/rokey/dev_ws/isaac_sim/cobot3/common/site.sh
export FASTRTPS_DEFAULT_PROFILES_FILE="$(cobot3_fastdds_profile web)"
#  → ~/.config/cobot3/fastdds_web.xml (repo·placeholder 오염 없음)
ip -4 addr show   # SUB1_SIDE_IP = 이 PC 실제 LAN NIC (docker0/wlan 아님)
```
배포지 바뀌면 **site.env 만 수정**(양측 자동 반영). web_server `run.sh`
도 동일 헬퍼로 자동 적용하도록 연동 가능. 멀티캐스트 허용 LAN 이면
`<initialPeersList>` 절은 삭제 가능.

## 4. OS 커널 버퍼 (C2 PC, 1회·영구)

프로파일 버퍼만으로 부족 — 커널 상한이 작으면 그대로 드랍.

```bash
echo 'rokey1234' | sudo -S tee /etc/sysctl.d/60-dds.conf >/dev/null <<'EOF'
net.core.rmem_max=8388608
net.core.wmem_max=8388608
EOF
echo 'rokey1234' | sudo -S sysctl --system
```

## 5. 방화벽 (C2 PC)

DDS UDP 포트는 `ROS_DOMAIN_ID` 기반으로 가변 → 서브넷 단위 허용이 안전.

```bash
echo 'rokey1234' | sudo -S ufw allow from 192.168.10.0/24   # LAN 대역(site.env IP 기준)
```

## 6. 검증 / 트러블슈팅

```bash
source /opt/ros/humble/setup.bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_DOMAIN_ID=130 ROS_LOCALHOST_ONLY=0
export FASTRTPS_DEFAULT_PROFILES_FILE=$PWD/fastdds_web.xml
ros2 topic list                       # 시뮬 PC 토픽 보이면 디스커버리 OK
ros2 topic hz /c2/video/compressed    # 영상 수신율
```

| 증상 | 원인 | 조치 |
|---|---|---|
| **C2 토픽 0 인데 Isaac 는 ROS2 발행 중**(로그 `OG 텔레메트리 발행`) | ★1순위★ **Isaac 가 2-PC 치환본이 아닌 `fastdds_no_shm.xml`(initialPeers 0개=멀티캐스트 전용)로 기동** → 크로스호스트 멀티캐스트 차단 시 C2 가 영영 못 봄 | Isaac PC: `cat /proc/$(pgrep -f camera_publisher.py\|head -1)/environ \| tr '\0' '\n' \| grep FASTRTPS` → `~/.config/cobot3/fastdds_main.xml`(initialPeers→C2) 여야. `fastdds_no_shm.xml` 이면 폴백된 것 — `cobot3-start_all_2`(MAIN) 가 이제 명시 export. 수동 시 `FASTRTPS_DEFAULT_PROFILES_FILE="$(cobot3_fastdds_profile main)"` 후 재기동 |
| `ros2 topic list` 에 시뮬 토픽 없음 / publishers=0 | 멀티캐스트 차단 또는 IP 오설정 | 위 항목 먼저, 그다음 §3 initialPeers·interfaceWhiteList(양 PC site.env=실 NIC), 방화벽 §5(UDP — HTTP TCP 되어도 UDP 별도 차단 가능) |
| 토픽은 보이나 영상만 0 | QoS 불일치 또는 멀티-NIC | §2 QoS 유지 확인, §3 interfaceWhiteList IP 확인 |
| 영상 끊김/지연 | 버퍼 부족 | §3 버퍼·§4 OS 버퍼, video_degrade 동작 확인 |
| ros_bridge HEALTH `ingest=LIVE` 인데 rx 0 | 정공 DDS 미성립, HTTP /ingest 폴백 동작 중 | 위 1·2순위(거의 항상 Isaac 프로파일 폴백 또는 양측 site.env/NIC 불일치·UDP 방화벽) |

ros_bridge 의 5초 주기 `HEALTH` 로그(`rx=… publishers=… ingest=…`)와
WS `diag` 이벤트가 1차 진단원. publishers>0 인데 rx=0 → QoS/RMW 의심.

---
관련: `../dev-docs/project_requirments.md` §5·§6 · `gp-quadruped-system-design.md` §4·Appendix-D · `README.md`
