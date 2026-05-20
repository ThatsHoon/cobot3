# DMZ Sentry 구현 설명

이 문서는 통합자가 `main`에서 기능을 확장할 때 빠르게 따라갈 수 있도록, 현재 브랜치에 들어간 데모 기능이 어떤 파일에서 어떻게 이어지는지 정리한 구현 설명입니다.

## 한 줄 요약

Isaac Sim의 ANYmal 정찰 시뮬레이션을 중심으로 ROS 2 센서/제어 토픽, YOLO 사람 감지, Nav2 순찰, rosbridge 웹 전술 지도를 연결한 DMZ 경계 감시 데모입니다.

## 주요 기능

- Isaac Sim에서 DMZ 스타일 지형, 울타리, 강, 벙커, 감시탑, 움직이는 침입자 target을 생성합니다.
- ANYmal 전방 카메라는 YOLO 감지용 `/camera/image_raw`, `/camera/depth`, `/camera/camera_info`, `/camera/points`를 발행합니다.
- 별도 Inspector 카메라는 target 확인용 `/inspection_camera/image_raw`, `/inspection_camera/depth`, `/inspection_camera/camera_info`, `/inspection_camera/points`를 발행합니다.
- YOLO 노드는 `/camera/image_raw`에서 사람을 감지하고 `/detections_text`, `/alerts`, 선택적으로 `/camera/annotated`를 발행합니다.
- Nav2 순찰 컨트롤러는 웹의 `/mission_command`를 받아 `/navigate_to_pose` goal로 변환하고, alert가 들어오면 일시 정지 후 재개합니다.
- 웹 전술 지도는 rosbridge로 `/odom`, `/alerts`, `/patrol_state`, `/intruder_states`를 구독하고, `/mission_command`, `/inspection_camera/command`를 발행합니다.

## 핵심 파일

| 영역 | 파일 | 역할 |
| --- | --- | --- |
| Isaac Sim | `isaacsim/anymal_gp_terrain.py` | 지형/에셋/ANYmal/침입자/카메라/LiDAR/ROS 2 bridge 그래프를 생성하는 메인 시뮬레이션 |
| Perception | `ros2_ws/src/dmz_sentry_perception/dmz_sentry_perception/yolo_person_detector.py` | Ultralytics YOLO로 사람 감지, detection JSON과 alert 발행 |
| Control | `ros2_ws/src/dmz_sentry_control/dmz_sentry_control/nav2_patrol_controller.py` | mission command를 Nav2 goal로 변환하고 순찰/복귀/정지/재개 상태 관리 |
| Control | `ros2_ws/src/dmz_sentry_control/dmz_sentry_control/cmd_vel_safety_filter.py` | Nav2 속도 명령을 ANYmal에 맞게 drive/turn 모드로 제한 |
| Bridge | `ros2_ws/src/dmz_sentry_control/dmz_sentry_control/inspection_bridge.py` | 웹 카메라 명령과 Isaac Sim 파일 mailbox, 침입자 상태 토픽을 연결 |
| Nav2 | `ros2_ws/src/dmz_sentry_control/launch/dmz_nav2.launch.py` | map server, planner, controller, smoother, BT navigator, velocity smoother 실행 |
| Web | `web/tactical_map/index.html`, `web/tactical_map/app.js`, `web/tactical_map/style.css` | 웹 전술 지도 UI, target 클릭, 출격/홈/정지/재개, pan/tilt/zoom/clear 제어 |
| Scripts | `scripts/demo_*.sh` | Isaac Sim, ROS 노드, Nav2, rosbridge, 웹 서버 실행 래퍼 |

## 데이터 흐름

### 감지와 경보

```text
Isaac Sim SentryFrontCamera
-> /camera/image_raw
-> yolo_person_detector
-> /detections_text
-> /alerts
-> nav2_patrol_controller, web tactical map
```

`yolo_person_detector.py`는 `classes=[0]`으로 사람 class만 추론합니다. `alert_confidence` 이상인 detection이 있으면 cooldown을 적용해 `/alerts`에 JSON 문자열을 발행합니다.

### Target 위치 표시

```text
Isaac Sim IntruderScenario
-> /tmp/dmz_sentry_intruder_states.json
-> inspection_bridge
-> /intruder_states
-> web tactical map
```

