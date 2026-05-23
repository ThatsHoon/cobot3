#!/usr/bin/env bash
# 최소 양방향 ROS2 브리지 검증 러너. run_camera_pub.sh 와 동일한 env 규약
# (시스템 ROS scrub + Isaac internal humble libfastrtps 2.6.x ← 시스템
# 2.6.11 과 와이어호환). rclpy 미사용 → py3.11/3.10 ABI 충돌 무관.
set -e
_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

unset AMENT_PREFIX_PATH AMENT_CURRENT_PREFIX COLCON_PREFIX_PATH
unset ROS_VERSION ROS_PYTHON_VERSION PYTHONPATH
_clean_ld=""
IFS=':' read -ra _parts <<< "${LD_LIBRARY_PATH}"
for _p in "${_parts[@]}"; do
  case "$_p" in
    */opt/ros/*|*IsaacSim-ros_workspaces*|"") ;;
    *) _clean_ld="${_clean_ld:+$_clean_ld:}$_p" ;;
  esac
done

export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE="${FASTRTPS_DEFAULT_PROFILES_FILE:-$_HERE/fastdds_no_shm.xml}"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-129}"
export ROS_LOCALHOST_ONLY=0
export ROS_DISTRO=humble
_ISAAC_BR=~/dev_ws/isaac_sim/isaacsim/_build/linux-x86_64/release/exts/isaacsim.ros2.bridge/humble/lib
export LD_LIBRARY_PATH="$_ISAAC_BR${_clean_ld:+:$_clean_ld}"

ISAAC=~/dev_ws/isaac_sim/isaacsim/_build/linux-x86_64/release
LOG=/tmp/cobot3_test_bridge.log
echo "[run] raw → $LOG | domain=$ROS_DOMAIN_ID profile=$FASTRTPS_DEFAULT_PROFILES_FILE"
"$ISAAC/python.sh" "$_HERE/test_ros2_bridge.py" 2>&1 \
  | tee "$LOG" \
  | grep --line-buffered -vF \
      -e 'getRenderSettings failed getting a stage-id' \
      -e "last read: 's'"
exit "${PIPESTATUS[0]}"
