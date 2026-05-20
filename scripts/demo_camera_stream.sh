#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

set +u
source /opt/ros/humble/setup.bash
if [ -f "${PROJECT_ROOT}/ros2_ws/install/setup.bash" ]; then
  source "${PROJECT_ROOT}/ros2_ws/install/setup.bash"
fi
set -u

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-121}"

echo "카메라 압축 스트림 시작"
echo "  /camera/image_raw           → /camera/image_raw/compressed"
echo "  /inspection_camera/image_raw → /inspection_camera/image_raw/compressed"

ros2 run image_transport republish raw compressed \
  --ros-args \
  -r in:=/camera/image_raw \
  -r out/compressed:=/camera/image_raw/compressed &

exec ros2 run image_transport republish raw compressed \
  --ros-args \
  -r in:=/inspection_camera/image_raw \
  -r out/compressed:=/inspection_camera/image_raw/compressed
