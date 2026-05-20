#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

YOLO_MODEL="${YOLO_MODEL:-${PROJECT_ROOT}/models/dmz_sentry_best.pt}"
YOLO_DEVICE="${YOLO_DEVICE:-0}"
YOLO_CONFIDENCE="${YOLO_CONFIDENCE:-0.50}"
YOLO_IMAGE_SIZE="${YOLO_IMAGE_SIZE:-320}"
YOLO_PUBLISH_ANNOTATED="${YOLO_PUBLISH_ANNOTATED:-true}"
YOLO_ANNOTATED_SCALE="${YOLO_ANNOTATED_SCALE:-0.5}"
YOLO_EVERY_N="${YOLO_EVERY_N:-1}"

if [ ! -f "${YOLO_MODEL}" ]; then
  echo "Missing deer YOLO model: ${YOLO_MODEL}" >&2
  exit 1
fi

exec "${PROJECT_ROOT}/scripts/run_yolo_person_detector.sh" --ros-args \
  -p model:="${YOLO_MODEL}" \
  -p device:="'${YOLO_DEVICE}'" \
  -p confidence:="${YOLO_CONFIDENCE}" \
  -p image_size:="${YOLO_IMAGE_SIZE}" \
  -p publish_annotated:="${YOLO_PUBLISH_ANNOTATED}" \
  -p annotated_scale:="${YOLO_ANNOTATED_SCALE}" \
  -p every_n:="${YOLO_EVERY_N}" \
  -p alerts_topic:="/deer_alerts" \
  -p detections_topic:="/deer_detections" \
  -p alert_label:="deer" \
  -p alert_event:="deer_detected" \
  -p detect_classes:="[1]" \
  -p alert_confidence:="0.50" \
  "$@"
