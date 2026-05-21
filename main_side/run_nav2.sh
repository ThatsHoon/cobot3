#!/bin/bash
# Nav2 launch wrapper — cobot3 Main 측 (Isaac PC) 에서 실행.
# 2026-05-21: sub1_side → main_side 이동. 로봇 측 onboard Nav2 패턴
# (실 Go2 배포 시에도 같은 구조). FastDDS 는 main 측 fastdds_no_shm.xml
# (UDP only, SHM 비활성 — Isaac OG ROS2 bridge 호환).

set -eo pipefail
_HERE="$(cd "$(dirname "$0")" && pwd)"

source /opt/ros/humble/setup.bash

export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE="$_HERE/fastdds_no_shm.xml"
export ROS_DOMAIN_ID=130
export ROS_LOCALHOST_ONLY=0
echo "[nav2] FASTRTPS_DEFAULT_PROFILES_FILE=$FASTRTPS_DEFAULT_PROFILES_FILE"

exec ros2 launch "$_HERE/nav2_bringup.launch.py" "$@"
