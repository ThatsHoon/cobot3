# cobot3

Isaac Sim에서 Unitree Go2 4족보행 로봇을 움직이고, 웹 화면에서 카메라와
전술 지도를 보는 프로젝트입니다.

쉽게 말하면:

- Isaac Sim 컴퓨터는 로봇과 맵을 실행합니다.
- C2 웹 컴퓨터는 영상을 보고, 로봇을 조종하고, 탐지 결과를 표시합니다.
- 큰 맵 파일은 GitHub에 올리지 않고 Google Drive로 따로 받습니다.

## 이번 브랜치에서 추가된 기능

이 브랜치는 기존 cobot3에 우리가 작업한 기능을 합친 버전입니다.

- `main_side`와 `sub1_side` 구조로 정리했습니다.
- Unitree Go2 로봇을 Isaac Sim에서 실행합니다.
- 로봇 카메라 영상을 웹에서 볼 수 있습니다.
- TP_A, TP_B, TP_C, TP_D 위치에 고정 감시 카메라를 만들었습니다.
- TP 카메라 위치에 감시탑 모델을 배치했습니다.
- TP 카메라 RGB와 depth 토픽을 발행합니다.
- YOLO 모델로 사람, 동물, 군인, 드론을 탐지합니다.
- 탐지된 대상은 Tactical Map에 점으로 표시합니다.
  - 사람/군인: 빨간 점
  - 동물/기타: 노란 점
- TP_A/B/C/D 카메라 위치는 Tactical Map에 초록 점으로 표시합니다.
- Tactical Map 배경은 overhead camera 화면을 사용합니다.
- depth 거리와 지도상 거리를 따로 볼 수 있게 했습니다.
- C2 웹은 Next.js로 실행합니다.
- FastAPI 서버가 ROS2 토픽을 받아 웹으로 보내줍니다.
- `main_side/scene`은 큰 파일이라 GitHub에 넣지 않고 따로 받게 했습니다.
- 철책 밖에서 다가오는 동물/사람/군인/드론 오브젝트를 자동 소환합니다.
- 멧돼지, 늑대, 사슴, 드론 에셋은 USDZ 리깅/애니메이션을 연결해서 움직임을 확인했습니다.
- 늑대 에셋 안에 들어있던 바닥용 helper mesh는 자동으로 숨깁니다.

## 폴더 설명

```text
cobot3/
  common/
    공통 설정 파일

  main_side/
    Isaac Sim 컴퓨터에서 실행하는 코드
    로봇, 카메라, 감시탑, 맵, ROS2 토픽 발행 담당

  sub1_side/
    C2 웹 컴퓨터에서 실행하는 코드
    웹 화면, 서버, YOLO, ROS2 토픽 수신 담당

  dev-docs/
    자세한 설명 문서

  tests/
    테스트 코드
```

## 아주 중요한 점

`main_side/scene` 폴더는 GitHub에 거의 들어있지 않습니다.

이유는 맵, USD, USDZ, texture 파일이 너무 크기 때문입니다.

그래서 팀원은 다음 두 가지를 받아야 합니다.

1. GitHub 코드
2. Google Drive의 `cobot3_scene.zip`

최종 폴더 구조는 이렇게 되어야 합니다.

```text
cobot3/
  main_side/
    camera_publisher.py
    run_camera_pub_gui.sh
    scene/
      gp_scene.usd
      assets/
      overrides/
      go2_unitree/
      go2_policy/
  sub1_side/
  common/
```

## 처음 설치하는 방법

### 1. 코드 받기

```bash
cd /home/rokey/dev_ws/isaac_sim
git clone -b new_hi https://github.com/ThatsHoon/cobot3.git cobot3
```

### 2. scene 파일 받기

Google Drive에서 `cobot3_scene.zip`을 받습니다.

그 다음 아래처럼 풉니다.

```bash
cd /home/rokey/dev_ws/isaac_sim/cobot3
unzip /path/to/cobot3_scene.zip
```

압축을 풀고 나서 아래 파일이 있어야 합니다.

```text
/home/rokey/dev_ws/isaac_sim/cobot3/main_side/scene/gp_scene.usd
```

이 파일이 없으면 Isaac Sim이 제대로 열리지 않습니다.

## ROS2 설정

우리 프로젝트는 `ROS_DOMAIN_ID=129`를 씁니다.

터미널마다 아래를 먼저 해주세요.

