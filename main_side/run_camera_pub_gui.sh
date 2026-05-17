#!/usr/bin/env bash
# 카메라 퍼블리셔 — GUI 표시판(사용자가 Isaac 창에서 직접 봄).
# 사용자 세션에서 직접 실행해야 함(GUI=DISPLAY 필요): 프롬프트에 `! 이 경로`
# headless 와 동일하게 OG 자동 생성·Play·publish 하므로 별도 조작 불필요.
#
# ⚠ MCP 비양립: 이건 standalone python.sh(mcp 확장 미적재). 동시에
#   isaac-sim MCP 서버가 떠 있으면 relay 가 빈 8766 소켓을 두드려 Isaac
#   콘솔에 `json parse … 's'` + `getRenderSettings … stage-id` 가 무한
#   폭주(무해하나 시끄러움). 근본조치: MCP 서버 비활성
#     claude mcp remove "isaac-sim" -s user      # 되돌리기:
#     claude mcp add isaac-sim -s user -- \
#       /home/rokey/dev_ws/isaac-sim-mcp/.venv/bin/python \
#       /home/rokey/dev_ws/isaac-sim-mcp/isaac_mcp/server.py
set -e
_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── ★ 시스템 ROS 환경 스크럽 (핵심 수정) ───────────────────────────────
# `!` 실행 시 셸의 ~/.bashrc 가 /opt/ros/humble(py3.10) 를 소싱 → Isaac(py3.11)
# 이 시스템 rclpy 를 만나 "Could not import rclpy" → bridge internal 모드 파손
# → json parse 스팸 + ROS2 미노출. Isaac 은 자체 번들 ROS2 만 써야 하므로
# 시스템 ROS 가 넣은 PYTHONPATH/AMENT/LD 항목을 제거한다.
unset AMENT_PREFIX_PATH AMENT_CURRENT_PREFIX COLCON_PREFIX_PATH
unset ROS_VERSION ROS_PYTHON_VERSION PYTHONPATH
# LD_LIBRARY_PATH 에서 ros/IsaacSim-ros_workspaces 토큰 제거
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
# Isaac 번들 humble/cyclone lib 를 LD_LIBRARY_PATH 선두에 (스크럽된 경로 위)
_ISAAC_BR=~/dev_ws/isaac_sim/isaacsim/_build/linux-x86_64/release/exts/isaacsim.ros2.bridge/humble/lib
export LD_LIBRARY_PATH="$_ISAAC_BR${_clean_ld:+:$_clean_ld}"
export GP_HEADLESS=0          # ← GUI 창 표시
# 동봉 이식 씬(스크립트 상대 — 하드코딩 제거; camera_publisher 기본과 일치)
export GP_SCENE="${GP_SCENE:-$_HERE/scene/gp_scene.usd}"
ISAAC=~/dev_ws/isaac_sim/isaacsim/_build/linux-x86_64/release
exec "$ISAAC/python.sh" /home/rokey/dev_ws/isaac_sim/cobot3/main_side/camera_publisher.py
