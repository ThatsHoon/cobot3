#!/bin/bash
# Nav2 launch wrapper — cobot3 ROS 환경 + FastDDS 설정 일관.

set -eo pipefail   # -u 는 ROS humble setup.bash 에 AMENT_TRACE_SETUP_FILES unbound 충돌
_HERE="$(cd "$(dirname "$0")" && pwd)"
_COBOT3_ROOT="$(cd "$_HERE/../.." && pwd)"

source /opt/ros/humble/setup.bash

export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
# 2026-05-21: ~/.config/cobot3/fastdds_web.xml (placeholder 치환된 sed 결과)
# 우선 사용 — repo template 은 __MAIN_PC_IP__ / __C2_LAN_IP__ 미치환 raw
# 라 builtin discovery 가 placeholder 파싱 실패 → nav2 노드 자기들끼리도
# 다른 fastdds context 로 분리 → navigate_to_pose action 미준비 원인.
# 다른 사이드카들은 cobot3_fastdds_profile / site.sh 통해 ~/.config 사용 중.
if [ -f "$HOME/.config/cobot3/fastdds_web.xml" ]; then
    export FASTRTPS_DEFAULT_PROFILES_FILE="$HOME/.config/cobot3/fastdds_web.xml"
else
    export FASTRTPS_DEFAULT_PROFILES_FILE="$_COBOT3_ROOT/sub1_side/fastdds_web.xml"
fi
export ROS_DOMAIN_ID=130
export ROS_LOCALHOST_ONLY=0
echo "[nav2] FASTRTPS_DEFAULT_PROFILES_FILE=$FASTRTPS_DEFAULT_PROFILES_FILE"

exec ros2 launch "$_HERE/nav2_bringup.launch.py" "$@"
