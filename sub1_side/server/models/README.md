# YOLO 모델 슬롯

cobot3 의 `sub1_side/server/yolo_infer.py` 가 사용할 모델 가중치 폴더.

## 우선순위 (config._pick_model())

1. `C2_YOLO_MODEL` 환경변수 명시 경로
2. 본 디렉토리(`sub1_side/server/models/`) 안 첫 번째 `*.pt`
3. `yolov8n.pt` 기본 (ultralytics 가 처음 추론 시 자동 다운로드)

## 모델 교체

```bash
cp <학습 산출물>/best.pt /home/rokey/dev_ws/isaac_sim/cobot3/sub1_side/server/models/
# 자동 픽업 — uvicorn 재시작 필요
pkill -f "uvicorn app:app"
( cd sub1_side/server && bash run.sh & )
```

## 클래스 매핑

`config.YOLO_CLASSES` 와 모델 학습 시 클래스 ID 가 일치해야 함.

| ID | 라벨 | 그룹 | alert 정책 |
|---|---|---|---|
| 0 | person | intruder | intruder_detected → 정밀사격 |
| 1 | soldier | intruder | intruder_detected → 정밀사격 |
| 2 | drone | intruder | intruder_detected → 정밀사격 |
| 3 | anymal | animal | animal_detected → 모니터링 |

> DMZ 경계근무 특화 4-class 모델. COCO80 범용 모델 대비 정확도 향상.
> `config.py`의 `YOLO_CLASSES` ID 순서와 모델 학습 클래스 순서가 반드시 일치해야 함.

## alert 분류 로직 (`yolo_infer.py`)

- **intruder 그룹** (`person`, `soldier`, `drone`): conf ≥ `YOLO_ALERT_CONF`(0.7), 5초/3프레임 stable tracker 충족 시 자동사격 트리거
- **animal 그룹** (`anymal`): conf ≥ `YOLO_ANIMAL_ALERT_CONF`(0.5), 모니터링 이벤트만 발생 (사격 없음)

## 학습 파이프라인

`main_side/scripts/yolo_train/` 참조.
