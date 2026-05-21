#!/usr/bin/env bash
# fire_turret ROS2 서비스 서버 실행 (Isaac Sim Python 환경)
# 사용: ./run_fire_turret.sh
# weapon/fire 서비스를 수신해 Go2_turret에서 구체 총알 스폰
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source /opt/ros/humble/setup.bash
source "$SCRIPT_DIR/../common/site.env" 2>/dev/null || true

~/dev_ws/isaac_sim/isaacsim/python.sh "$SCRIPT_DIR/fire_turret.py"
