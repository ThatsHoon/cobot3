# C2 공개 호스팅 — Cloudflare Tunnel (`cobot3.thatshoon.com`)

C2 PC 는 LAN 사설망(공인 IP 없음) → **Cloudflare Tunnel(named)** 로
`cobot3.thatshoon.com` 공개. UI(Next.js)+API(FastAPI)를 **단일 오리진**으로
묶어 CORS/WS 문제를 원천 제거하고, 앞단에 **Cloudflare Access** 게이트.

도메인/터널명은 `common/site.env`(SSOT) `PUBLIC_HOST` 한 곳만 본다.

## 1. 아키텍처

```
브라우저 ──TLS──► Cloudflare Edge ──[Access 게이트]──► Tunnel ──► C2 PC
  https://cobot3.thatshoon.com
   ├ /healthz /robots /telemetry /events(WS) /c2/*  → localhost:8000 (FastAPI)
   ├ /ingest                                         → 404 (LAN 전용·미라우팅)
   └ 그 외 (UI, _next, ...)                           → localhost:3000 (Next.js)
```

- `/ingest` 미라우팅: Isaac→C2 데이터 투입은 무인증이므로 공개 금지 →
  Main PC 는 LAN 직결(`http://<SUB1_SIDE_IP>:8000/ingest`) 그대로 사용.
- 단일 오리진이라 web `.env.local` = `NEXT_PUBLIC_C2_API=https://cobot3.thatshoon.com`,
  WS 는 자동으로 `wss://cobot3.thatshoon.com/events`.

## 2. 사용자 1회 작업 — Cloudflare 인증 (대화형, 자동화 불가)

```
! cloudflared tunnel login        # 브라우저에서 thatshoon.com 존 선택
```
→ `~/.cloudflared/cert.pem` 생성되면 완료. (이미 수행함.)

## 3. 사용자 1회 작업 — Access 게이트 (Zero Trust 대시보드)

경계초소 로봇 C2 라 **반드시** 설정. one-dash → Zero Trust →
Access → Applications → **Add a self-hosted application**:

- Application domain: `cobot3.thatshoon.com`
- Session 적절히(예: 24h)
- Policy: Action=Allow, Include=**Emails** 에 허용 운영자 이메일만
  (또는 Google/GitHub 등 IdP). 그 외 전원 차단.

Access 는 WS(`/events`)도 동일 세션 쿠키로 통과(같은 오리진). `/ingest`
는 터널에서 빠져 Access 와 무관(LAN 직결).

## 4. 기동

```bash
cd sub1_side
./run_cloudflared.sh        # 터널/ DNS 멱등 보장 후 foreground run
```
선행: C2 백엔드(`server/run.sh`, :8000)와 web(:3000)이 떠 있어야 실제
응답. 터널만 먼저 떠도 무방(502 반환).

web 은 공개 URL 로 빌드/기동:
```bash
cd sub1_side/web && npm run build && npm start   # .env.local 반영
```

## 5. 상시화(선택) — systemd 서비스

```bash
echo 'rokey1234' | sudo -S cloudflared service install
# 설정파일을 서비스가 보도록:
echo 'rokey1234' | sudo -S cp ~/.cloudflared/config-cobot3.yml /etc/cloudflared/config.yml
echo 'rokey1234' | sudo -S systemctl restart cloudflared
```
재배포지 변경 시 `common/site.env` `PUBLIC_HOST` 만 수정 →
`./run_cloudflared.sh` 재실행(터널 재사용, DNS 재바인딩).

## 6. 보안 요약

| 항목 | 처리 |
|---|---|
| UI/영상/텔레메트리/WS 공개 | Cloudflare Access 게이트(허용 이메일만) — §3 |
| 변경계열(fire/speaker/goto) | 기존 `ISAAC_SIM_API_KEY` 헤더 + Access 이중 |
| `/ingest`(무인증 데이터 투입) | 터널 미라우팅 → LAN 직결 전용 |
| 오리진 위장/타호스트 | ingress 4) `http_status:404` |
| TLS | Cloudflare Edge 종단(자동) |

## 7. 점검

```bash
cloudflared tunnel list                       # cobot3 + UUID
cloudflared tunnel info cobot3                 # 커넥션 상태
dig +short cobot3.thatshoon.com               # <UUID>.cfargotunnel.com CNAME
curl -I https://cobot3.thatshoon.com/healthz  # Access 미인증이면 302→로그인
```

---
관련: `../common/site.env`(PUBLIC_HOST SSOT) · `cloudflared/config.yml`(템플릿) ·
`run_cloudflared.sh` · `web/.env.local`
