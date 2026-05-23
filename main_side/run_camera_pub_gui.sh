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
# 사이트 IP 단일소스(SSOT): common/site.env → FastDDS 자동 파생
[ -f "$_HERE/../common/site.sh" ] && source "$_HERE/../common/site.sh"

# ── ★ 시스템 ROS2 Humble 소싱 (no-scrub — 정공 핵심 수정) ──────────────
# camera_publisher.py 는 rclpy 를 import 하지 않음(순수 OG C++ 브리지) →
# 과거 scrub 의 전제(Isaac py3.11 ↔ 시스템 py3.10 rclpy 충돌)가 이
# 프로세스엔 적용되지 않는다. scrub 는 오히려 Isaac C++ 브리지가 시스템
# fastrtps 2.6.11(= C2 와 동일·와이어 호환) 대신 internal/엉뚱한 libs 를
# 쓰게 만든 자해였음(이전 "정공 불가" 오진의 핵심). no-scrub 로 시스템
# 2.6.11 로드 → 시스템 ROS2 와 양방향 정공. (검증: odom 63Hz, cmd_vel
# 다운링크 RX, FASTDDS.md §6.) `!` 실행 시 ~/.bashrc 가 humble 을 이미
# 소싱하지만, 명시 소싱으로 비대화형 경로에서도 보장한다.
source /opt/ros/humble/setup.bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
# FastDDS 프로파일: env 지정 > site.env 로 자동 치환본(2-PC) > 기본 UDP-only.
if [ -z "${FASTRTPS_DEFAULT_PROFILES_FILE:-}" ]; then
  export FASTRTPS_DEFAULT_PROFILES_FILE="$_HERE/fastdds_no_shm.xml"
fi
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-129}"
export ROS_LOCALHOST_ONLY=0
export ROS_DISTRO=humble
export GP_HEADLESS=0          # ← GUI 창 표시
# 동봉 이식 씬(스크립트 상대 — 하드코딩 제거; camera_publisher 기본과 일치)
export GP_SCENE="${GP_SCENE:-$_HERE/scene/gp_scene.usd}"
ISAAC=~/dev_ws/isaac_sim/isaacsim/_build/linux-x86_64/release
# 전체 raw 출력은 $LOG 에 전량 보존(tee). 콘솔에서는 standalone+OG
# 렌더프로덕트의 알려진-양성 2종(omni.usd-abi getRenderSettings stage-id
# + 짝지은 json 's')만 필터 — 증거상 씬/MCP/애너테이터 무관·기능 무영향
# 으로 확정(분석: dev-docs/project_requirments §6 / debugging.md §12).
# 가림 아님: raw 로그 전량 남으므로 실제 이상 발생 시 그대로 진단 가능.
LOG=/tmp/cobot3_isaac_gui.log
echo "[run] raw 로그(전량) → $LOG | 콘솔은 알려진-양성 2종 필터"
"$ISAAC/python.sh" /home/rokey/dev_ws/isaac_sim/cobot3/main_side/camera_publisher.py 2>&1 \
  | tee "$LOG" \
  | grep --line-buffered -vF \
      -e 'getRenderSettings failed getting a stage-id' \
      -e "last read: 's'"
exit "${PIPESTATUS[0]}"
