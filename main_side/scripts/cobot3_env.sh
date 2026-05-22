#!/usr/bin/env bash
# cobot3_env.sh — cobot3 bashrc 함수 모음. ~/.bashrc 에 source 로 추가.
#
# 사용법 (최초 1회):
#   echo "source $(pwd)/main_side/scripts/cobot3_env.sh" >> ~/.bashrc
#   source ~/.bashrc
#
# 또는 절대경로로:
#   echo "source /path/to/cobot3/main_side/scripts/cobot3_env.sh" >> ~/.bashrc

# cobot3 Postgres (local)
export COBOT3_DB_URL="postgresql:///cobot3"
export COBOT3_DB_HOST="localhost"
export COBOT3_DB_NAME="cobot3"

# cobot3 Isaac Sim GUI (2-PC ROS2 정공 모드): FastDDS UDP-only / DOMAIN 130 /
# LOCALHOST_ONLY=0 — Isaac OG 가 /cam/realsense/rgb 등을 LAN 으로 발행.
# run_camera_pub_gui.sh 가 시스템 ROS scrub + GP_HEADLESS=0 + 동봉 씬 로드.
# DISPLAY 필요(사용자 터미널에서 직접 실행). 종료: Isaac 창 닫기/Ctrl-C.
# ⚠ standalone(mcp 미적재) — isaac-sim MCP 서버 동시 가동 시 콘솔 폭주
#   (무해). 비활성: claude mcp remove "isaac-sim" -s user
cobot3-isaacSim-gui() {
    local M="$_COBOT3_REPO/main_side"
    if [ ! -f "$M/run_camera_pub_gui.sh" ]; then
        echo "[cobot3] $M/run_camera_pub_gui.sh 없음"; return 1
    fi
    if [ -z "$DISPLAY" ]; then
        echo "[cobot3] ⚠ DISPLAY 미설정 — GUI 표시 불가(데스크톱 세션에서 실행)"; return 1
    fi
    if pgrep -f "isaac_mcp/server.py" >/dev/null 2>&1; then
        echo "[cobot3] ⚠ isaac-sim MCP 서버 가동중 → 콘솔 json/getRenderSettings 폭주(무해)."
        echo "[cobot3]   끄려면: claude mcp remove \"isaac-sim\" -s user"
    fi
    # IP/프로파일은 런처가 common/site.env(SSOT) 로 자동 파생 — 여기서
    # 하드코딩하지 않는다. 특정 배포만 바꾸려면 site.env 수정 or env override.
    echo "[cobot3] Isaac Sim GUI · 2-PC 모드 (FastDDS UDP-only / DOMAIN 130 / LOCALHOST_ONLY=0)"
    echo "[cobot3] IP 소스: cobot3/common/site.env (FastDDS 자동 파생)"
    echo "[cobot3] 씬: main_side/scene/gp_scene.usd | OG 자동 Play·ROS2 발행 | 종료: 창 닫기/Ctrl-C"
    ( cd "$M" && exec bash run_camera_pub_gui.sh )
}

# cobot3 C2(sub1_side) 전체 재시작: 기존 웹서버 종료 → DB·서버·웹 재기동
cobot3-cobot3_web-restart_full() {
    local SUB1="$_COBOT3_REPO/sub1_side"
    if [ ! -d "$SUB1" ]; then echo "[cobot3] $SUB1 없음"; return 1; fi

    echo "[cobot3] (1/4) 기존 웹서버/웹 종료 ..."
    pkill -f "uvicorn app:app"  2>/dev/null
    pkill -f "sub1_side/server" 2>/dev/null
    pkill -f "next dev"         2>/dev/null
    pkill -f "next-server"      2>/dev/null
    pkill -f "video_degrade_node" 2>/dev/null
    pkill -f "telemetry_bridge_node" 2>/dev/null
    fuser -k 8000/tcp 3000/tcp  2>/dev/null
    sleep 1

    echo "[cobot3] (2/4) PostgreSQL 재시작 + 스키마 적용 ..."
    echo 'rokey1234' | sudo -S systemctl restart postgresql >/dev/null 2>&1
    for i in 1 2 3 4 5; do pg_isready -q && break; sleep 1; done
    createdb cobot3 2>/dev/null
    if psql -d cobot3 -f "$SUB1/db/schema.sql" >/tmp/cobot3_db.log 2>&1; then
        echo "[cobot3]     schema OK"
    else
        echo "[cobot3]     schema WARN → /tmp/cobot3_db.log"
    fi

    echo "[cobot3] (3/4) web_server :8000 기동 ..."
    ( cd "$SUB1/server" && \
      { [ -d .venv ] && source .venv/bin/activate; } ; \
      setsid bash run.sh </dev/null >/tmp/cobot3_server.log 2>&1 & )

    echo "[cobot3] (4/4) web :3000 기동 ..."
    ( cd "$SUB1/web" && \
      { [ -d node_modules ] || npm install >/tmp/cobot3_web_install.log 2>&1; } ; \
      setsid bash -c 'npm run dev' </dev/null >/tmp/cobot3_web.log 2>&1 & )

    echo "[cobot3] (+) video_degrade 기동 (Isaac /cam/realsense/rgb 대기) ..."
    ( cd $_COBOT3_REPO/main_side && \
      setsid bash run_degrade.sh </dev/null >/tmp/cobot3_degrade.log 2>&1 & )

    echo "[cobot3] (+) telemetry_bridge 기동 (Isaac /robot/odom 대기) ..."
    ( cd $_COBOT3_REPO/main_side && \
      setsid bash run_telemetry_bridge.sh </dev/null >/tmp/cobot3_telem.log 2>&1 & )

    sleep 3
    echo "[cobot3] 완료. 로그: /tmp/cobot3_{db,server,web,degrade,telem}.log"
    echo "  server  http://localhost:8000/healthz"
    echo "  web     http://localhost:3000"
    echo "  영상: Isaac(FastDDS)+Play 시 /cam/realsense/rgb → degrade → 웹"
    echo "  텔레메트리: Isaac OG /robot/{odom,gps*,state*} (*=telemetry_bridge 파생)"
}

