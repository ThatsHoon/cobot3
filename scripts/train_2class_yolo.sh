#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

REPLICATOR_DIR="${PROJECT_ROOT}/datasets/deer_replicator"
EXTRA_DIR="${PROJECT_ROOT}/datasets/deer_replicator_extra"
YOLO_DIR="${PROJECT_ROOT}/datasets/dmz_2class_yolo"
MODEL_OUT="${PROJECT_ROOT}/models/dmz_sentry_best.pt"

if [ ! -d "${REPLICATOR_DIR}" ]; then
  echo "기본 데이터셋이 없습니다: ${REPLICATOR_DIR}" >&2
  exit 1
fi

EXTRA_ARGS=()
if [ -d "${EXTRA_DIR}" ]; then
  echo "추가 데이터셋 발견: ${EXTRA_DIR}"
  EXTRA_ARGS=(--extra-source-dirs "${EXTRA_DIR}")
else
  echo "추가 데이터셋 없음, 기본 데이터셋만 사용합니다."
fi

echo "=== Step 1: Replicator → YOLO 2-class 포맷 변환 (person=0, animal=1) ==="
python3 "${PROJECT_ROOT}/scripts/convert_replicator_to_yolo.py" \
  "${REPLICATOR_DIR}" \
  "${YOLO_DIR}" \
  "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}" \
  --classes "person,animal" \
  --val-ratio 0.2 \
  --no-group-intruders

echo ""
echo "=== Step 2: YOLOv8n 2-class 학습 (150 epochs) ==="
python3 "${PROJECT_ROOT}/scripts/train_deer_yolo.py" \
  --data "${YOLO_DIR}/data.yaml" \
  --output "${MODEL_OUT}" \
  --epochs 150 \
  --base-model yolov8n.pt

echo ""
echo "=== 완료 ==="
echo "모델: ${MODEL_OUT}"
