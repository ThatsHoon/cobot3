# legacy_scenes — 아카이브 (구 `cobot3/scenes/` 모듈)

> 이 폴더 전체는 **현행 GP 파이프라인에서 미사용**이다. 이력·참고용 보존
> 으로만 두며 코드/기동 경로에서 import 되지 않는다.
> 권위 설계: [`../gp-quadruped-system-design.md`](../gp-quadruped-system-design.md)
> · 환경/기동: [`../project_requirments.md`](../project_requirments.md)

## 왜 아카이브됐나

`scenes/` 는 **MCP/대화형 씬 조립 단계**의 단계별 idempotent 씬-빌드
헬퍼 모듈이었다(`from scenes import ...` 또는 `python.sh -m scenes.xxx`).
현행 검증 파이프라인 `main_side/camera_publisher.py` 는 **저장된 씬 USD
(`GP_SCENE`, 기본 `src/doosan-robot2/.../cobot3_1.usd` — scenes/ 외부 산출)
를 `open_stage` 로 열고 카메라·OG·Articulation 을 인라인 구성**한다.
즉 `scenes/` 모듈을 전혀 참조하지 않으므로 루트에서 제거하고 여기로 옮겼다
(CLAUDE.md 단순 폴더 구조 — 미사용 디렉토리 평탄화).

## 파일별 내역

### 워크하우스 M1/M2 시절 (창고 분류 conveyor+bins+m0609×4 스코프, GP 무관)
| 파일 | 용도(레거시) | 현행 대체 |
|---|---|---|
| `build_m1.py` | M1 오케스트레이터(conveyor+bins+r0+spawn) | GP 는 `main_side/camera_publisher.py` 가 씬 구성 |
| `build_og_factory.py` | r0~r3 멀티로봇 OG(joint/tf) | GP 단일로봇 OG = camera_publisher 내 fresh OG |
| `setup_conveyor.py` | 키네매틱 벨트 | GP 미사용 |
| `setup_bins.py` | 분류 bin 3종 | GP 미사용 |
| `setup_robot_r0.py` | `/World/Robots/r0/m0609` 배치 | GP prim 규약 `/World/Robot/m0609` 상이 |
| `setup_spawn_box.py` | 테스트 박스 스폰 | GP 미사용 |
| `setup_cameras.py` | 오버헤드 카메라 | GP = m0609 `link_6` 플랜지 RealSense |

### 구 "현행 유지" 였으나 GP 파이프라인 미참조로 함께 아카이브
| 파일 | 비고 |
|---|---|
| `__init__.py` | 모듈 호출법 docstring(경로는 구 `cobot3/scenes` 기준 — 참고용) |
| `setup_ground_and_physics.py` | PhysicsScene+GroundPlane idempotent 빌더. GP 는 저장된 USD 에 물리 포함 → 미사용. 향후 코드로 씬 재생성 시 참고 레시피 |

## 복구가 필요하면

MCP 로 씬을 코드 재조립하려면 이 디렉토리를 `cobot3/scenes/` 로 되돌리고
(`git mv dev-docs/legacy_scenes scenes`) `__init__.py` 의 경로 주석을
복원한 뒤 `python.sh -m scenes.<모듈>` 으로 호출. 단 현행 GP 는 저장된
USD + camera_publisher 인라인 구성이 정공이다.
