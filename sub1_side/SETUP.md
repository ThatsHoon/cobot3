# sub1_side(C2 PC) 초기 설정 & 기동 가이드

C2 PC(웹·브리지·DB 전담)에서 **한 명령으로 전체 스택을 올리고 내리기** 위한
`cobot3-sub1side-start_all` / `cobot3-sub1side-down_all` 설정 가이드.

---

## 1. 전제 — 1회 설치 (C2 PC)

```bash
# ROS 2 Humble (/opt/ros/humble 존재 전제)
sudo apt-get install -y \
  ros-humble-foxglove-bridge \
  docker.io postgresql \
  python3-venv python3-pip \
  nodejs npm sshpass

# docker 그룹 추가 후 재로그인
sudo usermod -aG docker "$USER"
```

---

## 2. 리포 복제 & IP 단일소스(SSOT)

```bash
git clone https://github.com/ThatsHoon/cobot3.git ~/dev_ws/isaac_sim/cobot3
cd ~/dev_ws/isaac_sim/cobot3

# common/site.env 수정 — 이 배포 실제 IP 로
nano common/site.env
#   MAIN_SIDE_IP=<Isaac PC LAN IP>
#   SUB1_SIDE_IP=<이 C2 PC LAN IP>
ip -4 addr show   # SUB1_SIDE_IP 확인 (docker0/wlan 제외, 실 NIC)
```

---

## 3. 서버 venv / 웹 / DB

```bash
# 서버 가상환경
cd ~/dev_ws/isaac_sim/cobot3/sub1_side/server
python3 -m venv --system-site-packages .venv
./.venv/bin/pip install -r requirements.txt

# 웹 의존성
cd ../web && npm install

# FastDDS 프로파일 생성 (site.env IP 치환)
source ~/dev_ws/isaac_sim/cobot3/common/site.sh
cobot3_fastdds_profile web   # → ~/.config/cobot3/fastdds_web.xml

# DB 스키마 (멱등 — 재실행 안전)
createdb cobot3 2>/dev/null || true
psql -d cobot3 -f ~/dev_ws/isaac_sim/cobot3/sub1_side/db/schema.sql
```

---

## 4. 웹 환경변수 설정

`sub1_side/web/.env.local` 파일 생성:

```bash
cat > ~/dev_ws/isaac_sim/cobot3/sub1_side/web/.env.local <<'EOF'
# LAN 직결 (C2 PC 에서 브라우저 띄울 때)
NEXT_PUBLIC_C2_API=http://localhost:8000
NEXT_PUBLIC_GP_ROBOT=gp0
NEXT_PUBLIC_LICHTBLICK_URL=http://localhost:8080
EOF
# 공개 Cloudflare 호스팅 시: NEXT_PUBLIC_C2_API=https://<PUBLIC_HOST>
```

---

## 5. `~/.bashrc` 에 기동/종료 함수 추가

아래 블록을 C2 PC 의 `~/.bashrc` 맨 끝에 붙여넣기.

**`YOUR_SUDO_PW` 를 이 PC 의 실제 sudo 비밀번호로 교체할 것.**

