#!/usr/bin/env bash
# bake_go2_recon_map.sh — Go2 정찰 사양 (2026-05-20) AABB 로 gp_static 베이크.
#
# 사양: HOME=(212.8, 890.53), GOAL=(620.36, 499.72), arrive=±10m.
# AABB = HOME↔GOAL 사각형 + 100m 패딩.
#   xmin=112.8, xmax=720.36, ymin=399.72, ymax=990.53, res=0.5 m/px
#   ≈ 1215×1182 px ≈ 1.4MB PGM (Nav2 map_server 4MB 한계 안전)
#
# 출력: main_side/scene/maps/gp_static.{pgm,yaml}
# 사용: bash main_side/bake_go2_recon_map.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ISAAC="${ISAAC_SIM_PATH:-$HOME/dev_ws/isaac_sim/isaacsim/_build/linux-x86_64/release}"
PYTHON_SH="$ISAAC/python.sh"

if [ ! -x "$PYTHON_SH" ]; then
    echo "[bake] ⚠ Isaac python.sh 미발견: $PYTHON_SH" >&2
    exit 1
fi

cd "$HERE"
exec "$PYTHON_SH" bake_gp_static_map.py \
    --xmin 112.8 --xmax 720.36 \
    --ymin 399.72 --ymax 990.53 \
    --res 0.5 \
    --no-clamp \
    "$@"
