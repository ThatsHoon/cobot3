#!/bin/bash
# capture_sample.sh — 시연 도중 sub1 이 수신하는 모든 ROS2 토픽을 짧게 캡처.
# 다음 세션의 Foxglove 패널 설계용 데이터 종류·구조 분석 자료.
#
# 사용: bash sub1_side/server/capture_sample.sh [DURATION_SEC]
# 기본 30초. 출력: /tmp/cobot3_sample_HHMMSS/
#   sample/      — MCAP bag (Lichtblick 재생 가능)
#   topic_list.txt — 활성 토픽·타입·QoS
#   topic_hz.txt   — 각 토픽 hz/bw (1회 스냅)
set -e
DUR="${1:-30}"
TS=$(date +%H%M%S)
OUT=/tmp/cobot3_sample_$TS
mkdir -p "$OUT"

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source /opt/ros/humble/setup.bash
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}"
export FASTRTPS_DEFAULT_PROFILES_FILE="${FASTRTPS_DEFAULT_PROFILES_FILE:-$REPO_ROOT/sub1_side/fastdds_web.xml}"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-129}"
export ROS_LOCALHOST_ONLY=0

echo "[capture] OUT=$OUT  DUR=${DUR}s  DOMAIN_ID=$ROS_DOMAIN_ID"
ros2 topic list -t > "$OUT/topic_list.txt"
echo "[capture] topic_list.txt: $(wc -l < "$OUT/topic_list.txt") 토픽"

# MCAP bag — 모든 토픽 (-a). storage mcap (Lichtblick 호환).
echo "[capture] ros2 bag record 시작 (${DUR}s)..."
( cd "$OUT" && timeout "$DUR" ros2 bag record -a -s mcap -o sample 2>&1 | tail -20 ) || true

# 각 토픽 2초 hz 스냅 (병행 X — bag 종료 후)
echo "[capture] topic_hz 스냅..."
ros2 topic list | while read t; do
    [ -z "$t" ] && continue
    H=$(timeout 2 ros2 topic hz "$t" 2>&1 | grep "average rate" | tail -1 \
        || echo "no_publisher_or_silent")
    echo "$t :: $H" >> "$OUT/topic_hz.txt"
done

echo "[capture] === 완료 ==="
du -sh "$OUT"
ls -la "$OUT/"
echo
echo "Lichtblick(:8080) 에서 'Open file' → $OUT/sample/sample_0.mcap 으로 재생/분석"
