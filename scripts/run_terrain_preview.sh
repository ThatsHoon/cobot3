#!/usr/bin/env bash
# 지형 미리보기 — 로봇/물리/ROS 2 없음. GPU 사용량 최소화.
set -euo pipefail

ISAAC_SIM_ROOT="${ISAAC_SIM_ROOT:-/home/rokey/dev_ws/isaac_sim/isaacsim/_build/linux-x86_64/release}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MATERIAL="${PROJECT_ROOT}/assets/materials/Ground081_2K-JPG"

cd "${ISAAC_SIM_ROOT}"
exec ./python.sh "${PROJECT_ROOT}/isaacsim/terrain_preview.py" \
  --terrain-texture          "${MATERIAL}/Ground081_2K-JPG_Color.jpg" \
  --terrain-normal-texture   "${MATERIAL}/Ground081_2K-JPG_NormalGL.jpg" \
  --terrain-roughness-texture "${MATERIAL}/Ground081_2K-JPG_Roughness.jpg" \
  --terrain-texture-scale    12 \
  --no-ground-detail \
  "$@"