```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=129
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_LOCALHOST_ONLY=0
export FASTRTPS_DEFAULT_PROFILES_FILE=/home/rokey/dev_ws/isaac_sim/cobot3/main_side/fastdds_no_shm.xml
```

## Isaac Sim 쪽 실행 방법

로봇, 맵, 카메라, 감시탑을 실행합니다.

```bash
cd /home/rokey/dev_ws/isaac_sim/cobot3/main_side
bash run_camera_pub_gui.sh
```

카메라 영상을 웹으로 보내는 압축 노드도 실행합니다.

다른 터미널에서:

```bash
cd /home/rokey/dev_ws/isaac_sim/cobot3/main_side
bash run_degrade.sh
```

## C2 서버 실행 방법

웹 서버와 YOLO 서버를 켭니다.

```bash
cd /home/rokey/dev_ws/isaac_sim/cobot3/sub1_side/server
python3 -m venv --system-site-packages .venv
./.venv/bin/pip install -r requirements.txt
bash run.sh
```

YOLO 모델은 기본적으로 아래 파일을 찾습니다.

```text
/home/rokey/Downloads/dmz_4class_v14.pt
```

이 파일이 없으면 팀원에게 모델 파일도 따로 받아야 합니다.

## 웹 실행 방법

처음 한 번만 설치합니다.

```bash
cd /home/rokey/dev_ws/isaac_sim/cobot3/sub1_side/web
npm install
```

웹을 실행합니다.

```bash
cd /home/rokey/dev_ws/isaac_sim/cobot3/sub1_side/web
npm run dev -- -H 0.0.0.0
```

브라우저에서 엽니다.

```text
http://localhost:3000
```

다른 노트북에서 보려면 Isaac/C2 컴퓨터 IP를 넣습니다.

예시:

```text
http://192.168.10.70:3000
```

## 잘 켜졌는지 확인하는 법

토픽 목록 확인:

```bash
ros2 topic list
```

TP_A 카메라 영상이 있는지 확인:

```bash
ros2 topic hz /cam/tactical/tp_a/rgb
```

TP_A depth가 있는지 확인:

```bash
ros2 topic hz /cam/tactical/tp_a/depth
```

YOLO 탐지 결과 확인:

```bash
ros2 topic echo /detections_text --once --full-length
```

웹에서 직접 TP_A 영상 확인:

```text
http://localhost:3000/c2/video/mjpeg?camera=tp_a
```

## Tactical Map에서 보이는 것

- 초록 점: TP_A/B/C/D 고정 감시 카메라 위치
- 빨간 점: 사람 또는 군인
- 노란 점: 동물 또는 기타 대상
- `d` 값: 카메라 depth 값
- `g` 값: 지도 위에서의 수평 거리

예시:

```text
TP_A person d13.6 g3.2m 74%
```

뜻:

- TP_A 카메라가 사람을 봤습니다.
- depth 카메라 기준 거리는 13.6m입니다.
- 지도상 수평 거리는 3.2m입니다.
- YOLO confidence는 74%입니다.

## 접근 오브젝트 애니메이션

Isaac Sim 실행 시 `main_side/camera_publisher.py`가 `/World/Approach_Objects` 아래에
접근 오브젝트를 만듭니다.

현재 연결된 에셋:

- `boar`: `main_side/scene/assets/objects/boar_walk.usdz`
- `wolf`: `main_side/scene/assets/objects/wolf_animated.usdz`
- `deer`: `main_side/scene/assets/objects/deer_low_poly_animated.usdz`
- `drone`: `main_side/scene/assets/objects/drone.usdz`
- `person`: `main_side/scene/assets/objects/person.usdz`
- `soldier`: `main_side/scene/assets/objects/soldier.usdz`

현재 상태:

- 멧돼지는 다리 움직임이 적용되어 뛰어옵니다.
- 늑대는 달리는 애니메이션이 적용되어 뛰어옵니다.
- 사슴은 새 `deer_low_poly_animated.usdz`로 교체했고 `Take_001` 애니메이션 바인딩이 잡힙니다.
- 드론은 hover 애니메이션 바인딩이 잡히지만, 뼈/타겟 수가 많아서 반복 샘플 복사는 하지 않습니다.

멧돼지를 움직이게 만든 방법:

