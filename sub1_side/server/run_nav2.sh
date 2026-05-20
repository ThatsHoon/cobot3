#!/bin/bash
# Nav2 launch wrapper — cobot3 ROS 환경 + FastDDS 설정 일관.

set -eo pipefail   # -u 는 ROS humble setup.bash 에 AMENT_TRACE_SETUP_FILES unbound 충돌
_HERE="$(cd "$(dirname "$0")" && pwd)"
_COBOT3_ROOT="$(cd "$_HERE/../.." && pwd)"

source /opt/ros/humble/setup.bash

export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE="$_COBOT3_ROOT/sub1_side/fastdds_web.xml"
export ROS_DOMAIN_ID=130
export ROS_LOCALHOST_ONLY=0

exec ros2 launch "$_HERE/nav2_bringup.launch.py" "$@"