```bash
# ══════════════════════════════════════════════════════════════════
#  cobot3 sub1_side(C2) 기동 / 종료
#  cobot3-sub1side-start_all  ── 전체 C2 스택 기동
#  cobot3-sub1side-down_all   ── 전체 C2 스택 종료
# ══════════════════════════════════════════════════════════════════
_COBOT3_SUB1="${HOME}/dev_ws/isaac_sim/cobot3/sub1_side"
_COBOT3_SUDO_PW="YOUR_SUDO_PW"   # ← 이 PC sudo 비밀번호로 교체

cobot3-sub1side-start_all() {
    local SUB1="$_COBOT3_SUB1"
    [ -d "$SUB1" ] || { echo "[cobot3] $SUB1 없음 — 리포 먼저 복제"; return 1; }

    echo "[cobot3] ===== sub1side-start_all : C2 스택 기동 ====="

    # 이전 실행 정리
    cobot3-sub1side-down_all 2>/dev/null

    # site.env 로드 (PUBLIC_HOST 판별용)
    [ -f "$SUB1/../common/site.sh" ] \
        && source "$SUB1/../common/site.sh" \
        && cobot3_site_load >/dev/null 2>&1

    # 1) PostgreSQL + 스키마
    echo "[cobot3] (1) PostgreSQL 기동 + 스키마 ..."
    echo "$_COBOT3_SUDO_PW" | sudo -S systemctl restart postgresql >/dev/null 2>&1
    sleep 1
    createdb cobot3 2>/dev/null || true
    psql -d cobot3 -f "$SUB1/db/schema.sql" >/tmp/cobot3_db.log 2>&1 \
        && echo "[cobot3]   schema OK" \
        || echo "[cobot3]   schema WARN → /tmp/cobot3_db.log"

    # FastDDS 프로파일 최신화 (IP 변경 시 자동 재생성)
    command -v cobot3_fastdds_profile >/dev/null 2>&1 \
        && cobot3_fastdds_profile web >/dev/null 2>&1 || true

    # 2) web_server :8000
    echo "[cobot3] (2) web_server :8000 기동 ..."
    ( cd "$SUB1/server" \
        && setsid bash run.sh </dev/null >/tmp/cobot3_server.log 2>&1 & )
    sleep 1

    # 3) Next.js :3000
    echo "[cobot3] (3) web :3000 기동 ..."
    ( cd "$SUB1/web" \
        && { [ -d node_modules ] || npm install >/tmp/cobot3_web_install.log 2>&1; } \
        && setsid bash -c 'npm run dev' </dev/null >/tmp/cobot3_web.log 2>&1 & )

    # 4) foxglove_bridge :8765
    echo "[cobot3] (4) foxglove_bridge :8765 기동 ..."
    ( cd "$SUB1" \
        && setsid bash run_foxglove_bridge.sh </dev/null >/tmp/cobot3_foxglove.log 2>&1 & )

    # 5) Lichtblick :8080
    echo "[cobot3] (5) Lichtblick :8080 기동 ..."
    echo "$_COBOT3_SUDO_PW" | sudo -S docker rm -f cobot3-lichtblick >/dev/null 2>&1 || true
    echo "$_COBOT3_SUDO_PW" | sudo -S docker run -d \
        --name cobot3-lichtblick --restart unless-stopped \
        -p 8080:8080 \
        -v "$SUB1/lichtblick/layout.json:/lichtblick/default-layout.json:ro" \
        ghcr.io/lichtblick-suite/lichtblick:latest \
        && echo "[cobot3]   Lichtblick OK (http://localhost:8080)" \
        || echo "[cobot3]   ⚠ Lichtblick 기동 실패 — sudo docker logs cobot3-lichtblick"

    # 6) cloudflared (PUBLIC_HOST 설정 시에만)
    if [ -n "${PUBLIC_HOST:-}" ]; then
        echo "[cobot3] (6) cloudflared ($PUBLIC_HOST) 기동 ..."
        ( cd "$SUB1" \
            && setsid bash run_cloudflared.sh </dev/null >/tmp/cobot3_cloudflared.log 2>&1 & )
    fi

    echo "[cobot3] ===== 완료 ====="
    echo "  server  : tail -f /tmp/cobot3_server.log"
    echo "  web     : tail -f /tmp/cobot3_web.log"
    echo "  foxglove: tail -f /tmp/cobot3_foxglove.log"
    echo "  UI      : http://localhost:3000  ·  /debug (Foxglove)  ·  /healthz"
    [ -n "${PUBLIC_HOST:-}" ] && echo "  공개URL : https://${PUBLIC_HOST}"
    echo ""
    echo "  ⚠ Isaac PC(${MAIN_SIDE_IP:-?}) 에서 'cobot3-start_all' 실행 필요"
}

cobot3-sub1side-down_all() {
    echo "[cobot3] ===== sub1side-down_all : C2 스택 종료 ====="

    # 웹·서버·foxglove·cloudflared 프로세스 종료
    local PAT="uvicorn app:app|sub1_side/server|next dev|next-server|foxglove_bridge|run_cloudflared|cloudflared.*cobot3"
    pkill -f "$PAT" 2>/dev/null || true
    sleep 0.5
    pkill -9 -f "$PAT" 2>/dev/null || true

    # 포트 점유 확인
    for p in 8000 3000 8765 8080; do
        fuser "$p/tcp" >/dev/null 2>&1 \
            && echo "[cobot3]   ⚠ 포트 $p 여전히 점유" \
            || echo "[cobot3]   포트 $p 해제"
    done

    # Lichtblick 컨테이너
    echo "$_COBOT3_SUDO_PW" | sudo -S docker rm -f cobot3-lichtblick >/dev/null 2>&1 \
        && echo "[cobot3]   Lichtblick 컨테이너 제거" || true

    # PostgreSQL
    echo "[cobot3] PostgreSQL 정지 ..."
    echo "$_COBOT3_SUDO_PW" | sudo -S systemctl stop postgresql >/dev/null 2>&1
    pg_isready -q 2>/dev/null \
        && echo "[cobot3]   ⚠ PostgreSQL 아직 응답" \
        || echo "[cobot3]   PostgreSQL 정지됨"

    echo "[cobot3] ===== 완료 ====="
}
# ══════════════════════════════════════════════════════════════════
```

