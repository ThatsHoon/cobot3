# YOLO 동물 감지 학습 파이프라인 (jsy 브랜치 포팅)

cobot3 의 YOLO 동물 감지(`sub1_side/server/yolo_infer.py`)를 위한 fine-tuning 도구.

## 흐름

1. **Replicator 데이터 생성** (Isaac Sim): synthetic RGB + 2D bbox + class labels
2. **YOLO 포맷 변환** (`convert_replicator_to_yolo.py`): Replicator → YOLO 표준 디렉토리
3. **2-class 학습** (`train_2class_yolo.sh`): person(0) + animal(1) ultralytics 학습
4. **모델 배포**: 산출물 `.pt` 를 `sub1_side/server/models/` 에 두면 cobot3 가 자동 사용

## 1. Replicator → YOLO 변환

```bash
${ISAAC_PYTHON} convert_replicator_to_yolo.py \
    --source-dir <Replicator 출력 디렉토리> \
    --output-dir <YOLO 데이터셋 디렉토리> \
    --classes "person,animal" \
    --val-ratio 0.20 \
    --min-area 80
```

여러 Replicator 출력을 병합하려면 `--extra-source-dirs dir1 dir2 ...`.

## 2. 2-class 학습

```bash
# 환경변수
export DATA=<YOLO 데이터셋>/data.yaml
export EPOCHS=50
export IMGSZ=640
export DEVICE=0

bash train_2class_yolo.sh
```

산출물: `runs/detect/train*/weights/best.pt`.

## 3. cobot3 통합

```bash
mkdir -p /home/rokey/dev_ws/isaac_sim/cobot3/sub1_side/server/models
cp runs/detect/train*/weights/best.pt \
    /home/rokey/dev_ws/isaac_sim/cobot3/sub1_side/server/models/dmz_animal_v1.pt
```

`sub1_side/server/config.py` 의 `_pick_model()` 가 `models/*.pt` 를 자동 픽업.
`C2_YOLO_MODEL` 환경변수로 명시 경로 우선 지정도 가능.

학습 모델의 클래스 매핑은 `config.YOLO_CLASSES` 와 일치해야 함 (현재
person→class 0, animal→class 1).
