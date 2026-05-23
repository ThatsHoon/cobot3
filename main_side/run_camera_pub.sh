#!/usr/bin/env bash
# standalone 카메라 퍼블리셔 기동 (MCP/GUI 비의존, FastDDS 정공).
# GUI Isaac 과 동시에 띄우면 GPU 경합 → GUI Isaac 은 닫고 실행 권장.
set -e
_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 사이트 IP 단일소스(SSOT): common/site.env → 자동 파생
[ -f "$_HERE/../common/site.sh" ] && source "$_HERE/../common/site.sh"

# ── ★ 시스템 ROS2 Humble 소싱 (no-scrub — 정공 핵심 수정) ──────────────
# camera_publisher.py 는 rclpy 를 import 하지 않음(순수 OG C++ 브리지) →
# 과거 scrub 의 전제(Isaac py3.11 ↔ 시스템 py3.10 rclpy 충돌)가 이
# 프로세스엔 적용되지 않는다. scrub 는 오히려 Isaac C++ 브리지가 시스템
# fastrtps 2.6.11(= C2 와 동일·와이어 호환) 대신 internal/엉뚱한 libs 를
# 쓰게 만든 자해였음(이전 "정공 불가" 오진의 핵심). no-scrub 로 시스템
# 2.6.11 로드 → 시스템 ROS2 와 양방향 정공 동작. (검증: /robot/odom 63Hz,
# /robot/cmd_vel 다운링크 RX, FASTDDS.md §6.) render=True 는 코드에 이미
# 적용(타임라인 전진 → OnPlaybackTick 펄스 → OG ROS2 노드 write/read).
source /opt/ros/humble/setup.bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
# FastDDS: env > site.env 자동 치환본(2-PC) > 기본 UDP-only. (FASTDDS.md §3)
if [ -z "${FASTRTPS_DEFAULT_PROFILES_FILE:-}" ]; then
  export FASTRTPS_DEFAULT_PROFILES_FILE="$_HERE/fastdds_no_shm.xml"
fi
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-129}"
export ROS_LOCALHOST_ONLY=0
export ROS_DISTRO=humble
# 어떤 씬을 쓸지 (기본 cobot3_1.usd; 없으면 스크립트가 최소 구성/빈 스테이지)
export GP_HEADLESS=1
# 동봉 이식 씬(스크립트 상대 — 하드코딩 제거; camera_publisher 기본과 일치)
export GP_SCENE="${GP_SCENE:-$_HERE/scene/gp_scene.usd}"
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
