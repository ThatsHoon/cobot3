# 씬 sublayer 가이드 — `gp_scene_overrides.usda`

`gp_scene.usd` 를 미수정 상태로 보존하면서 collider / material binding / mass / 활성 상태를 보강하는 USDA sublayer 사용법.

## 단일 소스 원칙

| 레이어 | 책임 | 편집 도구 |
|---|---|---|
| `main_side/scene/gp_scene.usd` | 씬 단일 소스 (Isaac Sim GUI 수동 저작·저장) | Isaac Sim GUI |
| `main_side/scene/overrides/gp_scene_overrides.usda` | 코드 추적 가능한 물리/활성 보강 | 에디터 (USDA 텍스트) |
| `main_side/camera_publisher.py` (런타임) | sublayer 가 못 다루는 leaf-Mesh CollisionAPI + 보강 fallback | Python |

원칙: **gp_scene.usd 는 GUI 저장본 = latest**. 코드 변경은 sublayer 로 격리해 사용자의 수동 저장과 충돌하지 않도록 한다.

## 로딩 메커니즘

`camera_publisher.py` 가 stage open 직후 다음을 수행:

```python
_rl = stage.GetRootLayer()
_rl_dir = os.path.dirname(_rl.realPath)
_rel = os.path.relpath(_OVERRIDES_USD, _rl_dir)
_rl.subLayerPaths.insert(0, _rel)   # 가장 강한 opinion
```

- **삽입 위치 0**: USD 의 sublayer index 가 낮을수록 강한 opinion → overrides 가 base 의 누락된 attribute 를 채움
- **상대 경로**: root layer 디렉토리 기준 — 씬 이식성 유지
- **`GP_USE_OVERRIDES=0`** env 로 비활성화 가능 (디버그 / 롤백)
- **파일 부재 시**: skip 로그 + runtime safety-net 만 동작

## 현재 적용된 override 표

| Prim | 변경 항목 | 값 | 이유 |
|---|---|---|---|
| `/World/Cube` | `active` | `false` | 정찰선 밖 의문 prim, 시연 영역 무관 |
| `/World/Go2_starting_point` | `physics:collisionEnabled` | `false` | scale 0.01 시각 마커, 충돌 불필요 |
| `/World/militarybase` | `physics:collisionEnabled` | `false` | scale 0.1 시각 마커 |
| `/World/radar_tower` | `physics:collisionEnabled` | `false` | 시각 마커 |
| `/World/Watchtowers` | `apiSchemas += MaterialBindingAPI` | — | leaf Mesh binding 을 runtime 이 처리 가능하게 schema 사전 적용 |
| `/World/Fence` | 동일 | — | 동일 |
| `/World/Doro` | 동일 | — | 동일 |
| `/World/spike_ball` | `physics:collisionEnabled`, `physics:mass`, schemas | `true`, `2.0`, CollisionAPI + MassAPI + MaterialBindingAPI | 동적 장애물 — rigidBody 는 base 에 있고 collision/mass 보강 |
| `/World/banana_obstacle` | 동일 | `true`, `0.3` | 동적 (가벼움) |
| `/World/Landmine` | 동일 | `true`, `1.0` | 동적 |

> Note — Cube 의 `active=false` 는 sublayer **와** gp_scene.usd 양쪽에 적용됨 (감사 도중 1회 직접 저장). sublayer 비활성화 시에도 gp_scene.usd 만으로 Cube 비활성 유지.

## leaf-Mesh CollisionAPI 정책 (runtime safety-net)

sublayer 는 자식 mesh 경로를 미리 열거하기 어려워, leaf Mesh 에는 `camera_publisher.py:380-434` 의 safety-net 이 적용:

| Prim 분류 | approximation | 이유 |
|---|---|---|
| **동적** (spike_ball / banana_obstacle / Landmine) | `convexHull` | PhysX 가 dynamic rigidBody 에 trimesh-none 금지 |
| **정적** (Watchtowers / Fence / Doro) | `none` (trimesh) | 정적 props 는 정확 mesh collision 가능 |
| **시각 마커** (Go2_starting_point / militarybase / radar_tower) | 적용 안 함 | sublayer 가 root 에서 collisionEnabled=false |

binding 은 Terrain 내부의 `physics_material` (dynFric=0.8, statFric=0.8) 을 leaf Mesh 마다 `weakerThanDescendants` 로 적용.

## 새 항목 추가 절차 (4-step)

1. **백업 — 항상 먼저**

   ```bash
   cp gp_scene_overrides.usda gp_scene_overrides.usda.bak.$(date +%Y%m%d_%H%M%S)
   ```

2. **`over` 블록 추가** — `over "<prim_name>" ( apiSchemas = [...] ) { ... }` 형식 그대로

3. **offline composition 검증** (라이브 stage 안 건드림):

   ```bash
   python3 -c "
   from pxr import Usd, Sdf
   anon = Sdf.Layer.CreateAnonymous('.usda')
   anon.subLayerPaths.insert(0, '/home/rokey/dev_ws/isaac_sim/cobot3/main_side/scene/overrides/gp_scene_overrides.usda')
   anon.subLayerPaths.insert(1, '/home/rokey/dev_ws/isaac_sim/cobot3/main_side/scene/gp_scene.usd')
   stage = Usd.Stage.Open(anon)
   print(stage.GetPrimAtPath('/World/<your_prim>').GetAppliedSchemas())
   "
   ```

4. **시연 직전 라이브 검증** — `cobot3-start_all` 후 MCP `execute_script` 로 composed state 확인 (live stage `subLayerPaths.insert()` 호출 금지 — full recomposition 으로 kit thread 행 위험)

## 롤백

| 상황 | 방법 | 효과 |
|---|---|---|
| 일시적 비활성화 | `export GP_USE_OVERRIDES=0` 후 재기동 | sublayer 미로드, safety-net 만 동작 |
| 영구 비활성화 | `gp_scene_overrides.usda` 삭제/이름변경 | `os.path.isfile` 가드 skip |
| 코드 자체 제거 | `camera_publisher.py` 의 sublayer 블록 1 hunk 제거 (~12줄) | safety-net 호환 |
| Cube 활성 복원 | gp_scene.usd backup 복원 (`gp_scene.usd.bak.20260521_173334`) | Cube 복원 + 다른 변경 없음 |

## 알려진 제약

- **라이브 stage 에 sublayer 동적 prepend 금지**: 27 MB binary USDC + 3478 mesh + 실행 중 OG/Physics 일 때 `subLayerPaths.insert()` 가 full recomposition 트리거 → main thread 락 → MCP 응답 불가 (2026-05-21 라이브 실측). 항상 stage open 시점에 prepend.
- **`physics:mass` float 정밀도**: 0.3 → 0.30000001192092896 (USD double 변환). 시뮬 영향 없음.
- **PrimStack 검증**: instancing 되는 prim 에 over 를 걸면 prototype 쪽에 적용되지 않을 수 있음. 향후 instancing 도입 시 prototype 경로로 직접 over.
