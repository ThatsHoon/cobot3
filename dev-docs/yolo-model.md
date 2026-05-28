# YOLO 탐지 모델 — 학습·추론·자동사격 파이프라인

DMZ 경계근무 특화 4-class YOLOv8 탐지 모델.
Isaac Sim Replicator 합성 데이터 + 실사 데이터로 학습.

---

## 1. 클래스 정의

표준 정의 파일: `common/yolo/data.yaml`

| ID | 라벨 | 설명 | alert 그룹 |
|---|---|---|---|
| 0 | person | 민간인 / 비전투원 | intruder |
| 1 | soldier | 무장 군인 / 전투원 | intruder |
| 2 | drone | 무인기 | intruder |
| 3 | animal | 동물 (anymal) — wolf/boar/deer 등 | animal |

> `sub1_side/server/config.py`의 `YOLO_CLASSES` 와 ID 순서 반드시 일치.

---

## 2. 모델 버전 이력

| 파일명 | 베이스 | 데이터셋 | mAP@50 | mAP@50-95 | 비고 |
|---|---|---|---|---|---|
| `cobot3_4class_best.pt` | yolov8s | merged_yolo | 0.983 | 0.920 | v1 — 최고 성능 |
| `cobot3_4class_v2_best.pt` | yolov8n | merged_v2 | 0.956 | 0.750 | v2 — 경량화 |
| `cobot3_4class_v3_best.pt` | yolov8s | merged_yolo | 0.963 | 0.782 | v3 — 재학습 |
| `cobot3_4class_v4_best.pt` | — | — | — | — | v4 최신 |
| `cobot3_4class_v3_best_small.pt` | yolov8s | merged_yolo | — | — | 현재 운용 기본값 |

> 가중치 파일(`.pt`)은 용량이 크므로 git 미추적. `sub1_side/server/models/` 에 복사하면 자동 픽업.

**현재 기본값:** `config.py`의 `_DEFAULT_MODEL = "cobot3_4class_v3_best_small.pt"`

### 모델 선택 우선순위 (`config._pick_model()`)
1. `C2_YOLO_MODEL` 환경변수 명시 경로
2. `sub1_side/server/models/` 내 첫 번째 `*.pt`
3. `_DEFAULT_MODEL` (`cobot3_4class_v3_best_small.pt`)
4. `yolov8n.pt` (ultralytics 자동 다운로드)

---

## 3. 데이터셋 구성

| 데이터셋 | 포커스 클래스 | 비고 |
|---|---|---|
| `person_yolo` | person(0) | 실사 데이터 위주 |
| `soldier_yolo` | soldier(1) | 실사 데이터 위주 |
| `drone_yolo` | drone(2) | 실사 데이터 위주 |
| `boar_yolo` | animal(3) | Isaac Sim Replicator 합성 |
| `wolf_yolo` | animal(3) | Isaac Sim Replicator 합성 |
| `merged_yolo` | 전체 4-class | v1 통합 데이터셋 |
| `merged_v2` | 전체 4-class | v2 통합 (dataset_v2/multi_yolo 기반) |

dataset_v2 수집 카메라: TP_A / TP_B / TP_C / TP_D 전술 고정 카메라 4개

데이터 변환 스크립트: `main_side/scripts/yolo_train/convert_replicator_to_yolo.py`

---

## 4. 주요 학습 설정

| 파라미터 | 값 |
|---|---|
| epochs | 150 |
| patience (early stop) | 30 |
| batch | 8 |
| imgsz | 640 |
| optimizer | auto |
| lr0 / lrf | 0.01 / 0.01 |
| weight_decay | 0.0005 |
| flipud / fliplr | 0.3 / 0.5 |
| degrees (회전 augment) | 10.0° |
| mixup | 0.1 |
| close_mosaic | 10 |

상세 설정: `common/yolo/README.md` 또는 각 실험의 `args.yaml` 참조.

---

## 5. C2 서버 추론 파이프라인

