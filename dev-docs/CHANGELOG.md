# CHANGELOG

이 파일은 cobot3 시스템의 주요 변경사항을 날짜 역순으로 기록합니다.
각 항목에는 변경된 파일, 변경 내용, 영향을 받는 컴포넌트를 기술합니다.

---

## 2026-05-19

### Next.js API 호스트 고정 버그 수정 (SSR freeze)

**변경 파일:** `sub1_side/web/lib/api.ts` (수정)
- **원인:** `API_BASE = process.env.NEXT_PUBLIC_C2_API || "http://localhost:8000"` 가 모듈 레벨 상수로 선언 → Next.js SSR 시점(window 없음)에 `"http://localhost:8000"` 으로 고정됨
- **수정:** `getApiBase()` 런타임 함수로 교체 (`window.location.hostname` 기반, `"use client"` 보장)
- **효과:** 브라우저에서 C2 PC IP(192.168.10.105:8000)로 올바르게 요청

**변경 파일:** `sub1_side/web/components/VideoWall.tsx` (수정)
- `import { API_BASE }` → `import { getApiBase }` 로 교체
- WebRTC offer URL, MJPEG src, HUD 레이블 등 4곳 `API_BASE` → `getApiBase()` 치환

### WebSocket /events 연결 오류 수정 (uvicorn websockets 라이브러리 누락)

**변경 파일:** `sub1_side/server/.venv` (재생성)
- **원인:** `uvicorn` 단독 설치 → WebSocket 지원 라이브러리(`websockets`/`wsproto`) 없음 → `WARNING: No supported WebSocket library detected` → WS 연결 404
- **수정:** `pip install "uvicorn[standard]" websockets` (C2 PC .venv에 적용)
- **참고:** 이후 rsync는 반드시 `--exclude='.venv'` 사용 (venv shebang 경로 사용자별 상이)

### CORS 차단 수정

**변경 파일:** `sub1_side/server/config.py` (수정)
- `C2_WEB_ORIGINS` 미설정 시 `["*"]` (LAN 전체 허용) — 개발 모드 기본값
- 기존: 고정 `localhost:3000` 목록 → C2 IP(192.168.10.105:3000) 차단

### Three.js Object.assign 버그 수정

**변경 파일:** `sub1_side/web/components/SpotSurroundView.tsx` (수정)
- **원인:** `Object.assign(new THREE.DirectionalLight(...), { position: new THREE.Vector3(...) })` → Three.js `Object3D.position` 은 non-replaceable `Vector3` 인스턴스, `Object.assign` 으로 교체 불가
- **수정:** `const blueLight = new THREE.DirectionalLight(0x0044cc, 0.4); blueLight.position.set(-4, 2, -4);`

---

## 2026-05-18

### debug 페이지 Three.js 3D 패널 추가
**변경 파일:** `sub1_side/web/components/SpotSurroundView.tsx` (신규),
              `sub1_side/web/app/debug/page.tsx` (수정)
- Three.js 3D 시각화 패널을 debug 페이지 상단에 추가 (height 280px)
- 로봇 바디 (주황색 박스 + 4다리), 전방 75° FOV 황색 frustum, 후방 75° FOV 청록 frustum,
  2.5m 녹색 커버리지 링 시각화
- 마우스 드래그 시점 회전 (spherical coords), 스크롤 줌
- `/robots/gp0/state` 200ms 폴링으로 odom yaw 실시간 반영 → robotGroup.rotation.y
- `import type * as THREE` 패턴으로 TypeScript 타입 안전 + SSR 안전 동시 달성

**변경 파일:** `sub1_side/server/ros_bridge.py` (수정)
- `_on_odom()` quaternion → yaw 변환 추가 (`math.atan2` 공식)
- `latest["odom"]`에 `"yaw"` 필드 추가: `{"x":…,"y":…,"z":…,"yaw":…}`

**변경 파일:** `sub1_side/server/app.py` (수정)
- `GET /robots/{rid}/state` 응답에서 잔재 `arm_q` 키 제거 (KeyError 방지)

**변경 파일:** `sub1_side/web/package.json` (수정)
- `three@^0.184.0`, `@types/three@^0.184.1` 의존성 추가

### 개발문서 체계 구축
**변경 파일:** `dev-docs/README.md`, `architecture.md`, `main-side.md`, `sub1-side.md`,
              `ros2-interface.md`, `ops.md`, `CHANGELOG.md` (신규)
**변경 파일:** `CLAUDE.md` (프로젝트 루트, 신규)
- main_side·sub1_side 전체 아키텍처/기능/통신 문서화
- source→doc 매핑 + CLAUDE.md로 코드 변경 시 자동 문서 갱신 체계 수립

---

## 2026-05-17

### spot_with_arm → spot 전환 + 2-카메라 시스템

**변경 파일:** `main_side/camera_publisher.py` (수정)
- 로봇 교체: spot_with_arm → spot (팔 없음, 12-DOF 다리만)
- 카메라 변경: 손목 카메라 1개 → 기체 전/후방 카메라 2개
- OmniGraph: 단일 카메라 노드 → RPFront/CamFront + RPRear/CamRear 이중 파이프라인
- ArmJS (arm joint states 발행) 제거
- 상수 변경: `CAM_PATH` → `CAM_FRONT_PATH` + `CAM_REAR_PATH`

**변경 파일:** `main_side/spot_controller.py` (수정)
- arm 관련 코드 전면 제거 (_STOW, _AIM, arm_idx, _patch_arm_gains, trigger_fire, set_speaker)
- 12-DOF 단순화: `_forward()` 순수 RL 정책 적용
- `initialize(set_gains=True, set_limits=True)`

**변경 파일:** `main_side/spot_isaac.urdf` (수정)
- arm0_* 링크 7개 + 관절 7개 제거
- 13링크(base+12다리), 12관절(3/다리×4)

**변경 파일:** `main_side/video_degrade_node.py` (수정)
- 하드코딩 토픽 → 환경변수 (`DEGRADE_IN`, `DEGRADE_OUT`)

**변경 파일:** `main_side/run_degrade.sh` (수정)
- 단일 인스턴스 → front/rear 2인스턴스 병렬 실행

**변경 파일:** `sub1_side/server/config.py` (수정)
- `arm_joint` 토픽 제거, `video` 단일 → `video_front` + `video_rear` 이중

**변경 파일:** `sub1_side/server/ros_bridge.py` (수정)
- arm_q 구독/저장 제거
- 단일 video → front/rear 이중 구독

**변경 파일:** `sub1_side/lichtblick/layout.json` (수정)
- Plot!arm 패널 제거
- Image!cam 단일 → Image!cam_front + Image!cam_rear 이중

---

## 2026-05-15

### isaac-sim-mcp 타임아웃 수정

**변경 파일:** `/home/rokey/dev_ws/isaac-sim-mcp/isaac_mcp/server.py` (수정)
- 연결 타임아웃 추가 (5초): `sock.settimeout(5.0)` before `connect()`
- 수신 타임아웃 단축 (300s → 60s): 무한 로딩 방지

---

## 2026-05-14 (이전)

### Spot 기반 시스템 전환 및 기반 구축
- ANYmal-C + m0609 2-아티큘레이션 → spot_with_arm 단일 아티큘레이션
- OmniGraph 기반 ROS2 브리지 구축 (render=True 필수 발견)
- FastDDS UDP-only 설정으로 Isaac↔System ROS2 크로스호스트 통신 해결
- C2 web_server FastAPI + Next.js 전술 콘솔 구축
- Lichtblick Foxglove 3D 시각화 구성
- PostgreSQL 텔레메트리 저장 체계 구축