현재 웹 지도 target 위치는 YOLO bbox와 depth로 추정한 값이 아니라 Isaac Sim이 알고 있는 ground-truth 좌표입니다. 그래서 지도 표시는 안정적이지만, 현실 확장 시에는 `/detections_text`, `/camera/depth`, `/camera/camera_info`, TF를 이용해 world 좌표를 추정하는 별도 tracker가 필요합니다.

### Inspector 카메라 제어

```text
web target click / pan / tilt / zoom / clear
-> /inspection_camera/command
-> inspection_bridge
-> /tmp/dmz_sentry_inspection_command.json
-> Isaac Sim inspection command poller
-> SentryInspectionCamera xform/focal length update
-> /inspection_camera/image_raw
```

Isaac Sim도 `/inspection_camera/command`를 직접 구독할 수 있고, 동시에 파일 mailbox도 poll합니다. 파일 mailbox는 rosbridge/ROS context가 엇갈릴 때를 대비한 느슨한 연결 방식입니다.

### 순찰 제어

```text
web sortie/home/stop/resume button
-> /mission_command
-> nav2_patrol_controller
-> /navigate_to_pose
-> Nav2 velocity_smoother
-> /cmd_vel_nav2_raw
-> cmd_vel_safety_filter
-> /cmd_vel
-> Isaac Sim ANYmal policy
```

`nav2_patrol_controller.py`는 홈, lane entry, 좌우 순찰 waypoint를 갖고 있습니다. `/alerts`가 들어오면 `ALERT_STOP`으로 전환해 goal을 취소하고 정지 명령을 냅니다. `alert_hold_seconds`가 지나면 이전 모드로 돌아가 다음 goal을 보냅니다.

## 실행 순서

ROS 2 패키지를 처음 실행하거나 수정했다면 먼저 빌드합니다.

```bash
cd /home/rokey/dev_ws/dmz_sentry/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install
```

데모는 아래 순서로 터미널을 나누어 실행합니다.

```bash
./scripts/demo_dmz_sim.sh
./scripts/demo_inspection_bridge.sh
./scripts/demo_yolo_detector.sh
./scripts/demo_nav2_bringup.sh
./scripts/demo_nav2_patrol_controller.sh
./scripts/demo_rosbridge.sh
./scripts/demo_tactical_map.sh
```

웹 지도는 `http://localhost:8080`에서 확인합니다. 카메라는 `rqt_image_view`에서 `/camera/annotated`와 `/inspection_camera/image_raw`를 보면 됩니다.

## 동작 확인 포인트

- `/camera/image_raw`, `/camera/depth`, `/camera/camera_info`, `/camera/points`가 발행되는지 확인합니다.
- `/inspection_camera/image_raw`, `/inspection_camera/depth`, `/inspection_camera/camera_info`, `/inspection_camera/points`가 발행되는지 확인합니다.
- `/alerts`에 `person_detected_near_fence` JSON이 나오는지 확인합니다.
- 웹 지도에서 target이 표시되고 target 클릭 시 Inspector 카메라가 해당 좌표를 바라보는지 확인합니다.
- 웹의 `출격`, `홈`, `정지`, `재개` 버튼이 `/mission_command`를 통해 Nav2 순찰 상태를 바꾸는지 확인합니다.
- `/navigate_to_pose` action이 보이고 `/cmd_vel`이 발행되는지 확인합니다.

## 현재 한계와 통합 시 참고사항

- target 지도 위치는 ground-truth 기반입니다. YOLO + depth 기반 world 좌표 추적은 아직 구현되어 있지 않습니다.
- Inspector 카메라는 실제 물리 짐벌이 아니라 USD 카메라 transform과 focal length를 코드로 갱신하는 가상 짐벌입니다.
- `assets.md`에 일부 외부 USDZ 에셋 출처와 라이선스가 TBD로 남아 있습니다. 공개 배포 전 정리가 필요합니다.
- `models/`와 `datasets/`, `runs/`는 `.gitignore` 대상입니다. 학습 모델은 로컬 경로 기준으로 실행 스크립트에서 참조합니다.
- Nav2는 SLAM이 아니라 정적 map과 `world` frame을 사용하는 known-map 데모 구성입니다.