1. USDZ 안에서 `Skeleton`과 `SkelAnimation`을 찾습니다.
2. `_force_skel_animation_binding()`에서 mesh에 skeleton과 animation source를 강제로 연결합니다.
3. 축이 안 맞는 에셋은 `_APPROACH_ASSET_FIX_ROT_X`로 X축을 보정합니다.
4. 정면 방향이 안 맞는 에셋은 `_APPROACH_ASSET_YAW_DEG`로 Z축 yaw를 보정합니다.
5. 걷다가 멈추는 에셋은 `_repeat_skel_animation_samples()`로 애니메이션 샘플을 반복 생성합니다.
6. 너무 크거나 작으면 `_APPROACH_ASSETS`의 scale 값을 조절합니다.
7. 공중에 뜨거나 바닥을 뚫으면 `_APPROACH_ASSETS`의 마지막 값 `z_extra`를 조절합니다.

Claude Code로 이어서 작업할 때 줄 프롬프트:

```text
cobot3의 main_side/camera_publisher.py에서 접근 오브젝트 애니메이션을 정리해줘.

핵심 위치:
- _APPROACH_ASSETS: label, usd 파일명, scale, lane, x_offset, y_extra, z_extra 설정
- _APPROACH_ASSET_FIX_ROT_X: Y-up/Z-up 축 보정
- _APPROACH_ASSET_YAW_DEG: 정면 방향 yaw 보정
- _force_skel_animation_binding(): Skeleton/SkelAnimation 강제 연결
- _repeat_skel_animation_samples(): 멈추는 애니메이션을 반복 샘플로 확장
- _APPROACH_ANIM_REPEAT_LABELS: 반복 샘플 확장을 적용할 label 목록

현재 동작:
- boar, wolf는 반복 샘플 확장 대상이다.
- deer는 Take_001 애니메이션 바인딩은 잡히지만 반복 샘플 확장 대상에서는 제외했다.
- drone은 hover animation이 있지만 타겟 수가 많아 반복 샘플 확장 대상에서 제외해야 한다.

새 동물 에셋을 추가할 때:
1. USDZ 안에 Skeleton과 SkelAnimation이 있는지 로그로 확인한다.
2. skel binding 로그가 없으면 해당 파일은 다리 애니메이션으로 쓰기 어렵다.
3. 에셋이 세로로 서면 _APPROACH_ASSET_FIX_ROT_X를 조절한다.
4. 옆을 보면 _APPROACH_ASSET_YAW_DEG를 조절한다.
5. 너무 작거나 크면 _APPROACH_ASSETS의 scale을 바꾼다.
6. 반복 샘플 확장 후 Isaac Sim 클릭이 안 먹으면 해당 label을 GP_APPROACH_ANIM_REPEAT_LABELS에서 뺀다.
7. scene/assets/objects 안의 USDZ 파일은 GitHub가 아니라 scene zip으로 공유한다.
```

## 감시탑 크기 조절

기본 감시탑 scale은 `0.01`입니다.

바꾸고 싶으면 Isaac 실행 전에 설정합니다.

```bash
export GP_TACTICAL_TOWER_SCALE=0.01
export GP_TACTICAL_TOWER_ROLL_DEG=90
export GP_TACTICAL_TOWER_X_OFFSET=0
export GP_TACTICAL_TOWER_Y_OFFSET=0
export GP_TACTICAL_TOWER_Z_OFFSET=0
```

그 다음 다시 실행합니다.

```bash
cd /home/rokey/dev_ws/isaac_sim/cobot3/main_side
bash run_camera_pub_gui.sh
```

## 팀원에게 전달할 때

코드는 GitHub `new_hi` 브랜치로 공유합니다.

scene은 따로 압축해서 Google Drive로 공유합니다.

scene 압축 방법:

```bash
cd /home/rokey/dev_ws/isaac_sim/cobot3
zip -r cobot3_scene.zip main_side/scene
```

팀원에게 알려줄 말:

```text
1. GitHub에서 new_hi 브랜치를 받으세요.
2. Google Drive에서 cobot3_scene.zip을 받으세요.
3. cobot3 폴더 안에서 zip을 푸세요.
4. main_side/run_camera_pub_gui.sh를 실행하세요.
5. sub1_side/server/run.sh를 실행하세요.
6. sub1_side/web에서 npm run dev -- -H 0.0.0.0을 실행하세요.
```

## 문제가 생기면

더 자세한 문서는 여기에 있습니다.

```text
dev-docs/project_requirments.md
dev-docs/ops.md
dev-docs/main-side.md
dev-docs/sub1-side.md
```
