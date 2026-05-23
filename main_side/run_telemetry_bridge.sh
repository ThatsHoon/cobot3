#!/usr/bin/env bash
# telemetry_bridge_node 기동 — Isaac /robot/odom → /robot/gps + /robot/state
# Isaac 미기동이어도 먼저 떠서 odom 을 기다린다(무해). video_degrade 와 형제.
set -e
cd "$(dirname "$0")"
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-129}"
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}"
# cwd=main_side → $PWD 기준 FastDDS 프로파일(run_degrade.sh 와 동일 규약).
export FASTRTPS_DEFAULT_PROFILES_FILE="${FASTRTPS_DEFAULT_PROFILES_FILE:-$PWD/fastdds_no_shm.xml}"
# rclpy/std_msgs/sensor_msgs/nav_msgs 만 필요(cv2 불요) → 시스템 python3 우선,
# 없으면 C2 server venv fallback(run_degrade.sh 와 대칭).
PY="python3"
command -v "$PY" >/dev/null 2>&1 || PY="/home/rokey/dev_ws/isaac_sim/cobot3/sub1_side/server/.venv/bin/python"
exec "$PY" telemetry_bridge_node.py
