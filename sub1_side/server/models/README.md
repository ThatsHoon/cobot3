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

| ID | 라벨 | 종류 |
|---|---|---|
| 0 | person | 사람 |
| 1 | animal | 동물 (jsy 학습 모델 호환) |
| 16~25 | bird/cat/dog/horse/sheep/cow/elephant/bear/zebra/giraffe | COCO 동물 |

## jsy 학습 모델

`cobot3_for_extracting_dtModel_web_component/models/dmz_person_calibration_001_best.pt`
(2-class person+animal). 본 폴더에 복사 시 자동 사용.

학습 파이프라인: `main_side/scripts/yolo_train/` 참조.
