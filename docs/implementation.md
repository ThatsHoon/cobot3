# DMZ Sentry 구현 설명

이 문서는 통합자가 `main`에서 기능을 확장할 때 빠르게 따라갈 수 있도록, 현재 브랜치에 들어간 데모 기능이 어떤 파일에서 어떻게 이어지는지 정리한 구현 설명입니다.

## 한 줄 요약

Isaac Sim의 ANYmal 정찰 시뮬레이션을 중심으로 ROS 2 센서/제어 토픽, YOLO 사람·사슴 감지, 순찰 컨트롤러, rosbridge 웹 전술 지도를 연결한 DMZ 경계 감시 데모입니다.

## 주요 기능

- Isaac Sim에서 DMZ 스타일 지형, 울타리, 강, 벙커, 감시탑, 움직이는 침입자 target을 생성합니다.
- ANYmal 전방 카메라는 항상 철책(world +Y) 방향을 향하며 YOLO 감지용 `/camera/image_raw`, `/camera/depth`, `/camera/camera_info`, `/camera/points`를 발행합니다.
- 별도 Inspector 카메라는 target 확인용 `/inspection_camera/image_raw`, `/inspection_camera/depth`, `/inspection_camera/camera_info`, `/inspection_camera/points`를 발행합니다.
- YOLO 노드는 `/camera/image_raw`에서 사람·사슴을 감지하고 `/detections_text`, `/alerts`(`/deer_alerts`), 선택적으로 `/camera/annotated`를 발행합니다.
- 순찰 컨트롤러는 웹의 `/mission_command`를 받아 직접 cmd\_vel을 발행하고, alert가 들어오면 일시 정지 후 재개합니다.
- 웹 전술 지도는 rosbridge로 `/odom`, `/alerts`, `/deer_alerts`, `/patrol_state`, `/intruder_states`를 구독하고, `/mission_command`, `/inspection_camera/command`를 발행합니다.

## 핵심 파일

| 영역 | 파일 | 역할 |
| --- | --- | --- |
| Isaac Sim | `isaacsim/anymal_gp_terrain.py` | 지형/에셋/ANYmal/침입자/카메라/LiDAR/ROS 2 bridge 그래프를 생성하는 메인 시뮬레이션 |
| Perception | `ros2_ws/src/dmz_sentry_perception/dmz_sentry_perception/yolo_person_detector.py` | Ultralytics YOLO로 사람·사슴 감지, detection JSON과 alert 발행, `robot_x/y/yaw`, `bbox_xyxy`, `image_width` 포함 |
| Control | `ros2_ws/src/dmz_sentry_control/dmz_sentry_control/patrol_controller.py` | mission command를 받아 cmd\_vel로 직접 순찰/복귀/정지/재개 상태 관리 |
| Control | `ros2_ws/src/dmz_sentry_control/dmz_sentry_control/cmd_vel_safety_filter.py` | 속도 명령을 ANYmal에 맞게 drive/turn 모드로 제한 |
| Bridge | `ros2_ws/src/dmz_sentry_control/dmz_sentry_control/inspection_bridge.py` | 웹 카메라 명령과 Isaac Sim 파일 mailbox, 침입자 상태 토픽을 연결 |
| Web | `web/tactical_map/index.html` | 웹 전술 지도 HTML — 전방 카메라·Inspector 카메라 피드 2개 포함 |
| Web | `web/tactical_map/app.js` | rosbridge 연결, target 클릭→look\_at 커맨드, 출격/홈/정지/재개, pan/tilt/zoom/clear 제어 |
| Web | `web/tactical_map/style.css` | 전술 지도 UI 스타일 |
| Scripts | `scripts/demo_*.sh` | Isaac Sim, ROS 노드, rosbridge, 웹 서버 실행 래퍼 |

## 데이터 흐름

### 감지와 경보

```text
Isaac Sim SentryFrontCamera (항상 철책/+Y 방향 고정)
-> /camera/image_raw
-> yolo_person_detector (사람: /alerts, 사슴: /deer_alerts)
-> patrol_controller (경보 시 정지)
-> web tactical map (감지 dot 표시)
```

`yolo_person_detector.py`는 `detect_classes=[0]`으로 사람, `[1]`로 사슴을 구분합니다. alert payload에는 `robot_x`, `robot_y`, `robot_yaw`, `bbox_xyxy`, `image_width`가 포함되며, 웹에서 철책 위 추정 좌표 계산에 사용됩니다.

### 감지 위치 추정 (웹)

```text
alert payload (robot_x/y, bbox_xyxy, image_width)
-> estimateDetectionWorldPos()
   - 카메라 방향: 고정 +Y (CAMERA_YAW = π/2)
   - 감지 깊이: FENCE_WORLD_Y(16) - robot_world_y - 1.5
   - 횡방향 오프셋: depth * tan(bboxCenterNorm * HFOV)
   - 실제 카메라 파라미터: focal=18mm, aperture=21mm → HFOV≈60.5°
-> deer/person dot 좌표 (world Y ≈ 14.5, X 값 다양)
```

