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
# FastDDS 프로파일: env 지정 > common/site.env(SSOT) 자동 치환본(web) >
# placeholder 폴백. main_side 런처와 대칭(IP 단일소스). 설정: ../FASTDDS.md
[ -f ../../common/site.sh ] && source ../../common/site.sh
if [ -z "${FASTRTPS_DEFAULT_PROFILES_FILE:-}" ]; then
  command -v cobot3_fastdds_profile >/dev/null 2>&1 && _P="$(cobot3_fastdds_profile web 2>/dev/null || true)"
  export FASTRTPS_DEFAULT_PROFILES_FILE="${_P:-$(cd .. && pwd)/fastdds_web.xml}"
fi

# 로컬 Postgres / 인증 (설계 §4.3 / §13)
export COBOT3_DB_URL="${COBOT3_DB_URL:-postgresql:///cobot3}"
# export ISAAC_SIM_API_KEY=...   # 변경계열 보호용 (미설정 시 LAN 개발모드)

# venv 의 uvicorn 을 명시적으로 사용 (PATH·CWD 비의존 절대경로). 상대경로
# ./.venv 는 호출 위치에 따라 빗나가 시스템 python3 fallback(uvicorn 부재)
# 으로 샐 수 있어 $0 기준 절대경로로 고정.
VENV_UVICORN="$(cd "$(dirname "$0")" && pwd)/.venv/bin/uvicorn"
if [ -x "$VENV_UVICORN" ]; then
    exec "$VENV_UVICORN" app:app --host "${C2_HTTP_HOST:-0.0.0.0}" --port "${C2_HTTP_PORT:-8000}"
else
    exec python3 -m uvicorn app:app --host "${C2_HTTP_HOST:-0.0.0.0}" --port "${C2_HTTP_PORT:-8000}"
fi
