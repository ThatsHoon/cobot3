# Foxglove 도입 런북 — C2(sub1_side) 디버그 시각화

목적: sub1_side 웹에 **`/debug` 라우트**를 추가하고, 그 안에서 Foxglove
(자체호스팅 **Lichtblick**)로 로봇 텔레메트리/영상을 렌더(참고 스크린샷 =
3D 패널 + Plot 스택 + Image).

> 상태: **구현 완료(2-PC 정공 모드)**. 텔레메트리·영상 ROS2 발행은
> 이미 코드에 있고, 2-PC 시각화는 Isaac 실토픽을 `foxglove_bridge` 가 직접 구독.
> 권위 설계: `../dev-docs/gp-quadruped-system-design.md`, 통신 전제: `FASTDDS.md`, 공개: `CLOUDFLARE.md`.

확정 결정: 데이터 = ROS2(`foxglove_bridge`) · 3D = 1단계 메시 없음
(TF/odom 축 + JointState) · 표시 = 기존 Next.js 앱 `/debug` iframe ·
뷰어 = docker Lichtblick :8080.

---

## 0. ⚠ 전제 / 제약 (먼저 읽을 것)

**(P1) 2-PC 정공이 기본 — foxglove_bridge 가 Isaac 실토픽 직접 구독.**
`foxglove_bridge` 는 시스템 ROS2(py3.10). Isaac 은 OG 내부 ROS2 브리지로
영상·텔레메트리를 발행하고, C2 PC 의 foxglove_bridge 가 LAN FastDDS 로
직접 수신. 재발행(C2_INGEST_REPUBLISH)은 제거됨.

**(P2) 텔레메트리 발행 구현됨.** `main_side/camera_publisher.py` 의 OG 가
`/cam/realsense/rgb`·`/dsr01/joint_states`·`/robot/leg_joint_states`·
`/robot/odom` 을, `main_side/telemetry_bridge_node.py` 가 `/robot/gps`·
`/robot/state` 를 발행(`FASTDDS.md §3.1`).

**(P3) 로봇 = spot_with_arm(단일 아티큘레이션).** Foxglove 는 USD 를 못
읽으므로 3D 로봇 메시는 **생략**(TF/odom 축 + JointState Plot).
Spot URDF/glTF 메시는 후속 단계.

---

## 1. 종단 아키텍처 (2-PC 정공)

```
[Main PC] Isaac OG/telemetry_bridge ── ROS2/FastDDS domain130 ──┐ LAN
[C2 PC]   video_degrade_node /cam/realsense/rgb→/c2/video/compressed
[C2 PC]   foxglove_bridge :8765 (Isaac 실토픽 직접 구독) → Lichtblick → /debug
   브라우저 ──TLS── Cloudflare(Access) ── (CLOUDFLARE.md)
```

`foxglove_bridge` 는 화이트리스트 없이 전 토픽 노출.

---

## 2. 사전 요구 (설치 완료 상태)

| 항목 | 상태 |
|---|---|
| `ros-humble-foxglove-bridge` | ✅ 설치됨 (3.3.0) |
| `docker.io` | ✅ 설치됨 (29.x). 임시 런북은 `sudo docker` 사용(그룹 재로그인 회피) |
| Lichtblick 이미지 | ✅ `ghcr.io/lichtblick-suite/lichtblick:latest`(Caddy :8080 정적 SPA, 검증됨) |
| ROS2 env | `ROS_DOMAIN_ID=130`, `RMW=rmw_fastrtps_cpp` (`FASTDDS.md`) |
| Cloudflare(2-PC 공개 시) | `CLOUDFLARE.md` — §"2-PC 정식" 참조 |

---

## S1 — Isaac→ROS2 텔레메트리 발행 (이미 구현됨 — 확인만)

별도 구현 불필요. 발행 주체·토픽(계약은 `server/config.py` TOPICS, QoS 는
RELIABLE — 영상만 BEST_EFFORT):

| 채널 | 토픽 | 타입 | 발행 주체 |
|---|---|---|---|
| state | `/robot/state` | std_msgs/String(JSON) | `telemetry_bridge_node`(odom 파생) |
| gps | `/robot/gps` | sensor_msgs/NavSatFix | `telemetry_bridge_node` |
| odom | `/robot/odom` | nav_msgs/Odometry | camera_publisher OG |
| arm | `/dsr01/joint_states` | sensor_msgs/JointState | camera_publisher OG(Spot 전체) |
| leg | `/robot/leg_joint_states` | sensor_msgs/JointState | camera_publisher OG(Spot 전체) |
| video | `/c2/video/compressed` | sensor_msgs/CompressedImage | video_degrade_node |