# cobot3 C2 전체 종료: 웹서버(:8000)/웹(:3000)/video_degrade + PostgreSQL 정지
cobot3-cobot3_web-down() {
    echo "[cobot3] (1/2) 웹 관련 프로세스 종료 ..."
    local before
    before=$(pgrep -f "uvicorn app:app|sub1_side/server|next dev|next-server|video_degrade_node|telemetry_bridge_node" 2>/dev/null | wc -l)
    pkill -f "uvicorn app:app"    2>/dev/null
    pkill -f "sub1_side/server"   2>/dev/null
    pkill -f "next dev"           2>/dev/null
    pkill -f "next-server"        2>/dev/null
    pkill -f "video_degrade_node" 2>/dev/null
    pkill -f "telemetry_bridge_node" 2>/dev/null
    fuser -k 8000/tcp 3000/tcp    2>/dev/null
    sleep 1
    # 잔존 시 강제 종료
    pkill -9 -f "uvicorn app:app|sub1_side/server|next dev|next-server|video_degrade_node|telemetry_bridge_node" 2>/dev/null
    local after
    after=$(pgrep -f "uvicorn app:app|sub1_side/server|next dev|next-server|video_degrade_node|telemetry_bridge_node" 2>/dev/null | wc -l)
    echo "[cobot3]     종료 대상 ${before}개 → 잔존 ${after}개"
    fuser 8000/tcp 3000/tcp 2>/dev/null && echo "[cobot3]     ⚠ 8000/3000 포트 여전히 점유" || echo "[cobot3]     8000/3000 포트 해제됨"

    echo "[cobot3] (2/2) PostgreSQL 정지 ..."
    echo 'rokey1234' | sudo -S systemctl stop postgresql >/dev/null 2>&1
    sleep 1
    if pg_isready -q 2>/dev/null; then
        echo "[cobot3]     ⚠ PostgreSQL 아직 응답 — systemctl status postgresql 확인"
    else
        echo "[cobot3]     PostgreSQL 정지됨"
    fi
    echo "[cobot3] 완료 — C2 웹/DB 전체 종료. 재기동: cobot3-cobot3_web-restart_full"
}

# ───────────────────────── cobot3 통합 기동/종료 ─────────────────────────
# start_all = 2-PC ROS2 정공. site.env IP ↔ 로컬 NIC 로 역할 자동판별:
#   MAIN(Isaac PC) = Isaac(OG 텔레메트리·보행 컨트롤러·cmd_vel 수신)
#   C2(웹 PC)     = PG·web_server·web·foxglove_bridge·Lichtblick(+cloudflared)
#   각 PC 에서 동일 명령:
#     cobot3-start_all           = 일반(standalone camera_pub, MCP 확장 미적재)
#     cobot3-start_all-with_mcp  = Isaac + isaac-sim-mcp 확장(:8766, 라이브 MCP 제어)
#   (MCP 모드는 MAIN 에만 영향; C2 역할은 두 명령 동일)
# down_all = 위 모두 + Isaac + Lichtblick 컨테이너 + 포트 + PostgreSQL 정리.
# 이 파일의 위치에서 레포 루트를 동적으로 계산 (하드코딩 없음)
_COBOT3_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

_cobot3_pg_up() {   # PostgreSQL 재시작 + 스키마 멱등 적용
    local SUB1="$_COBOT3_REPO/sub1_side"
    echo "[cobot3] PostgreSQL 재시작 + 스키마 ..."
    echo 'rokey1234' | sudo -S systemctl restart postgresql >/dev/null 2>&1
    local i; for i in 1 2 3 4 5; do pg_isready -q && break; sleep 1; done
    createdb cobot3 2>/dev/null
    if psql -d cobot3 -f "$SUB1/db/schema.sql" >/tmp/cobot3_db.log 2>&1; then
        echo "[cobot3]   schema OK"
    else
        echo "[cobot3]   schema WARN → /tmp/cobot3_db.log"
    fi
}

_cobot3_web_up() {  # web_server :8000 (+ web :3000)
    local SUB1="$_COBOT3_REPO/sub1_side"
    echo "[cobot3] web_server :8000 기동 ..."
    ( cd "$SUB1/server" && \
      { [ -d .venv ] && source .venv/bin/activate; } ; \
      setsid bash run.sh </dev/null >/tmp/cobot3_server.log 2>&1 & )
    echo "[cobot3] web :3000 기동 ..."
    ( cd "$SUB1/web" && \
      { [ -d node_modules ] || npm install >/tmp/cobot3_web_install.log 2>&1; } ; \
      setsid bash -c 'npm run dev' </dev/null >/tmp/cobot3_web.log 2>&1 & )
}

