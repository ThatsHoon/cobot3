#!/usr/bin/env bash
# 발행측 영상/depth 대역 절감 노드 다중 기동 (Tier 1 통신 효율화 2026-05-24).
# RGB:
#   후방:    /cam/rear/rgb              → /c2/rear/compressed  (JPEG 640×360 5fps)
#   검사:    /cam/inspect/rgb           → /c2/inspect/compressed
#   오버헤드: /cam/overhead/rgb         → /c2/overhead/compressed
#   TP_A~D: /cam/tactical/tp_x/rgb    → /c2/tp_x/compressed
# Depth (NEW 2026-05-24, LAN 9MB/s → 0.4MB/s):
#   TP_A~D: /cam/tactical/tp_x/depth → /c2/tp_x/depth_compressed (PNG 320×180 2fps)
# Isaac 미기동이어도 먼저 떠서 토픽을 기다린다(무해).
# WHY: 각 노드를 _restart_loop 함수로 감싸 비정상 종료 시 자동 재기동.
#   영상 끊김의 주원인이 degrade 노드의 조용한 종료임을 실측으로 확인(2026-05-27).
set -e
cd "$(dirname "$0")"
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-130}"
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}"
export FASTRTPS_DEFAULT_PROFILES_FILE="${FASTRTPS_DEFAULT_PROFILES_FILE:-$PWD/fastdds_no_shm.xml}"
export ROS_LOG_DIR="${ROS_LOG_DIR:-/tmp/cobot3_ros_logs}"
mkdir -p "$ROS_LOG_DIR"
PY=""
for CAND in \
  "/home/rokey/dev_ws/isaac_sim/cobot3/sub1_side/server/.venv/bin/python" \
  "python3"
do
  if command -v "$CAND" >/dev/null 2>&1 && "$CAND" -c "import rclpy, cv2, numpy" >/dev/null 2>&1; then
    PY="$CAND"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "[run_degrade] usable python not found (needs rclpy, cv2, numpy)" >&2
  exit 1
fi
echo "[run_degrade] PY=$PY"

# WHY: 크래시 후 2초 대기 뒤 재기동. 무한 루프로 안정성 보장.
# 재시작 시 "[restart]" 로 기록해 감시 가능.
_restart_loop() {
  local label="$1"; shift
  while true; do
    echo "[run_degrade] START $label"
    "$@" || true
    echo "[run_degrade] RESTART $label (2s 후 재기동)"
    sleep 2
  done
}

# FRAME_TIMING=1: inspect 채널 발송 시각 로그 (c2 수신 시각과 비교해 네트워크 지연 측정)
_restart_loop "rear"     env DEGRADE_IN=/cam/rear/rgb     DEGRADE_OUT=/c2/rear/compressed      "$PY" video_degrade_node.py &
_restart_loop "inspect"  env DEGRADE_IN=/cam/inspect/rgb  DEGRADE_OUT=/c2/inspect/compressed  FRAME_TIMING="${FRAME_TIMING:-1}" "$PY" video_degrade_node.py &
_restart_loop "overhead" env DEGRADE_IN=/cam/overhead/rgb DEGRADE_OUT=/c2/overhead/compressed  "$PY" video_degrade_node.py &
_restart_loop "tp_a"     env DEGRADE_IN=/cam/tactical/tp_a/rgb DEGRADE_OUT=/c2/tp_a/compressed "$PY" video_degrade_node.py &
_restart_loop "tp_b"     env DEGRADE_IN=/cam/tactical/tp_b/rgb DEGRADE_OUT=/c2/tp_b/compressed "$PY" video_degrade_node.py &
_restart_loop "tp_c"     env DEGRADE_IN=/cam/tactical/tp_c/rgb DEGRADE_OUT=/c2/tp_c/compressed "$PY" video_degrade_node.py &
_restart_loop "tp_d"     env DEGRADE_IN=/cam/tactical/tp_d/rgb DEGRADE_OUT=/c2/tp_d/compressed "$PY" video_degrade_node.py &

# Depth 압축 (LAN 9MB/s 절감) — 320×180 PNG 16UC1, 2fps
_restart_loop "depth_tp_a" env DEPTH_IN=/cam/tactical/tp_a/depth DEPTH_OUT=/c2/tp_a/depth_compressed "$PY" depth_degrade_node.py &
_restart_loop "depth_tp_b" env DEPTH_IN=/cam/tactical/tp_b/depth DEPTH_OUT=/c2/tp_b/depth_compressed "$PY" depth_degrade_node.py &
_restart_loop "depth_tp_c" env DEPTH_IN=/cam/tactical/tp_c/depth DEPTH_OUT=/c2/tp_c/depth_compressed "$PY" depth_degrade_node.py &
_restart_loop "depth_tp_d" env DEPTH_IN=/cam/tactical/tp_d/depth DEPTH_OUT=/c2/tp_d/depth_compressed "$PY" depth_degrade_node.py &

wait
