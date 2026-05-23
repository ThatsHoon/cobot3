#!/usr/bin/env bash
# C2 공개 호스팅 — Cloudflare Tunnel 기동 (C2 PC 에서 실행).
# PUBLIC_HOST(site.env SSOT) → UI(:3000)+API(:8000) 단일오리진 노출.
# 멱등: 터널/ DNS 가 없으면 만들고, 있으면 그대로 run. CLOUDFLARE.md 참고.
set -euo pipefail
_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TUNNEL=cobot3
CF=~/.cloudflared
TMPL="$_HERE/cloudflared/config.yml"
OUT="$CF/config-$TUNNEL.yml"

# ── 사이트 SSOT 로드 (PUBLIC_HOST) ────────────────────────────────────
[ -f "$_HERE/../common/site.sh" ] && source "$_HERE/../common/site.sh"
cobot3_site_load || { echo "[cf] site.env 로드 실패"; exit 1; }
: "${PUBLIC_HOST:?[cf] site.env 에 PUBLIC_HOST 필요}"

# ── ENV 자가점검 (프로젝트 계측 규약) ─────────────────────────────────
echo "==== cloudflared 기동 점검 ===="
echo "  PUBLIC_HOST = $PUBLIC_HOST"
echo "  TUNNEL      = $TUNNEL"
echo "  ingress     = /ingest→차단 | /(healthz|robots|telemetry|events|c2)→:8000 | 그외→:3000"
command -v cloudflared >/dev/null || { echo "  ⚠ cloudflared 미설치"; exit 1; }
echo "  cloudflared = $(cloudflared --version 2>/dev/null | head -1)"
if [ ! -f "$CF/cert.pem" ]; then
  echo "  ⚠ $CF/cert.pem 없음 = Cloudflare 미인증."
  echo "    먼저 대화형 로그인 실행:  ! cloudflared tunnel login"
  exit 1
fi
echo "  auth        = cert.pem OK"
echo "==============================="

# ── 터널 멱등 보장 ───────────────────────────────────────────────────
if ! cloudflared tunnel list 2>/dev/null | command grep -qw "$TUNNEL"; then
  echo "[cf] 터널 '$TUNNEL' 신규 생성"
  cloudflared tunnel create "$TUNNEL"
else
  echo "[cf] 터널 '$TUNNEL' 기존 사용"
fi
UUID="$(cloudflared tunnel list 2>/dev/null \
        | command awk -v t="$TUNNEL" '$2==t{print $1}')"
[ -n "$UUID" ] || { echo "[cf] 터널 UUID 해석 실패"; exit 1; }
echo "[cf] UUID = $UUID"

# ── 템플릿 → 치환본 생성(repo 비오염, ~/.cloudflared/) ────────────────
command sed -e "s/__TUNNEL_UUID__/$UUID/g" \
            -e "s/__PUBLIC_HOST__/$PUBLIC_HOST/g" \
            -e "s#__CF_HOME__#$HOME#g" "$TMPL" > "$OUT"
case "$(<"$OUT")" in *__*) echo "[cf] 치환 미완(placeholder 잔존)"; exit 1 ;; esac
echo "[cf] config 생성 → $OUT"

# ── DNS 라우트 멱등 (CNAME PUBLIC_HOST → 터널) ───────────────────────
cloudflared tunnel route dns "$TUNNEL" "$PUBLIC_HOST" 2>&1 \
  | command grep -viE 'already (exists|configured)' || true
echo "[cf] DNS 라우트 보장: $PUBLIC_HOST → $TUNNEL"

# ── run (포그라운드; 상시화는 CLOUDFLARE.md §5 service install) ───────
echo "[cf] tunnel run — Ctrl+C 종료. https://$PUBLIC_HOST"
exec cloudflared tunnel --config "$OUT" run "$TUNNEL"