_cobot3_foxglove_up() {  # foxglove_bridge :8765 + Lichtblick docker :8080
    local SUB1="$_COBOT3_REPO/sub1_side"
    echo "[cobot3] foxglove_bridge :8765 기동 ..."
    ( cd "$SUB1" && \
      setsid bash run_foxglove_bridge.sh </dev/null >/tmp/cobot3_foxglove.log 2>&1 & )
    echo "[cobot3] Lichtblick 컨테이너 :8080 기동 ..."
    echo 'rokey1234' | sudo -S docker rm -f cobot3-lichtblick >/dev/null 2>&1
    echo 'rokey1234' | sudo -S docker run -d --name cobot3-lichtblick \
      --restart unless-stopped -p 8080:8080 \
      -v "$SUB1/lichtblick/layout.json:/lichtblick/default-layout.json:ro" \
      ghcr.io/lichtblick-suite/lichtblick:latest >/dev/null 2>&1 \
      && echo "[cobot3]   Lichtblick OK (http://localhost:8080)" \
      || echo "[cobot3]   ⚠ Lichtblick 기동 실패 — sudo docker logs cobot3-lichtblick"
}

_cobot3_role() {    # site.env IP ↔ 로컬 NIC → MAIN|C2|UNKNOWN
    [ -f "$_COBOT3_REPO/common/site.sh" ] && source "$_COBOT3_REPO/common/site.sh" \
        && cobot3_site_load >/dev/null 2>&1
    local ips=" $(hostname -I 2>/dev/null) "
    if   [ -n "$MAIN_SIDE_IP" ] && [[ "$ips" == *" $MAIN_SIDE_IP "* ]]; then echo MAIN
    elif [ -n "$SUB1_SIDE_IP" ] && [[ "$ips" == *" $SUB1_SIDE_IP "* ]]; then echo C2
    else echo UNKNOWN; fi
}

# Isaac 백그라운드 기동. $1 = 모드:
#   gui : standalone camera_pub GUI (run_camera_pub_gui.sh, MCP 확장 미적재)
#   mcp : Isaac Sim + isaac-sim-mcp 확장 (포트 8766, Claude/MCP 라이브 제어용)
# 호출자가 GP_ROS2_TELEM/GP_SPOT_CONTROL 을 export 해 두면 gui 런처가 존중.
# DISPLAY 없으면 GUI 불가 → 나머지 스택은 살리고 Isaac 만 건너뜀.
_cobot3_isaac_up() {
    local mode="${1:-gui}" MAIN="$_COBOT3_REPO/main_side"
    if [ -z "$DISPLAY" ]; then
        echo "[cobot3] ⚠ DISPLAY 미설정 → GUI Isaac 생략(나머지 스택은 가동)."
        echo "[cobot3]   데스크톱 세션에서 'cobot3-isaacSim-gui' 로 별도 기동."
        return 0
    fi
    if [ "$mode" = mcp ]; then
        echo "[cobot3] Isaac Sim + isaac-sim-mcp 확장 기동 (MCP :8766) ..."
        ( cd "$MAIN" && setsid env \
            RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
            FASTRTPS_DEFAULT_PROFILES_FILE="$MAIN/fastdds_no_shm.xml" \
            ROS_DOMAIN_ID=130 ROS_LOCALHOST_ONLY=0 \
            ~/dev_ws/isaac_sim/isaacsim/_build/linux-x86_64/release/isaac-sim.sh \
            --ext-folder ~/dev_ws/isaacsim-mcp-server/ \
            --enable isaac.sim.mcp_extension \
            </dev/null >/tmp/cobot3_isaac_mcp.console.log 2>&1 & )
        echo "[cobot3]   MCP 준비 후: camera_publisher 로직을 MCP 로 주입/구동"
        echo "[cobot3]   로그 tail -f /tmp/cobot3_isaac_mcp.console.log"
        return 0
    fi
    if pgrep -f "isaac_mcp/server.py" >/dev/null 2>&1; then
        echo "[cobot3] ⚠ isaac-sim MCP 서버 가동중 → Isaac 콘솔 json/getRenderSettings 폭주(무해)"
        echo "[cobot3]   끄려면: claude mcp remove \"isaac-sim\" -s user (또는 cobot3-start_all-with_mcp 사용)"
    fi
    # Go2 정찰 사양 (2026-05-20): Nav2 외부 경로 사용 시 내부 P-제어 비활성
    # (충돌 방지), SETTLE 1000→00(10초) — 시연 대기 단축.
    export GP_GO2_NAV="${GP_GO2_NAV:-0}"
    export GP_GO2_SETTLE="${GP_GO2_SETTLE:-500}"
    echo "[cobot3] Isaac Sim GUI 기동 (standalone camera_pub, MCP 미적재; GP_ROS2_TELEM=${GP_ROS2_TELEM:-1} GP_SPOT_CONTROL=${GP_SPOT_CONTROL:-1} GP_GO2_NAV=$GP_GO2_NAV GP_GO2_SETTLE=$GP_GO2_SETTLE) ..."
    ( cd "$MAIN" && \
      setsid bash run_camera_pub_gui.sh </dev/null >/tmp/cobot3_isaac_gui.console.log 2>&1 & )
}

# 하위호환 별칭(기존 호출부·머슬메모리 보호)
_cobot3_isaac_gui_up() { _cobot3_isaac_up gui; }

