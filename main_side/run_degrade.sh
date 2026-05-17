#!/usr/bin/env bash
# video_degrade_node 기동 — Isaac /cam/realsense/rgb → /c2/video/compressed
# Isaac 미기동이어도 먼저 떠서 토픽을 기다린다(무해).
set -e
cd "$(dirname "$0")"
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-130}"
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}"
# 파일은 main_side/ 로 이동됨. 위 cd 로 cwd=main_side → $PWD 기준(하드코딩 제거).
export FASTRTPS_DEFAULT_PROFILES_FILE="${FASTRTPS_DEFAULT_PROFILES_FILE:-$PWD/fastdds_no_shm.xml}"
# cv2 가 있는 인터프리터: C2 server venv 재사용(없으면 시스템 python3)
PY="/home/rokey/dev_ws/isaac_sim/cobot3/sub1_side/server/.venv/bin/python"
[ -x "$PY" ] || PY="python3"
exec "$PY" video_degrade_node.py
