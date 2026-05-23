# cobot3 — Claude Code 지시문

## 코드 변경 시 문서 자동 갱신 규칙

**이 프로젝트에서 파일을 수정할 때마다, 아래 매핑에 따라 해당 dev-docs 섹션도 함께 갱신한다.**
변경이 작으면(1줄 수정) 해당 섹션의 값·경로·설명만 업데이트.
변경이 크면(기능 추가/삭제) `dev-docs/CHANGELOG.md` 상단에 새 항목 추가.

---

## source → doc 매핑

| 수정한 파일 | 갱신해야 할 dev-docs 섹션 |
|------------|------------------------|
| `main_side/camera_publisher.py` | `main-side.md` § camera_publisher.py (상수·OG 구조·카메라 배치) |
| `main_side/spot_controller.py` | `main-side.md` § spot_controller.py (메서드 표·DOF 레이아웃·중재 로직) |
| `main_side/telemetry_bridge_node.py` | `main-side.md` § telemetry_bridge_node.py, `ros2-interface.md` § 토픽 목록 |
| `main_side/video_degrade_node.py` | `main-side.md` § video_degrade_node.py |
| `main_side/run_degrade.sh` | `ops.md` § 기동 순서, `main-side.md` § video_degrade 인스턴스 표 |
| `main_side/spot_isaac.urdf` | `main-side.md` § 씬 구조 (링크·관절 수) |
| `main_side/scene/gp_scene.usd` | `main-side.md` § 씬 구조 |
| `main_side/fastdds_*.xml` | `ros2-interface.md` § FastDDS 설정, `ops.md` § 환경변수 |
| `sub1_side/server/app.py` | `sub1-side.md` § FastAPI REST 엔드포인트 |
| `sub1_side/server/config.py` | `sub1-side.md` § ros_bridge.py 구독/발행 표, `ros2-interface.md` § 토픽 목록 |
| `sub1_side/server/ros_bridge.py` | `sub1-side.md` § ros_bridge.py (구독·발행·헬스 타이머) |
| `sub1_side/server/db_writer.py` | `sub1-side.md` § db_writer.py |
| `sub1_side/web/app/page.tsx` | `sub1-side.md` § Next.js 컴포넌트 § 메인 페이지 |
| `sub1_side/web/app/debug/page.tsx` | `sub1-side.md` § Next.js 컴포넌트 § 디버그 페이지 |
| `sub1_side/web/components/*.tsx` | `sub1-side.md` § Next.js 컴포넌트 표 |
| `sub1_side/web/lib/api.ts` | `sub1-side.md` § API 클라이언트 |
| `sub1_side/lichtblick/layout.json` | `sub1-side.md` § Lichtblick 레이아웃 |
| `common/site.env` | `architecture.md` § 2-PC 토폴로지 (IP 주소) |
| 포트·서비스 변경 | `architecture.md` § 포트 맵 |
| 토픽명·타입·QoS 변경 | `ros2-interface.md` § 토픽 목록 전체 |
| 환경변수 추가/변경 | `ops.md` § 환경변수 완전 목록 |
| 트러블슈팅 새 발견 | `ops.md` § 트러블슈팅 표 |

---

## CHANGELOG 갱신 기준

다음 중 하나에 해당하면 `dev-docs/CHANGELOG.md` 상단에 새 항목 추가:
- 새 ROS2 토픽/서비스 추가 또는 삭제
- 새 컴포넌트·페이지 추가
- API 엔드포인트 추가/변경/삭제
- 로봇 모델 또는 씬 교체
- DB 스키마 변경
- 2개 이상 파일을 동시에 수정하는 기능 변경

**CHANGELOG 항목 형식:**
```
## YYYY-MM-DD

### 변경사항 제목
**변경 파일:** `파일명` (신규|수정|삭제)
- 변경 내용 (무엇이, 왜)
```

---

## 에셋 배치 규칙

**git-ignore 대상인 대용량 바이너리는 반드시 `main_side/scene/` 하위에 위치해야 한다.**

- USD/USDZ/DAE/`.pt`/`.jit`/`.pgm` 등 대용량 파일 → `main_side/scene/` 전용
- `main_side/` 루트에 에셋 전용 폴더 신설 금지 (ex. `main_side/go2_unitree/` ← 금지)
- `.gitignore` 패턴 추가 시 반드시 `main_side/scene/<경로>` 형태 준수
- `scene/` 전체는 Google Drive 아카이브로 팀 공유 (`scripts/scene_pack.sh` / `scripts/scene_pull.sh`)
  - 코드·설정·USDA 텍스트 파일은 git 추적 대상 (scene/ 안에 있어도 동일)
  - 대용량 바이너리만 Google Drive 경유 (git LFS 미사용)

## 개발 규칙 (전역)

- sudo 비밀번호: `rokey1234` — `echo 'rokey1234' | sudo -S <cmd>`
- 폴더 구조 단순 유지: 3단계 이상 중첩 신설 금지
- 임시방편 우회 금지: 근본 원인 해결
- 변경 시 영향도 grep 스캔 필수
- 코드 주석: WHY만 (WHAT은 코드가 설명함)
