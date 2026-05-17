#!/usr/bin/env bash
# standalone 카메라 퍼블리셔 기동 (MCP/GUI 비의존, CycloneDDS).
# GUI Isaac 과 동시에 띄우면 GPU 경합 → GUI Isaac 은 닫고 실행 권장.
set -e
_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── ★ 시스템 ROS 환경 스크럽 (핵심 수정) ───────────────────────────────
# 시스템 /opt/ros/humble(py3.10) 가 PYTHONPATH/AMENT/LD 에 있으면 Isaac(py3.11)
# 이 시스템 rclpy 와 충돌 → "Could not import rclpy" → bridge internal 모드
# 파손 → json parse 스팸 + ROS2 미노출. Isaac 자체 번들만 쓰도록 제거.
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
export FASTRTPS_DEFAULT_PROFILES_FILE=/home/rokey/dev_ws/isaac_sim/cobot3/fastdds_no_shm.xml
export ROS_DOMAIN_ID=130
export ROS_LOCALHOST_ONLY=0
export ROS_DISTRO=humble
_ISAAC_BR=~/dev_ws/isaac_sim/isaacsim/_build/linux-x86_64/release/exts/isaacsim.ros2.bridge/humble/lib
export LD_LIBRARY_PATH="$_ISAAC_BR${_clean_ld:+:$_clean_ld}"
# 어떤 씬을 쓸지 (기본 cobot3_1.usd; 없으면 스크립트가 최소 구성/빈 스테이지)
export GP_HEADLESS=1
# 동봉 이식 씬(스크립트 상대 — 하드코딩 제거; camera_publisher 기본과 일치)
export GP_SCENE="${GP_SCENE:-$_HERE/scene/gp_scene.usd}"
ISAAC=~/dev_ws/isaac_sim/isaacsim/_build/linux-x86_64/release
# 진단: 전체 출력을 영속 로그로 tee (터미널에도 그대로 표시).
LOG=/tmp/cobot3_isaac_headless.log
echo "[run] 전체 로그 캡처 → $LOG (live)"
"$ISAAC/python.sh" /home/rokey/dev_ws/isaac_sim/cobot3/main_side/camera_publisher.py 2>&1 | tee "$LOG"
exit "${PIPESTATUS[0]}"