적용:
```bash
source ~/.bashrc
```

---

## 6. 일상 사용

| 명령 | 동작 |
|------|------|
| `cobot3-sub1side-start_all` | C2 전체 스택 기동 (PG·서버·웹·Foxglove·Lichtblick) |
| `cobot3-sub1side-down_all` | C2 전체 스택 종료 |

기동 순서:

```
[C2 PC]   cobot3-sub1side-start_all
[Main PC] cobot3-start_all            # Isaac Sim + degrade + telem_bridge
```

---

## 7. 검증

```bash
# 서버 응답
curl -s http://localhost:8000/healthz   # 200 OK

# ROS2 토픽 (Main PC 발행 중일 때)
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=130 ROS_LOCALHOST_ONLY=0 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE=~/.config/cobot3/fastdds_web.xml
ros2 topic list   # /robot/odom, /c2/video/compressed 등 확인
ros2 topic hz /c2/video/compressed   # ~5 Hz

# 브라우저
# http://localhost:3000         작전 콘솔
# http://localhost:3000/debug   Foxglove(Lichtblick) 임베드
```

---

## 8. 트러블슈팅

| 증상 | 확인 |
|------|------|
| `ros2 topic list` 에 Isaac 토픽 없음 | `~/.config/cobot3/fastdds_web.xml` 의 `<address>` 가 `MAIN_SIDE_IP` 인지 확인; 변경 시 `cobot3_fastdds_profile web` 재실행 후 서버 재기동 |
| 영상이 웹에 안 뜸 | `tail -f /tmp/cobot3_server.log` → `rx.video` 수신량 확인; 0이면 Main PC `run_degrade.sh` 미기동 |
| PostgreSQL 기동 실패 | `sudo systemctl status postgresql` → 포트 5432 충돌 여부 |
| Lichtblick 기동 실패 | `sudo docker logs cobot3-lichtblick`; docker 그룹 재로그인 필요 여부 확인 |
| `cobot3_fastdds_profile: command not found` | `source ~/dev_ws/isaac_sim/cobot3/common/site.sh` 를 `~/.bashrc` 에 추가 |

---

## 9. common/site.sh 자동 로드 (권장)

`~/.bashrc` 에 아래 줄 추가 시 `cobot3_fastdds_profile` 등 공용 유틸 자동 사용 가능:

```bash
[ -f ~/dev_ws/isaac_sim/cobot3/common/site.sh ] \
    && source ~/dev_ws/isaac_sim/cobot3/common/site.sh
```
