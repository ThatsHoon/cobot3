# YOLO 모델 슬롯

cobot3 의 `sub1_side/server/yolo_infer.py` 가 사용할 모델 가중치 폴더.
가중치 파일(`.pt`)은 용량이 크므로 git 미추적 — 별도 공유 후 이 폴더에 복사.

---

## 모델 선택 우선순위 (`config._pick_model()`)

1. `C2_YOLO_MODEL` 환경변수 명시 경로
2. 본 디렉토리(`sub1_side/server/models/`) 안 첫 번째 `*.pt`
3. `_DEFAULT_MODEL` = `cobot3_4class_v3_best_small.pt` (config.py 기본값)
4. `yolov8n.pt` (ultralytics 첫 추론 시 자동 다운로드)

---

## 현재 운용 모델

| 파일명 | 베이스 | 데이터셋 | mAP@50 | mAP@50-95 |
|---|---|---|---|---|
| `cobot3_4class_v3_best_small.pt` | yolov8s | merged_yolo | 0.963 | 0.782 |

> 전체 버전 이력 및 학습 정보: `dev-docs/yolo-model.md`

---

## 클래스 매핑

`config.YOLO_CLASSES` 와 모델 학습 클래스 ID 가 반드시 일치해야 함.
표준 정의 파일: `common/yolo/data.yaml`

| ID | 라벨 | 그룹 | alert 정책 |
|---|---|---|---|
| 0 | person | intruder | `intruder_detected` → 정밀조준 사격 |
| 1 | soldier | intruder | `intruder_detected` → 정밀조준 사격 |
| 2 | drone | intruder | `intruder_detected` → 정밀조준 사격 |
| 3 | animal (anymal) | animal | `animal_detected` → 모니터링만 (사격 없음) |

---

## alert / 자동사격 기준

| 그룹 | conf 임계값 | stable tracker | 자동사격 쿨다운 |
|---|---|---|---|
| intruder (person/soldier) | ≥ 0.7 | 5초 window / 3프레임 | 30초 |
| intruder (drone) | ≥ 0.7 | 3초 window / 2프레임 | 30초 |
| animal | ≥ 0.5 | — (사격 없음) | — |

---

## 모델 교체 절차

```bash
# 1. 가중치 파일 복사
cp <경로>/best.pt /home/rokey/dev_ws/isaac_sim/cobot3/sub1_side/server/models/

# 2. uvicorn 재시작 (자동 픽업)
pkill -f "uvicorn app:app"
( cd sub1_side/server && bash run.sh & )
```

특정 파일을 강제 지정하려면:
```bash
export C2_YOLO_MODEL=/home/rokey/dev_ws/isaac_sim/cobot3/sub1_side/server/models/cobot3_4class_best.pt
```

---

## 학습 파이프라인

`main_side/scripts/yolo_train/` 참조.
상세 문서: `dev-docs/yolo-model.md`
