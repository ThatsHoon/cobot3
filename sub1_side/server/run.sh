#!/usr/bin/env bash
# C2 web_server 기동 (C2 PC 에서 실행 — Main PC 아님)
set -e
cd "$(dirname "$0")"

# ROS 2 Humble + Main PC 와 동일 도메인 (설계 §4.2 / D10)
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-130}"
export ROS_LOCALHOST_ONLY=0
# Isaac Sim ROS2 bridge 와 DDS 통일 (FastDDS 디스커버리 불일치 회피)
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}"
# 웹/C2 PC 자체 프로파일을 기본 사용 (별도 PC 에 Main PC 경로가 없어
# 무음 실패하던 버그 수정). 같은-PC 임시모드는 bashrc 가 export 한 값이
# 우선되어 기존 동작 불변. 설정/IP 치환: ../FASTDDS.md
export FASTRTPS_DEFAULT_PROFILES_FILE="${FASTRTPS_DEFAULT_PROFILES_FILE:-$(cd .. && pwd)/fastdds_web.xml}"

# 로컬 Postgres / 인증 (설계 §4.3 / §13)
export COBOT3_DB_URL="${COBOT3_DB_URL:-postgresql:///cobot3}"
# export ISAAC_SIM_API_KEY=...   # 변경계열 보호용 (미설정 시 LAN 개발모드)

# venv 의 uvicorn 을 명시적으로 사용 (PATH 의존 제거). 없으면 시스템 fallback.
if [ -x ./.venv/bin/uvicorn ]; then
    exec ./.venv/bin/uvicorn app:app --host "${C2_HTTP_HOST:-0.0.0.0}" --port "${C2_HTTP_PORT:-8000}"
else
    exec python3 -m uvicorn app:app --host "${C2_HTTP_HOST:-0.0.0.0}" --port "${C2_HTTP_PORT:-8000}"
fi
