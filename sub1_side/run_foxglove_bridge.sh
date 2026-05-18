#!/usr/bin/env bash
# foxglove_bridge 기동 (C2-side) — 재발행/실 ROS2 토픽을 WebSocket(:8765) 노출.
# 같은-PC 임시: web_server 가 C2_INGEST_REPUBLISH=1 로 /ingest→ROS2 재발행한
# 토픽을 잡는다(동일 시스템 ROS2 py3.10 → 같은-PC DDS OK).
# 2-PC 정식: C2 PC 에서 띄우면 Isaac 실토픽을 LAN 으로 직접 잡는다.
# 설치: sudo apt install -y ros-humble-foxglove-bridge
set -e
cd "$(dirname "$0")"
source /opt/ros/humble/setup.bash
# spot_description 패키지 경로 포함 — foxglove_bridge 가 package:// URI 를 해석할 수 있도록
[ -f /home/hoon/dev_ws/cobot_ws/install/setup.bash ] && source /home/hoon/dev_ws/cobot_ws/install/setup.bash
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-130}"
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}"
# FastDDS 프로파일: web_server(run.sh)와 동일 규약 — site.sh 자동 치환본 >
# placeholder 폴백. env 로 직접 주면 그 값 최우선. (FASTDDS.md §3)
[ -f ../common/site.sh ] && source ../common/site.sh
if [ -z "${FASTRTPS_DEFAULT_PROFILES_FILE:-}" ]; then
  command -v cobot3_fastdds_profile >/dev/null 2>&1 && _P="$(cobot3_fastdds_profile web 2>/dev/null || true)"
  [ -n "${_P:-}" ] && export FASTRTPS_DEFAULT_PROFILES_FILE="$_P"
fi
exec ros2 launch foxglove_bridge foxglove_bridge_launch.xml \
  port:=8765 address:=0.0.0.0 use_compression:=false