### Target 위치 표시 (침입자)

```text
Isaac Sim IntruderScenario (ground-truth world 좌표)
-> /tmp/dmz_sentry_intruder_states.json
-> inspection_bridge
-> /intruder_states
-> web tactical map (intruder marker)
```

### Inspector 카메라 제어

```text
web target click / pan / tilt / zoom / clear
-> /inspection_camera/command  (JSON: action, x, y, z, focal_length)
-> inspection_bridge
-> /tmp/dmz_sentry_inspection_command.json  (sequence 번호 포함)
-> Isaac Sim inspection command poller (_FileStringMailbox)
-> SentryInspectionCamera xform + focal length 갱신
-> /inspection_camera/image_raw
```

target 클릭 시 `focal_length: 70`(기본 35mm의 2배)을 함께 전송해 자동 줌인합니다. Clear 시 `action: "clear"`로 focal length가 35mm로 복원됩니다.

Isaac Sim은 `/inspection_camera/command`를 직접 ROS 구독(`_OptionalRosStringSubscriber`)하기도 하지만, rosbridge context 간 충돌 방지를 위해 파일 mailbox 경로(`inspection_bridge.py`)를 사용하는 것이 더 안정적입니다.

### 순찰 제어

```text
web 출격/홈/정지/재개 버튼
-> /mission_command
-> patrol_controller
-> /cmd_vel
-> Isaac Sim ANYmal policy
```

`patrol_controller.py`는 홈, 좌우 순찰 waypoint를 가지고 있습니다. `/alerts`가 들어오면 `ALERT_STOP`으로 전환해 정지 명령을 냅니다. `alert_hold_seconds`가 지나면 이전 모드로 돌아갑니다.

## 실행 순서

ROS 2 패키지를 처음 실행하거나 수정했다면 먼저 빌드합니다.

```bash
cd ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
```

데모는 아래 순서로 터미널을 나누어 실행합니다.

```bash
./scripts/demo_dmz_sim.sh          # Isaac Sim 시뮬레이션
./scripts/demo_inspection_bridge.sh # Inspector 카메라 명령 브릿지
./scripts/demo_person_detector.sh   # 사람 YOLO 감지
./scripts/demo_deer_detector.sh     # 사슴 YOLO 감지
./scripts/demo_patrol_controller.sh # 순찰 컨트롤러
./scripts/demo_camera_stream.sh     # 카메라 압축 스트림 변환
./scripts/demo_rosbridge.sh         # ROS 2 ↔ WebSocket 브릿지
./scripts/demo_tactical_map.sh      # 웹 서버 (http://localhost:7070)
```

웹 지도는 `http://localhost:7070`에서 확인합니다.

## 좌표 변환 참고

| 좌표계 | 설명 |
| --- | --- |
| Isaac Sim world | Z-up, 철책 Y=16, 로봇 스폰 world Y=-12 |
| ROS odom | 스폰 시점 (0,0) 기준. `world_y = odom_y + SPAWN_Y_OFFSET(-12)` |
| 웹 지도 | `worldToCanvas()` 함수로 world 좌표 → canvas px 변환 |

`SPAWN_Y_OFFSET = -12`는 `app.js` 상단에 상수로 정의됩니다.

## 동작 확인 포인트

- `/camera/image_raw`, `/inspection_camera/image_raw`가 발행되는지 확인합니다.
- `/alerts`에 `person_detected_near_fence` JSON이 나오는지 확인합니다 (`robot_x/y/yaw`, `bbox_xyxy`, `image_width` 포함 여부 확인).
- 웹 지도에서 target dot이 철책선(Y≈14.5) 근처에 표시되는지 확인합니다.
- target dot 클릭 시 Inspector 카메라가 해당 방향으로 pan하고 2배 줌인되는지 확인합니다.
- 웹의 `출격`, `홈`, `정지`, `재개` 버튼이 순찰 상태를 바꾸는지 확인합니다.
- `/tmp/dmz_sentry_inspection_command.json` 파일이 target 클릭 후 갱신되는지 확인합니다 (inspection_bridge 정상 동작 확인).

## 현재 한계와 통합 시 참고사항

- target 지도 위치(침입자)는 ground-truth 기반입니다. YOLO + depth 기반 world 좌표 추적은 아직 구현되어 있지 않습니다.
- YOLO 감지 dot 위치는 카메라 고정 방향(+Y)과 bbox 중심으로 추정한 값입니다. 실제 깊이 센서 데이터 연동 시 정확도가 향상됩니다.
- Inspector 카메라는 실제 물리 짐벌이 아니라 USD 카메라 transform과 focal length를 코드로 갱신하는 가상 짐벌입니다.
- `assets.md`에 일부 외부 USDZ 에셋 출처와 라이선스가 TBD로 남아 있습니다. 공개 배포 전 정리가 필요합니다.
- `models/`와 `datasets/`, `runs/`는 `.gitignore` 대상입니다. 학습 모델은 로컬 경로 기준으로 실행 스크립트에서 참조합니다.
