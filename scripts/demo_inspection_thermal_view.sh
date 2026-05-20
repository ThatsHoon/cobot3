#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

THERMAL_MODEL="${THERMAL_MODEL:-${PROJECT_ROOT}/models/dmz_person_calibration_001_best.pt}"
THERMAL_DEVICE="${THERMAL_DEVICE:-0}"
THERMAL_CONFIDENCE="${THERMAL_CONFIDENCE:-0.25}"
THERMAL_IMAGE_SIZE="${THERMAL_IMAGE_SIZE:-320}"
THERMAL_EVERY_N="${THERMAL_EVERY_N:-2}"
THERMAL_DRAW_BOXES="${THERMAL_DRAW_BOXES:-false}"

if [ ! -f "${THERMAL_MODEL}" ]; then
  echo "Missing thermal YOLO model: ${THERMAL_MODEL}" >&2
  exit 1
fi

exec "${PROJECT_ROOT}/scripts/run_inspection_thermal_view.sh" --ros-args \
  -p model:="${THERMAL_MODEL}" \
  -p device:="'${THERMAL_DEVICE}'" \
  -p confidence:="${THERMAL_CONFIDENCE}" \
  -p image_size:="${THERMAL_IMAGE_SIZE}" \
  -p every_n:="${THERMAL_EVERY_N}" \
  -p draw_boxes:="${THERMAL_DRAW_BOXES}" \
  "$@"
