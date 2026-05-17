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
# D-확장 업링크 대상. 같은-PC=localhost / 2-PC=C2 PC IP (env 로 지정).
export C2_INGEST_URL="${C2_INGEST_URL:-http://localhost:8000}"
ISAAC=~/dev_ws/isaac_sim/isaacsim/_build/linux-x86_64/release
# 전체 raw 출력은 $LOG 에 전량 보존(tee). 콘솔에서는 알려진-양성 2종
# (omni.usd-abi getRenderSettings stage-id + 짝지은 json 's')만 필터.
# 증거상 씬/MCP/애너테이터 무관·기능 무영향 확정 — 가림 아님(raw 전량).
LOG=/tmp/cobot3_isaac_headless.log
echo "[run] raw 로그(전량) → $LOG | 콘솔은 알려진-양성 2종 필터"
"$ISAAC/python.sh" /home/rokey/dev_ws/isaac_sim/cobot3/main_side/camera_publisher.py 2>&1 \
  | tee "$LOG" \
  | grep --line-buffered -vF \
      -e 'getRenderSettings failed getting a stage-id' \
      -e "last read: 's'"
exit "${PIPESTATUS[0]}"
