# cobot3 YOLO 모델 학습 정보

DMZ 경계근무 특화 4-class 탐지 모델.
Isaac Sim Replicator 합성 데이터 + 실사 데이터 혼합 학습.

---

## 클래스 정의

| ID | 라벨 | 설명 | alert 그룹 |
|---|---|---|---|
| 0 | person | 민간인 / 비전투원 | intruder |
| 1 | soldier | 무장 군인 / 전투원 | intruder |
| 2 | drone | 무인기 | intruder |
| 3 | animal | 동물 (anymal) — wolf/boar/deer 등 | animal |

> `sub1_side/server/config.py`의 `YOLO_CLASSES` ID 순서와 반드시 일치해야 함.
> 표준 정의: `common/yolo/data.yaml`

---

## 모델 버전 이력

| 파일명 | 베이스 모델 | 학습 데이터셋 | 비고 |
|---|---|---|---|
| `cobot3_4class_best.pt` | yolov8s | merged_yolo (v1) | 초기 통합 모델 |
| `cobot3_4class_v2_best.pt` | yolov8n | merged_v2 | 경량화 버전 |
| `cobot3_4class_v3_best.pt` | yolov8s | merged_yolo (v1) | v1 재학습 (graphs_v3) |
| `cobot3_4class_v4_best.pt` | — | — | 최신 버전 |

> 모델 가중치 파일(`.pt`)은 용량이 크므로 git 미추적.
> `sub1_side/server/models/` 에 복사 시 자동 픽업.

---

## 데이터셋 구성

| 데이터셋 | 학습 클래스 포커스 | 비고 |
|---|---|---|
| `person_yolo` | person(0) | 단일 클래스 포커스, 4-class 레이블 |
| `soldier_yolo` | soldier(1) | 단일 클래스 포커스, 4-class 레이블 |
| `drone_yolo` | drone(2) | 단일 클래스 포커스, 4-class 레이블 |
| `boar_yolo` | animal(3) | 멧돼지 Isaac Sim Replicator 합성 |
| `wolf_yolo` | animal(3) | 늑대 Isaac Sim Replicator 합성 |
| `merged_yolo` | 전체 4-class | v1 통합 데이터셋 |
| `merged_v2` | 전체 4-class | v2 통합 데이터셋 (dataset_v2/multi_yolo 기반) |

데이터셋 원본 경로 (학습자 로컬): `/home/jeon/dev_ws/src/cobot3/datasets/`

---

## 주요 학습 설정 (args.yaml 요약)

| 파라미터 | yolov8s_4class | yolov8s_4class_v2 |
|---|---|---|
| 베이스 모델 | yolov8s.pt | yolov8n.pt |
| 데이터셋 | merged_yolo | merged_v2 |
| epochs | 150 | 150 |
| patience | 30 | 30 |
| batch | 8 | 8 |
| imgsz | 640 | 640 |
| optimizer | auto | auto |
| augment: flipud | 0.3 | 0.3 |
| augment: fliplr | 0.5 | 0.5 |
| augment: degrees | 10.0 | 10.0 |
| augment: mixup | 0.1 | 0.1 |
| lr0 | 0.01 | 0.01 |
| weight_decay | 0.0005 | 0.0005 |

---

## 최종 성능 지표 (epoch 150 기준)

| 실험명 | Precision | Recall | mAP@50 | mAP@50-95 |
|---|---|---|---|---|
| graphs_v3 | 0.946 | 0.920 | **0.963** | 0.782 |
| yolov8s_4class | 0.992 | 0.961 | **0.983** | **0.920** |
| yolov8s_4class_v2 | 0.950 | 0.901 | 0.956 | 0.750 |

> `yolov8s_4class` (cobot3_4class_best.pt) 가 mAP 기준 최고 성능.

---

## 학습 파이프라인

```bash
# Isaac Sim Replicator 합성 데이터 → YOLO 포맷 변환
python main_side/scripts/yolo_train/convert_replicator_to_yolo.py

# 학습 (args.yaml 참고)
yolo detect train \
  data=common/yolo/data.yaml \
  model=yolov8s.pt \
  epochs=150 batch=8 imgsz=640 \
  project=models name=cobot3_4class
```

학습 완료 후 `weights/best.pt` → `sub1_side/server/models/` 에 복사.