상세는 `../main_side/FASTDDS.md §3.1`. **같은-PC(M1)** 에선 위 토픽을
Isaac 가 DDS 로 직접 못 보내므로(불변식 #8), `ros_bridge.py` 가
`/ingest` 로 받은 동일 데이터를 같은 토픽명으로 **재발행**한다. arm/leg 는
`/ingest` 의 `arm_q`/`leg_q`(맨 float 리스트)에 합성 조인트명을 부여
(arm `arm0_j{i}`, leg `fl/fr/hl/hr × hx/hy/kn`).

---

## S2 — foxglove_bridge

런처 = `sub1_side/run_foxglove_bridge.sh`(생성됨). 도메인130·
rmw_fastrtps·site.sh FastDDS 프로파일 정합·`:8765`·화이트리스트 없음.

```bash
cd sub1_side && bash run_foxglove_bridge.sh   # 또는 bashrc 오케스트레이션
```

검증: `ros2 topic list` 에 재발행/실 토픽이 보이고 bridge 로그에
`Foxglove WebSocket server ... listening on 0.0.0.0:8765` + 클라이언트
connect. M1 에선 `ros2 node info /c2_web_server` 가 해당 토픽을
**publisher** 로 표시(= web_server PID 가 재발행 중).

---

## S3 — Lichtblick 자체호스팅 (docker, 검증됨)

이미지의 entrypoint 가 **`/lichtblick/default-layout.json`** 바인드마운트를
읽어 index.html 의 레이아웃 플레이스홀더에 주입한다(검증: 마운트 시 패널
ID 가 서빙 HTML 에 반영됨). 레이아웃 = `sub1_side/lichtblick/layout.json`
(3D[/tf,/robot/odom] · RawMessages[/robot/state] · Plot[arm] · Plot[leg] ·
Image[/c2/video/compressed]).

```bash
sudo docker rm -f cobot3-lichtblick 2>/dev/null
sudo docker run -d --name cobot3-lichtblick --restart unless-stopped \
  -p 8080:8080 \
  -v /home/rokey/dev_ws/isaac_sim/cobot3/sub1_side/lichtblick/layout.json:/lichtblick/default-layout.json:ro \
  ghcr.io/lichtblick-suite/lichtblick:latest
```

외부 SaaS(app.foxglove.dev) 임베드는 경계초소 데이터 외부 유출이라 금지
— 자체호스팅 Lichtblick 만. Spot 3D 메시(URDF/glTF, USD 불가)는 후속 확장.

---

## S4 — sub1_side/web `/debug` 라우트 (생성됨)

`app/page.tsx`·`layout.tsx` **무수정**. 신규 `app/debug/page.tsx` 가 루트
layout 자동 상속, `.panel` 스타일 + 전체화면 iframe. 데이터소스 자동연결:
`?ds=foxglove-websocket&ds.url=ws://localhost:8765`.

env(`lib/api.ts` `LICHTBLICK_URL`, 빌드타임 주입):
`NEXT_PUBLIC_LICHTBLICK_URL`(기본 `http://localhost:8080`).
**같은-PC 임시 검증 시 `.env.local` 의 `NEXT_PUBLIC_C2_API` 도
`http://localhost:8000` 로 둘 것** — prod https 오리진에 http Lichtblick
iframe 은 혼합콘텐츠로 차단됨. `NEXT_PUBLIC_*` 변경 시 `next dev` 재시작/
재빌드 필요.

---

## S5 — 2-PC 런북

Isaac `main_side/run_camera_pub.sh`(Play) → C2 PC `server/run.sh` →
foxglove_bridge → 브라우저 `http://C2_PC_IP:3000/debug`.

foxglove_bridge + Lichtblick 기동:
```bash
# C2 PC — foxglove_bridge
source /opt/ros/humble/setup.bash && export ROS_DOMAIN_ID=130 && \
  ros2 launch foxglove_bridge foxglove_bridge_launch.xml port:=8765 &
# Lichtblick
sudo docker run -d --name cobot3-lichtblick -p 8080:8080 \
  ghcr.io/lichtblick-suite/lichtblick:latest
```

Cloudflare 공개는 전용 호스트 권장 + **반드시 동일 Cloudflare Access 정책**:

```yaml
# cloudflared/config.yml ingress (CLOUDFLARE.md 확장)
  - hostname: cobot3-foxglove.thatshoon.com
    path: ^/ws(/.*)?$
    service: ws://localhost:8765
  - hostname: cobot3-foxglove.thatshoon.com
    service: http://localhost:8080
```
web env: `NEXT_PUBLIC_LICHTBLICK_URL=https://cobot3-foxglove.thatshoon.com`,
iframe ds.url 을 `wss://cobot3-foxglove.thatshoon.com/ws` 로.

---

## 6. 검증

**2-PC 정공**:
1. Isaac `run_camera_pub.sh` → Play. `ros2 topic list` → Isaac 토픽 보임.
2. `ros2 topic hz /robot/odom` → 63Hz, `ros2 topic hz /c2/video/compressed`.
3. `/tmp/cobot3_foxglove.log` listening 0.0.0.0:8765.
4. `http://C2_PC:3000/debug` → 3D 축 이동, State/Plot 스트림, Image 영상.
5. `ros2 node info /c2_web_server` 가 구독 + 업링크 pub(`/robot/cmd_vel`,
   `/robot/nav/goal`, `/robot/speaker/audio`). 텔레메트리 버스트 후
   `robot_state_log`/`gps_track`/`joint_snapshots` 중복행 0.

## 7. 트러블슈팅

| 증상 | 원인 | 조치 |
|---|---|---|
| Foxglove 토픽 0 | Isaac 미Play 또는 FastDDS 불일치 | `FASTDDS.md §6` 확인, `ros2 topic list` |
| 토픽 보이나 0 메시지 | QoS 불일치 | `FASTDDS.md §2` QoS 확인 |
| Image 패널 빈값 | 영상 프레임 미수신 | `/c2/video/compressed hz`, degrade 동작 확인 |
| iframe 빈 화면 | `NEXT_PUBLIC_*` 미주입 | `.env.local` 후 web 재빌드 |
| 혼합콘텐츠 차단 | prod https + http Lichtblick | 정식은 §S5 Cloudflare |
| docker 권한 | 그룹 미반영 | 임시 런북은 `sudo docker` |

---
관련: `../main_side/FASTDDS.md §3.1`(발행측) · `CLOUDFLARE.md` ·
`../dev-docs/gp-quadruped-system-design.md` · `server/config.py`(TOPICS) ·
`server/ros_bridge.py`(재발행/구독)
