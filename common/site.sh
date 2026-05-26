#!/usr/bin/env bash
# cobot3 사이트 IP 파생 헬퍼 — site.env(SSOT) 하나로 양측 설정 자동 수식.
# 사용: source 후 cobot3_site_load → $MAIN_SIDE_IP/$SUB1_SIDE_IP,
#       cobot3_c2_ingest_url, cobot3_fastdds_profile <main|web>.
# 멱등. site.env 없거나 값 누락이면 비치명(빈값 → 호출측이 폴백).
# 주의: 사용자 셸이 grep/sed 를 함수/별칭으로 덮을 수 있어 외부명령은
#       전부 `command` 로 우회하고, env 파싱은 순수 bash 로만 한다.

_COBOT3_COMMON="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_COBOT3_ROOT="$(cd "$_COBOT3_COMMON/.." && pwd)"

cobot3_site_load() {           # site.env 의 KEY=VALUE 만 순수 bash 로 추출
    local f="${COBOT3_SITE_ENV:-$_COBOT3_COMMON/site.env}" line k v
    [ -f "$f" ] || { echo "[site] $f 없음" >&2; return 1; }
    while IFS= read -r line || [ -n "$line" ]; do
        line="${line%%#*}"                       # 주석 제거
        [[ "$line" == *=* ]] || continue
        k="${line%%=*}"; v="${line#*=}"
        k="${k//[[:space:]]/}"; v="${v//[[:space:]]/}"
        case "$k" in
            MAIN_SIDE_IP|SUB1_SIDE_IP|PUBLIC_HOST|C2_YOLO_CAMERAS) [ -n "$v" ] && export "$k=$v" ;;
        esac
    done < "$f"
    # 성공 기준은 IP 2종만(PUBLIC_HOST 는 선택 — 미사용 배포 허용).
    [ -n "$MAIN_SIDE_IP" ] && [ -n "$SUB1_SIDE_IP" ]
}

cobot3_public_url() {          # C2 공개 호스팅 URL (Cloudflare). 미설정 시 1
    cobot3_site_load
    [ -n "$PUBLIC_HOST" ] || { echo "[site] PUBLIC_HOST 미설정" >&2; return 1; }
    echo "https://${PUBLIC_HOST}"
}

cobot3_c2_ingest_url() {       # D-확장 업링크 대상 (C2 web_server)
    cobot3_site_load || return 1
    echo "http://${SUB1_SIDE_IP}:8000"
}

# placeholder 템플릿 → 치환본(~/.config/cobot3/) 재생성, 경로를 stdout 으로.
#   main → main_side/fastdds_main.xml(__C2_PC_IP__/__MAIN_LAN_IP__)
#   web  → sub1_side/fastdds_web.xml(__MAIN_PC_IP__/__C2_LAN_IP__)
cobot3_fastdds_profile() {
    cobot3_site_load || return 1
    local side="$1" tmpl out
    local cfg="$HOME/.config/cobot3"; mkdir -p "$cfg"
    case "$side" in
        main) tmpl="$_COBOT3_ROOT/main_side/fastdds_main.xml"; out="$cfg/fastdds_main.xml"
              command sed "s/__C2_PC_IP__/$SUB1_SIDE_IP/; s/__MAIN_LAN_IP__/$MAIN_SIDE_IP/" "$tmpl" > "$out" ;;
        web)  tmpl="$_COBOT3_ROOT/sub1_side/fastdds_web.xml"; out="$cfg/fastdds_web.xml"
              command sed "s/__MAIN_PC_IP__/$MAIN_SIDE_IP/; s/__C2_LAN_IP__/$SUB1_SIDE_IP/" "$tmpl" > "$out" ;;
        *) echo "[site] cobot3_fastdds_profile: side=main|web" >&2; return 1 ;;
    esac
    # placeholder 잔존 없으면 경로 반환(순수 bash 검사 — grep 비의존)
    [ -s "$out" ] || return 1
    local c; c="$(<"$out")"; [[ "$c" == *__* ]] && return 1
    echo "$out"
}
