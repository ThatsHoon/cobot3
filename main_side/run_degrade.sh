#!/usr/bin/env bash
# video_degrade_node 2-인스턴스 기동
# 전방: /cam/front/rgb → /c2/front/compressed
# 후방: /cam/rear/rgb  → /c2/rear/compressed
# Isaac 미기동이어도 먼저 떠서 토픽을 기다린다(무해).
set -e
cd "$(dirname "$0")"
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-130}"
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}"
export FASTRTPS_DEFAULT_PROFILES_FILE="${FASTRTPS_DEFAULT_PROFILES_FILE:-$PWD/fastdds_no_shm.xml}"
PY="/home/rokey/dev_ws/isaac_sim/cobot3/sub1_side/server/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

DEGRADE_IN=/cam/front/rgb  DEGRADE_OUT=/c2/front/compressed  "$PY" video_degrade_node.py &
DEGRADE_IN=/cam/rear/rgb   DEGRADE_OUT=/c2/rear/compressed   "$PY" video_degrade_node.py &
wait
