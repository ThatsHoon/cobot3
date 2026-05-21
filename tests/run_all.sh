#!/bin/bash
# DMZ Sentry 통합 테스트 일괄 실행. 사전조건: PostgreSQL + ROS humble.
# pytest 63개 (54 시스템 + 9 venv) + e2e 안내 (T12, T13).
set -e
_REPO="$(cd "$(dirname "$0")/.." && pwd)"
source /opt/ros/humble/setup.bash

echo "═══ Phase 1+2+3 : pytest 단위 + ROS round-trip + DB ═══"
python3 -m pytest "$_REPO/tests" -v \
    --ignore="$_REPO/tests/test_api_endpoints.py" \
    --ignore="$_REPO/tests/_ros_helpers.py"

echo
echo "═══ Phase 3-API : FastAPI (venv 안에서 실행) ═══"
"$_REPO/sub1_side/server/.venv/bin/python" -m pytest \
    "$_REPO/tests/test_api_endpoints.py" -v

echo
echo "═══ Phase 4-6 : e2e (수동) ═══"
cat <<EOF
1. isaac-clear ; cobot3-start_all     # Main 역할 자동
2. (별도 셸 또는 C2 PC) cobot3-start_all   # C2 역할 자동
3. ros2 lifecycle get /bt_navigator   → "active [3]"
4. ros2 topic pub --once /mission_command std_msgs/String "{data: 'sortie'}"
5. ros2 topic echo --once --field data /patrol_state  → "mode": "PATROL"
6. ros2 topic pub --once /alerts std_msgs/String "{data: '{\"level\":\"ALERT\",...}'}"
7. patrol_state mode 가 ALERT_STOP 으로 전환 후 6s 뒤 자동 PATROL 복귀
8. 브라우저 http://<C2_IP>:3000 → MapTrack cube/cone 마커, PatrolControls 버튼 동작
9. psql -d cobot3 -c "SELECT count(*) FROM patrol_state_log;" ≥ 1
10. T13 (DMZ_Zone): tests/test_e2e_dmz_zone.md 참조
    - export GP_GO2_SPAWN_ZONE=dmz; cobot3-start_all
    - ros2 run tf2_ros tf2_echo world Go2 → (0,0,*) 부근
    - ros2 topic echo --once --field data /scene/landmarks | grep zone:dmz
EOF