```
inspect 카메라 프레임 (5fps, 640×360 JPEG)
  ↓  ros_bridge._on_video("inspect")
  ↓  ThreadPoolExecutor(max_workers=1) — 비동기, 이전 추론 중이면 프레임 드롭
  ↓  YoloInfer.infer_with_alerts(bgr)
       ├─ infer()            → YOLO 추론 (conf ≥ YOLO_ALERT_CONF=0.7)
       ├─ _update_stable()   → stable tracker (window/frame 조건 충족 시 auto-fire cb)
       ├─ person_alert       → intruder_detected 이벤트 (cooldown 3s)
       └─ animal_alert       → animal_detected 이벤트 (cooldown 5s)
```

**추론 채널:** 기본 `inspect` 단독. `C2_YOLO_CAMERAS=inspect,tp_a,tp_b,tp_c,tp_d` 로 확장 가능.

**C2_YOLO_LOCAL=0 모드:** 모델 미로드 — stable tracker만 동작. `main_side/yolo_node.py`가 추론을 담당하고 결과를 ROS 토픽으로 전달할 때 사용.

---

## 6. Alert / 자동사격 정책

### intruder 그룹 (person / soldier / drone)

| 단계 | 조건 | 동작 |
|---|---|---|
| 1차 alert | conf ≥ 0.7, cooldown 3s | `/events` WS에 `intruder_detected` 방송 |
| 자동사격 | stable tracker 충족 + 쿨다운 해제 | `look_at_pixel` 정밀조준 → `call_fire()` ROS 서비스 |

**Stable tracker 기준:**

| 라벨 | window | 최소 프레임 |
|---|---|---|
| soldier / person | 5초 | 3프레임 |
| drone | 3초 | 2프레임 |

> WHY: 단발 오탐 방지 — window 시간 내 충분한 프레임이 감지될 때만 트리거.

**자동사격 쿨다운:** 30초 (`GP_AUTO_FIRE_COOLDOWN_S` 환경변수로 조정)

### animal 그룹 (animal / anymal)

| 조건 | 동작 |
|---|---|
| conf ≥ 0.5, cooldown 5s | `/events` WS에 `animal_detected` 방송 (모니터링 전용, 사격 없음) |

---

## 7. 관련 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `C2_YOLO_LOCAL` | `1` | `0`이면 모델 미로드, stable tracker만 동작 |
| `C2_YOLO_MODEL` | — | 모델 절대 경로 (지정 시 최우선) |
| `C2_YOLO_CAMERAS` | `inspect` | 추론할 카메라 채널 (콤마 구분) |
| `C2_YOLO_ALERT_CONF` | `0.7` | intruder alert 최소 confidence |
| `C2_YOLO_ALERT_COOLDOWN` | `3.0` | intruder alert 쿨다운(초) |
| `C2_YOLO_ANIMAL_ALERT_CONF` | `0.5` | animal alert 최소 confidence |
| `C2_YOLO_ANIMAL_ALERT_COOLDOWN` | `5.0` | animal alert 쿨다운(초) |
| `GP_AUTO_FIRE_COOLDOWN_S` | `30.0` | 자동사격 후 재발화 금지 시간(초) |

---

## 8. 관련 파일

| 파일 | 역할 |
|---|---|
| `common/yolo/data.yaml` | 표준 클래스 정의 (학습·추론 공통) |
| `common/yolo/README.md` | 모델 버전·데이터셋·성능 요약 |
| `sub1_side/server/yolo_infer.py` | YoloInfer 클래스 — 추론·stable tracker·alert |
| `sub1_side/server/config.py` | YOLO_CLASSES, 환경변수 기본값, 모델 픽업 로직 |
| `sub1_side/server/models/` | 가중치 파일 위치 (`.pt`, git 미추적) |
| `sub1_side/server/models/README.md` | 모델 교체 절차·클래스 매핑 |
| `main_side/yolo_node.py` | Main PC 측 YOLO 추론 노드 (C2_YOLO_LOCAL=0 시 사용) |
| `main_side/scripts/yolo_train/` | 학습 파이프라인 스크립트 |
