#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPLICATOR_DIR="${PROJECT_ROOT}/datasets/deer_replicator"
YOLO_DIR="${PROJECT_ROOT}/datasets/deer_yolo"
MODEL_OUT="${PROJECT_ROOT}/models/deer_detector_best.pt"

# Step 1: Replicator 출력 → YOLO 포맷 변환
echo "=== Step 1: Replicator → YOLO 포맷 변환 ==="
python3 "${PROJECT_ROOT}/scripts/convert_replicator_to_yolo.py" \
  "${REPLICATOR_DIR}" \
  "${YOLO_DIR}" \
  --class-name animal \
  --val-ratio 0.2 \
  --no-group-intruders

# Step 2: YOLOv8 학습
echo "=== Step 2: YOLOv8 학습 시작 ==="
python3 "${PROJECT_ROOT}/scripts/train_deer_yolo.py" \
  --data "${YOLO_DIR}/data.yaml" \
  --output "${MODEL_OUT}"

echo "=== 완료: ${MODEL_OUT} ==="