# 공용 구현: $1 = Isaac 모드(gui|mcp). MCP 는 MAIN(Isaac PC)에만 의미 있음.
_cobot3_start_all_impl() {
    local _im="${1:-gui}"
    local MAIN="$_COBOT3_REPO/main_side" SUB1="$_COBOT3_REPO/sub1_side"
    if [ ! -d "$_COBOT3_REPO" ]; then echo "[cobot3] $_COBOT3_REPO 없음"; return 1; fi
    # site.sh 를 이 함수 스코프에 source(서브셸 아님 → 함수/IP 가 분기까지 유지).
    # _cobot3_role 은 $(...) 서브셸이라 그 안의 source 는 여기로 안 남는다.
    [ -f "$_COBOT3_REPO/common/site.sh" ] && source "$_COBOT3_REPO/common/site.sh" \
        && cobot3_site_load >/dev/null 2>&1
    local role; role="$(_cobot3_role)"
    echo "[cobot3] ===== start_all : 2-PC ROS2 정공 (역할=$role / Isaac=$_im) ====="
    echo "[cobot3] site.env MAIN=$MAIN_SIDE_IP SUB1=$SUB1_SIDE_IP / 로컬IP=$(hostname -I)"
    # 좀비 정리 (2-pass: SIGTERM → SIGKILL). 2026-05-20 강화.
    echo "[cobot3] 좀비 프로세스 정리 중 ..."
    cobot3-down_all >/dev/null 2>&1
    # 추가 안전망: 패턴 grep 으로 잔존 검사·강제 종료
    local _LEFT_PAT="camera_publisher\.py|mission_echo\.py|npc_relay\.py|video_degrade_node|inspect_relay\.py|world_odom_tf_pub\.py|landmarks_pub\.py|telemetry_bridge_node|nav2_patrol\.py|cmd_vel_safety_filter\.py|fall_relay\.py|weapon_relay\.py|wind_publisher\.py|run_nav2\.sh|nav2_bringup|nav2_lifecycle_manager|map_server|controller_server|smoother_server|planner_server|behavior_server|bt_navigator|waypoint_follower|velocity_smoother|uvicorn app:app|next dev|run_urdf_server\.sh|run_camera_pub|run_degrade"
    sleep 1
    if pgrep -f "$_LEFT_PAT" >/dev/null 2>&1; then
        local _N; _N=$(pgrep -f "$_LEFT_PAT" 2>/dev/null | wc -l)
        echo "[cobot3]   ⚠ down_all 후 잔존 ${_N}개 — SIGKILL 강제"
        pkill -9 -f "$_LEFT_PAT" 2>/dev/null
        sleep 2
    fi
    echo "[cobot3]   정리 완료 (잔존 $(pgrep -f "$_LEFT_PAT" 2>/dev/null | wc -l)개)"
    case "$role" in
      MAIN)
        # ROS2 정공: OG 텔레메트리(GP_ROS2_TELEM=1) + 보행 컨트롤러(GP_SPOT_CONTROL=1).
        # video_degrade: /cam/front/rgb → /c2/front/compressed, /cam/rear/rgb → /c2/rear/compressed (2×, 5fps)
        # telemetry_bridge: /robot/odom → /robot/gps + /robot/state
        # C2 ros_bridge 가 FastDDS LAN 으로 직접 구독 → HTTP /ingest 미사용.
        echo "[cobot3] 역할=MAIN(Isaac PC, Isaac=$_im) → Isaac + video_degrade + telemetry_bridge."
        _cobot3_isaac_up "$_im"
        # MCP 모드: 나머지 사이드카 스킵 — Isaac+MCP 확장만 단독.
        # camera_publisher 미실행 → video_degrade·telemetry·urdf 등 무의미.
        # 또한 run_urdf_server.sh 가 :8766 점유 시 MCP 확장 바인딩 실패.
        if [ "$_im" = mcp ]; then
            echo "[cobot3]   MCP 모드 — 나머지 사이드카(video_degrade/telemetry/urdf/...) 스킵"
            echo "[cobot3] ===== 완료 (MCP) — MCP execute_script 로 씬 제어 ====="
            return 0
        fi
        echo "[cobot3] video_degrade_node 기동 ..."
        ( cd "$MAIN" && setsid bash run_degrade.sh </dev/null >/tmp/cobot3_degrade.log 2>&1 & )
        echo "[cobot3] telemetry_bridge_node 기동 ..."
        ( cd "$MAIN" && setsid bash run_telemetry_bridge.sh </dev/null >/tmp/cobot3_telemetry_bridge.log 2>&1 & )
        # DMZ Sentry M9: world→odom static TF + landmarks 사이드카
        echo "[cobot3] world_odom_tf_pub 기동 ..."
        ( cd "$MAIN" && setsid bash -c "source /opt/ros/humble/setup.bash \
              && export RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
              && export FASTRTPS_DEFAULT_PROFILES_FILE=$MAIN/fastdds_no_shm.xml \
              && export ROS_DOMAIN_ID=130 \
              && python3 world_odom_tf_pub.py" \
              </dev/null >/tmp/cobot3_world_odom_tf.log 2>&1 & )
        echo "[cobot3] landmarks_pub 기동 ..."
        ( cd "$MAIN" && setsid bash -c "source /opt/ros/humble/setup.bash \
              && export RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
              && export FASTRTPS_DEFAULT_PROFILES_FILE=$MAIN/fastdds_no_shm.xml \
              && export ROS_DOMAIN_ID=130 \
              && python3 landmarks_pub.py" \
              </dev/null >/tmp/cobot3_landmarks_pub.log 2>&1 & )
        echo "[cobot3] inspect_relay 기동 ..."
        ( cd "$MAIN" && setsid bash -c "source /opt/ros/humble/setup.bash \
              && export RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
              && export FASTRTPS_DEFAULT_PROFILES_FILE=$MAIN/fastdds_no_shm.xml \
              && export ROS_DOMAIN_ID=130 \
              && python3 inspect_relay.py" \
              </dev/null >/tmp/cobot3_inspect_relay.log 2>&1 & )
        echo "[cobot3] mission_echo 기동 ..."
        ( cd "$MAIN" && setsid bash -c "source /opt/ros/humble/setup.bash \
              && export RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
              && export FASTRTPS_DEFAULT_PROFILES_FILE=$MAIN/fastdds_no_shm.xml \
              && export ROS_DOMAIN_ID=130 \
              && python3 mission_echo.py" \
              </dev/null >/tmp/cobot3_mission_echo.log 2>&1 & )
        echo "[cobot3] npc_relay 기동 ..."
        ( cd "$MAIN" && setsid bash -c "source /opt/ros/humble/setup.bash \
              && export RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
              && export FASTRTPS_DEFAULT_PROFILES_FILE=$MAIN/fastdds_no_shm.xml \
              && export ROS_DOMAIN_ID=130 \
              && python3 npc_relay.py" \
              </dev/null >/tmp/cobot3_npc_relay.log 2>&1 & )
        echo "[cobot3] URDF :8766 server 기동 ..."
        ( cd "$MAIN" && setsid bash run_urdf_server.sh \
              </dev/null >/tmp/cobot3_urdf_server.log 2>&1 & )
        echo "[cobot3] camera_info_publisher 기동 ..."
        ( cd "$MAIN" && setsid bash -c "source /opt/ros/humble/setup.bash \
              && export RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
              && export FASTRTPS_DEFAULT_PROFILES_FILE=$MAIN/fastdds_no_shm.xml \
              && export ROS_DOMAIN_ID=130 \
              && python3 camera_info_publisher.py" \
              </dev/null >/tmp/cobot3_camera_info.log 2>&1 & )
        echo "[cobot3] fall_relay 기동 ..."
        ( cd "$MAIN" && setsid bash -c "source /opt/ros/humble/setup.bash \
              && export RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
              && export FASTRTPS_DEFAULT_PROFILES_FILE=$MAIN/fastdds_no_shm.xml \
              && export ROS_DOMAIN_ID=130 \
              && python3 fall_relay.py" \
              </dev/null >/tmp/cobot3_fall_relay.log 2>&1 & )
        echo "[cobot3] weapon_relay 기동 ..."
        ( cd "$MAIN" && setsid bash -c "source /opt/ros/humble/setup.bash \
              && export RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
              && export FASTRTPS_DEFAULT_PROFILES_FILE=$MAIN/fastdds_no_shm.xml \
              && export ROS_DOMAIN_ID=130 \
              && python3 weapon_relay.py" \
              </dev/null >/tmp/cobot3_weapon_relay.log 2>&1 & )
        echo "[cobot3] wind_publisher 기동 ..."
        ( cd "$MAIN" && setsid bash -c "source /opt/ros/humble/setup.bash \
              && export RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
              && export FASTRTPS_DEFAULT_PROFILES_FILE=$MAIN/fastdds_no_shm.xml \
              && export ROS_DOMAIN_ID=130 \
              && python3 wind_publisher.py" \
              </dev/null >/tmp/cobot3_wind_publisher.log 2>&1 & )
        # Nav2 stack (2026-05-21 sub1_side → main_side 이동, 로봇 onboard 패턴).
        # 2026-05-21 fix: Isaac 가 씬/OG 로드 중 CPU 점유율 매우 높을 때 nav2
        # lifecycle service RMW response 가 손실 → planner_server 응답 timeout →
        # lifecycle_manager autostart 중단 → bt_navigator unconfigured → sortie
        # 무한 WAITING_FOR_NAV2. 해결: Isaac 가 stepping 안정화될 때까지 nav2
        # 기동 지연. /clock 첫 메시지 도착이 안정화 신호 (camera_publisher 의
        # OG ROS2PublishClock 가 발행 시작 = scene/OG 빌드 완료).
        echo "[cobot3] Isaac 안정화 대기 (/clock 첫 메시지 또는 최대 90s) ..."
        ( source /opt/ros/humble/setup.bash 2>/dev/null \
            && export ROS_DOMAIN_ID=130 RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
            && export FASTRTPS_DEFAULT_PROFILES_FILE=$MAIN/fastdds_no_shm.xml \
            && timeout 90 ros2 topic echo /clock --once >/dev/null 2>&1 \
            && echo "[cobot3]   /clock 수신 — 추가 5초 후 nav2 기동" \
            && sleep 5 \
            || echo "[cobot3]   ⚠ /clock 90s 미수신 — fallback 진행"
          echo "[cobot3] Nav2 stack 기동 ..."
          cd "$MAIN" && setsid bash run_nav2.sh \
                </dev/null >/tmp/cobot3_nav2.log 2>&1 &
          echo "[cobot3] cmd_vel_safety_filter 기동 ..."
          ( cd "$MAIN" && setsid bash -c "source /opt/ros/humble/setup.bash \
                && export RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
                && export FASTRTPS_DEFAULT_PROFILES_FILE=$MAIN/fastdds_no_shm.xml \
                && export ROS_DOMAIN_ID=130 \
                && python3 cmd_vel_safety_filter.py" \
                </dev/null >/tmp/cobot3_cmd_vel_safety.log 2>&1 & )
          # nav2_patrol 은 lifecycle activate 완료 후 (8s 마진) 기동
          sleep 8
          echo "[cobot3] nav2_patrol 기동 ..."
          ( cd "$MAIN" && setsid bash -c "source /opt/ros/humble/setup.bash \
                && export RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
                && export FASTRTPS_DEFAULT_PROFILES_FILE=$MAIN/fastdds_no_shm.xml \
                && export ROS_DOMAIN_ID=130 \
                && python3 nav2_patrol.py" \
                </dev/null >/tmp/cobot3_nav2_patrol.log 2>&1 & )
        ) &
        sleep 2
        echo "[cobot3] ===== 완료 (2-PC / MAIN / Isaac=$_im) ====="
        if [ "$_im" = mcp ]; then
          echo "  Isaac+MCP 기동 — tail -f /tmp/cobot3_isaac_mcp.console.log (MCP :8766)"
          echo "  MCP 준비 후 camera_publisher 로직을 MCP 로 주입/구동 필요"
        else
          echo "  Isaac GUI 기동 — tail -f /tmp/cobot3_isaac_gui.console.log"
        fi
        echo "  degrade    — tail -f /tmp/cobot3_degrade.log"
        echo "  telem_bridge — tail -f /tmp/cobot3_telemetry_bridge.log"
        echo "  검증: ros2 topic hz /robot/odom  → 63 Hz"
        echo "  ⚠ C2 PC($SUB1_SIDE_IP) 에서도 'cobot3-start_all' 실행 필요"
        ;;
      C2)
        # ROS2 정공: ros_bridge 가 Isaac 실토픽 직접 구독(domain130, FastDDS).
        # foxglove_bridge 도 동일 토픽 직접 구독 → /debug Lichtblick.
        echo "[cobot3] 역할=C2(웹 PC) → PG·web_server·web·foxglove·Lichtblick."
        # FastDDS 프로파일 최신화 (IP 변경 시 구 XML 로 기동하면 디스커버리 실패)
        command -v cobot3_fastdds_profile >/dev/null 2>&1 \
            && cobot3_fastdds_profile web >/dev/null 2>&1 \
            && echo "[cobot3]   FastDDS 프로파일 갱신 완료" || true
        _cobot3_pg_up
        _cobot3_web_up
        _cobot3_foxglove_up
        # DMZ Sentry M9: Nav2 + patrol controller + cmd_vel safety filter
        echo "[cobot3] Nav2 stack 기동 ..."
        ( cd "$SUB1/server" && setsid bash run_nav2.sh \
              </dev/null >/tmp/cobot3_nav2.log 2>&1 & )
        echo "[cobot3] cmd_vel_safety_filter 기동 ..."
        ( cd "$SUB1/server" && setsid bash -c "source /opt/ros/humble/setup.bash \
              && export RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
              && export FASTRTPS_DEFAULT_PROFILES_FILE=$SUB1/fastdds_web.xml \
              && export ROS_DOMAIN_ID=130 \
              && python3 cmd_vel_safety_filter.py" \
              </dev/null >/tmp/cobot3_cmd_vel_safety.log 2>&1 & )
        echo "[cobot3] nav2_patrol 기동 ..."
        ( cd "$SUB1/server" && setsid bash -c "source /opt/ros/humble/setup.bash \
              && export RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
              && export FASTRTPS_DEFAULT_PROFILES_FILE=$SUB1/fastdds_web.xml \
              && export ROS_DOMAIN_ID=130 \
              && python3 nav2_patrol.py" \
              </dev/null >/tmp/cobot3_nav2_patrol.log 2>&1 & )
        echo "[cobot3] foxglove_sdk_publisher :8767 기동 ..."
        ( cd "$SUB1/server" && setsid bash -c "source /opt/ros/humble/setup.bash \
              && export RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
              && export FASTRTPS_DEFAULT_PROFILES_FILE=$SUB1/fastdds_web.xml \
              && export ROS_DOMAIN_ID=130 \
              && /usr/bin/python3 foxglove_sdk_publisher.py" \
              </dev/null >/tmp/cobot3_foxglove_sdk.log 2>&1 & )
        if [ -x "$SUB1/run_cloudflared.sh" ] && [ -n "$PUBLIC_HOST" ]; then
          echo "[cobot3] cloudflared(공개 $PUBLIC_HOST) 기동 ..."
          ( cd "$SUB1" && setsid bash run_cloudflared.sh </dev/null >/tmp/cobot3_cloudflared.log 2>&1 & )
        fi
        sleep 3
        echo "[cobot3] ===== 완료 (2-PC / C2) ====="
        echo "  web http://localhost:3000 (/debug) · server :8000 · Lichtblick :8080"
        echo "  로그 /tmp/cobot3_{db,server,web,foxglove,cloudflared}.log"
        echo "  ⚠ Isaac PC($MAIN_SIDE_IP) 에서도 'cobot3-start_all' 실행 필요"
        ;;
      *)
        echo "[cobot3] ⚠ 역할 판별 실패 — 로컬 IP 가 site.env 의 MAIN/SUB1 와 불일치."
        echo "[cobot3]   common/site.env 의 IP 를 이 배포에 맞게 수정 후 재실행."
        return 1
        ;;
    esac
}

# 진입점: 일반(MCP 미적재, standalone camera_pub) / MCP 적재(라이브 제어)
cobot3-start_all()          { _cobot3_start_all_impl gui; }
cobot3-start_all-with_mcp() { _cobot3_start_all_impl mcp; }

# 로컬 전체 종료·정리 (웹/DB/브리지/Isaac/Lichtblick/포트) — 공용 본체
_cobot3_local_full_down() {
    # PAT — 모든 cobot3 관련 프로세스 패턴 (2026-05-20 mission_echo·npc_relay·urdf_server 포함)
    local PAT="uvicorn app:app|sub1_side/server|next dev|next-server|video_degrade_node|telemetry_bridge_node|foxglove_bridge|run_camera_pub|camera_publisher\.py|run_cloudflared|cloudflared.*cobot3|nav2_patrol\.py|cmd_vel_safety_filter\.py|world_odom_tf_pub\.py|landmarks_pub\.py|inspect_relay\.py|mission_echo\.py|npc_relay\.py|fall_relay\.py|weapon_relay\.py|wind_publisher\.py|run_urdf_server\.sh|run_nav2\.sh|nav2_bringup|nav2_lifecycle_manager|map_server|controller_server|smoother_server|planner_server|behavior_server|bt_navigator|waypoint_follower|velocity_smoother|foxglove_sdk_publisher\.py"
    pkill -f "$PAT" 2>/dev/null
    sleep 2
    # 2nd pass: 잔존 시 SIGKILL
    if pgrep -f "$PAT" >/dev/null 2>&1; then
        pkill -9 -f "$PAT" 2>/dev/null
        sleep 1
    fi
    echo 'rokey1234' | sudo -S docker rm -f cobot3-lichtblick >/dev/null 2>&1 \
      && echo "[cobot3]   Lichtblick 컨테이너 제거"
    fuser -k 8000/tcp 3000/tcp 8765/tcp 8080/tcp 2>/dev/null
    sleep 1
    local left; left=$(pgrep -f "$PAT" 2>/dev/null | wc -l)
    echo "[cobot3]   잔존 프로세스 ${left}개"
    for p in 8000 3000 8765 8080; do
        fuser "$p/tcp" >/dev/null 2>&1 && echo "[cobot3]   ⚠ 포트 $p 점유" \
            || echo "[cobot3]   포트 $p 해제"
    done
    echo "[cobot3] PostgreSQL 정지 ..."
    echo 'rokey1234' | sudo -S systemctl stop postgresql >/dev/null 2>&1
    sleep 1
    pg_isready -q 2>/dev/null && echo "[cobot3]   ⚠ PostgreSQL 아직 응답" \
        || echo "[cobot3]   PostgreSQL 정지됨"
}

# MAIN 측 프로세스 종료 — Isaac + 모든 사이드카 (mission_echo, npc_relay,
# urdf_server, inspect_relay 포함). 2026-05-20: 좀비 정리 강화 — SIGTERM
# 1차 → 잔존 검사 → SIGKILL 2차.
_cobot3_isaac_down() {
    # PAT — Main 측 모든 cobot3 프로세스 + Isaac kit/python 자식
    local PAT="run_camera_pub|camera_publisher\.py|camera_info_publisher\.py|video_degrade_node|run_degrade|telemetry_bridge_node|run_telemetry_bridge|world_odom_tf_pub\.py|landmarks_pub\.py|inspect_relay\.py|mission_echo\.py|npc_relay\.py|run_urdf_server\.sh|isaac\.sim\.mcp_extension|isaacsim/_build/linux-x86_64/release/isaac-sim\.sh|isaacsim/_build/linux-x86_64/release/python\.sh|isaacsim/_build/linux-x86_64/release/kit/python/bin/python3.*camera_publisher"
    pkill -f "$PAT" 2>/dev/null
    sleep 2
    if pgrep -f "$PAT" >/dev/null 2>&1; then
        pkill -9 -f "$PAT" 2>/dev/null
        sleep 1
    fi
    local n; n=$(pgrep -f "$PAT" 2>/dev/null | wc -l)
    if [ "$n" -gt 0 ]; then
        echo "[cobot3]   ⚠ MAIN 잔존 ${n}개 — 강제 재시도"
        pgrep -af "$PAT" | head -5
        pkill -9 -f "$PAT" 2>/dev/null
        sleep 1
        n=$(pgrep -f "$PAT" 2>/dev/null | wc -l)
    fi
    echo "[cobot3]   MAIN 잔존 프로세스 ${n}개"
}

# 2-PC 종료: 역할 자동판별 — MAIN=Isaac+degrade+telem / C2=웹·DB·브리지 전체
cobot3-down_all() {
    local role; role="$(_cobot3_role)"
    echo "[cobot3] ===== down_all : 2-PC 종료 (역할=$role) ====="
    case "$role" in
      MAIN)
        echo "[cobot3] MAIN → Isaac·video_degrade·telemetry_bridge 종료"
        _cobot3_isaac_down ;;
      C2)
        echo "[cobot3] C2 → 웹/DB/브리지/Lichtblick 전체 종료"
        _cobot3_local_full_down ;;
      *)
        echo "[cobot3] ⚠ 역할 판별 실패 → 안전하게 로컬 전체 종료"
        _cobot3_local_full_down ;;
    esac
    echo "[cobot3] ===== down_all 완료 ====="
}

# 강력 정리: down_all 이 못 잡는 잔존(stale URDF python3 -, MCP bridge,
# kit 좀비, 점유 포트) 까지 모두 SIGTERM → 2s → SIGKILL 2-pass.
# 역할 무관 — Isaac/MCP/cobot3 관련 모든 프로세스 + 점유 포트 해제.
cobot3-clear() {
    echo "[cobot3-clear] ===== 전체 잔존 정리 시작 ====="
    # 1) 역할 기반 정상 종료 우선 시도
    cobot3-down_all >/dev/null 2>&1
    # 2) 강화 PAT — down_all 미커버 (MCP bridge, stale URDF python3 -, kit)
    local PAT="kit/kit|isaac-sim\.sh|isaacsim/_build/linux-x86_64/release|isaac_mcp|isaac-sim-mcp/\.venv|camera_publisher\.py|camera_info_publisher\.py|video_degrade_node|telemetry_bridge_node|world_odom_tf_pub\.py|landmarks_pub\.py|inspect_relay\.py|mission_echo\.py|npc_relay\.py|fall_relay\.py|weapon_relay\.py|wind_publisher\.py|run_urdf_server\.sh|run_camera_pub|run_degrade|run_telemetry_bridge|run_nav2\.sh|nav2_bringup|nav2_lifecycle_manager|nav2_patrol\.py|cmd_vel_safety_filter\.py|map_server|controller_server|smoother_server|planner_server|behavior_server|bt_navigator|waypoint_follower|velocity_smoother|foxglove_sdk_publisher\.py|foxglove_bridge|uvicorn app:app|sub1_side/server|next dev|next-server|run_cloudflared|cloudflared.*cobot3"
    local before
    before=$(pgrep -f "$PAT" 2>/dev/null | wc -l)
    if [ "$before" -gt 0 ]; then
        echo "[cobot3-clear] (강화 PAT) SIGTERM ${before}개 ..."
        pkill -f "$PAT" 2>/dev/null
        sleep 2
        local mid
        mid=$(pgrep -f "$PAT" 2>/dev/null | wc -l)
        if [ "$mid" -gt 0 ]; then
            echo "[cobot3-clear] (강화 PAT) SIGKILL ${mid}개 잔존 강제 ..."
            pkill -9 -f "$PAT" 2>/dev/null
            sleep 1
        fi
    fi
    # 3) stale URDF: 'python3 -' (stdin script) from main_side cwd
    local stale
    stale=$(for p in $(pgrep -f "^python3 -$" 2>/dev/null); do
              readlink "/proc/$p/cwd" 2>/dev/null | grep -q cobot3 && echo "$p"
            done | tr '\n' ' ')
    if [ -n "$stale" ]; then
        echo "[cobot3-clear] stale URDF python3 - 정리: PID $stale"
        echo "$_COBOT3_SUDO_PW" | sudo -S kill -9 $stale 2>/dev/null \
            || kill -9 $stale 2>/dev/null
    fi
    # 4) 점유 포트 해제
    local PORTS="8000 3000 8765 8766 8767"
    for port in $PORTS; do
        local holders
        holders=$(echo 'rokey1234' | sudo -S ss -ltnp 2>/dev/null \
                  | awk -v p=":$port " '$4 ~ p {print $0}' \
                  | grep -oE "pid=[0-9]+" | cut -d= -f2 | sort -u)
        if [ -n "$holders" ]; then
            echo "[cobot3-clear] 포트 :$port 점유 PID($holders) 강제 정리"
            echo 'rokey1234' | sudo -S kill -9 $holders 2>/dev/null || true
        fi
    done
    # 5) Lichtblick docker (있으면 제거)
    if command -v docker >/dev/null 2>&1; then
        echo 'rokey1234' | sudo -S docker rm -f cobot3-lichtblick >/dev/null 2>&1 \
            && echo "[cobot3-clear] Lichtblick 컨테이너 제거" || true
    fi
    # 6) 최종 검증
    sleep 1
    local left
    left=$(pgrep -f "$PAT" 2>/dev/null | wc -l)
    echo "[cobot3-clear] ===== 완료 (최종 잔존 ${left}개) ====="
    if [ "$left" -gt 0 ]; then
        echo "[cobot3-clear] ⚠ 잔존 프로세스:"
        pgrep -af "$PAT" 2>/dev/null | head -10
    fi
}
alias cobot3-clean='cobot3-clear'  # 흔한 오타/유사 명령 보조

# cobot3-restart_all — clear → start_all 순차 (2026-05-21).
# WHY: 시연 중 코드/씬 변경 후 빠른 재기동. cobot3-clear 결과의 잔존이 있어도
# start_all 의 자체 cleanup 이 이중 보호 (선요청 시 잔존 PID 표시 후 진행).
# 인자 'mcp' 전달 시 with_mcp 변형 사용.
cobot3-restart_all() {
    local mode="${1:-gui}"   # gui | mcp
    echo "[cobot3-restart] 1/2 cobot3-clear ..."
    cobot3-clear
    echo "[cobot3-restart] 2/2 cobot3-start_all (mode=$mode) ..."
    if [ "$mode" = "mcp" ]; then
        cobot3-start_all-with_mcp
    else
        cobot3-start_all
    fi
}

# Isaac Sim python — 설치 경로가 다르면 수정 필요
alias isaac-python='~/dev_ws/isaac_sim/isaacsim/_build/linux-x86_64/release/python.sh'
