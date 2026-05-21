# gp_scene.usd 4축 감사 (2026-05-21)

`main_side/scene/gp_scene.usd` (27 MB binary USDC) 의 **구조 정확성 · USD 효율성 · 물리법칙 구현 · 로봇·센서 통합성** 4개 측면 감사 보고서.

## 측정 환경

| 항목 | 값 |
|---|---|
| 일자 | 2026-05-21 17:30 KST |
| 도구 | `pxr.Usd` (usd-core 26.5) + `isaac-sim-mcp` execute_script |
| Isaac Sim | 5.1.0-rc.19 (PID 1652625, kit + `isaac.sim.mcp_extension`) |
| 측정 스크립트 | `/tmp/cobot3_scene_before.json`, `/tmp/cobot3_phys_mat.json`, `/tmp/cobot3_bbox.json`, `/tmp/cobot3_eff.json` |
| 백업 | `gp_scene.usd.bak.20260521_173334` (변경 직전) |

## 사실 카운트

| 항목 | BEFORE | AFTER | 비고 |
|---|---:|---:|---|
| Mesh prim | 3478 | 3478 | (Cube mesh 는 비활성, 카운트 유지) |
| Material prim | 234 | 234 | unbound 10/234 = 4% (P1 백로그) |
| Shader prim | 459 | 459 | |
| Xform prim | 7320 | 7320 | |
| CollisionAPI prim | 63 | 63 + 런타임 1729 (예상) | safety-net 가 leaf Mesh 에 적용 |
| CollisionAPI 커버리지 | 1.81% | (sublayer + safety-net 적용 후) ~50% | Fence 1650 mesh + 정적 props 79 |
| 파일 사이즈 | 26 MB | 26 MB | Cube `active=false` 만 변경 — boolean diff |

## 측면별 발견 사항

### 1. 씬 구조 정확성 (Structural Correctness)

| ID | 발견 | 영향 | 처리 | 우선순위 |
|---|---|---|---|---|
| S-1 | `default_prim=World`, `upAxis=Z`, `metersPerUnit=1` | OK — 기준 정상 | — | — |
| S-2 | `/World/Cube` @ (-718, 955, 37) — 정찰선 멀리 밖 의문의 prim | 시연 영역과 무관, 디버그 잔재 가능성 | sublayer `over "Cube" { active = false }` (안전) + gp_scene.usd 저장 | **P0** ✅ |
| S-3 | Watchtowers/Fence/Doro root translate=(0,0,0) but bbox 실제 영역 X≈200-300, Y≈850-920 | 자식 mesh 가 절대 world 좌표 보유 → 위치 OK | translate 보정 불필요 (감사 도중 정정 — 초기 plan 의 translate=(212.8, 890.53, 0) 보정안은 잘못된 진단) | — |
| S-4 | Go2_starting_point/militarybase/radar_tower scale 0.01~0.1 마커 | 시각화 전용, 물리 불필요 | sublayer 에 `physics:collisionEnabled=false` 명시 | **P0** ✅ |
| S-5 | `/World/Robot` (legacy Spot stub) | 존재 안 함 (이미 정리됨) | — | — |

### 2. USD 효율성 (Efficiency)

| ID | 발견 | 영향 | 처리 | 우선순위 |
|---|---|---|---|---|
| E-1 | Material 234개 중 unbound 10개 (~4%) | 메모리 / 파일 사이즈 미미 | 향후 라이브 확인 후 purge | **P1** 백로그 |
| E-2 | Fence 자식 mesh 1650 — 단일 prim 의 50% mesh 차지 | 시뮬레이션 부하 큼 | LOD / PointInstancer 후보 — 위험도 높아 수동 검토 | **P1** 백로그 |
| E-3 | spike_ball (33 mesh) / banana_obstacle (21) / Landmine (7) / Doro (12) — 반복 표준 객체 | instancing 후보 | prototype 분리 + `SetInstanceable(True)` 가능 — collider 가 instance 후 override 안 되므로 prototype 에 미리 적용 필요 | **P1** 백로그 |
| E-4 | `/World/Cube` (디버그) 활성 | 메모리 영향 미미 | `active=false` (sublayer + USD 저장) | **P0** ✅ |

### 3. 물리법칙 구현 (Physics)

| ID | 발견 | 영향 | 처리 | 우선순위 |
|---|---|---|---|---|
| P-1 | `/World/Physics_Materials` 컨테이너 비어 있음 — `physics_material` prim 없음 | 명시 친구 binding 타깃 부재 | runtime safety-net 가 Terrain 내부 material (dynFric=0.8) 사용 | — |
| P-2 | Terrain physics_material 실제 위치: `/World/Terrain/Meshes/Sketchfab_model/.../physics_material` (dynFric=0.8 적용) | OK — 이미 정의됨 | runtime safety-net 가 자동 발견 | — |
| P-3 | spike_ball/banana_obstacle/Landmine: `physics:rigidBodyEnabled=true` BUT `physics:collisionEnabled` 미설정 | rigidBody 활성 + collider 없음 → 동적 충돌 안 일어남 | sublayer 에 `physics:collisionEnabled=true` + `physics:mass` 명시 | **P0** ✅ |
| P-4 | leaf Mesh CollisionAPI 1.81% 커버리지 (Watchtowers/Fence/Doro/spike_ball/... 모두 누락) | Go2 가 통과 / 충돌 안 함 | runtime safety-net 가 leaf Mesh 에 CollisionAPI + MeshCollisionAPI(approximation) 적용 | **P0** ✅ |
| P-5 | safety-net 의 approximation 이 모든 prim 에 'none' (trimesh) 적용 | dynamic rigidBody 에 trimesh-none 은 PhysX 금지 → 시뮬 에러 | safety-net 분기 — dynamic prim 은 'convexHull', 정적 prim 은 'none' | **P0** ✅ |

### 4. 로봇·센서 통합성 (Integration)

| ID | 발견 | 영향 | 처리 | 우선순위 |
|---|---|---|---|---|
| I-1 | Go2 spawn 좌표 `camera_publisher.py:201` 하드코딩, `world_odom_tf_pub.py` 는 `GP_GO2_SPAWN_X/Y/Z` env | spawn 좌표 SSOT 위반 — env 변경 시 camera_publisher 가 안 따라옴 | `camera_publisher.py` 도 동일 env 읽도록 수정 | **P0** ✅ |
| I-2 | `Clock` 노드 publishRate 미설정 (Isaac 기본 ~100 Hz 추정) | Nav2 sim_time stamp 매칭 매번 다른 rate 로 동작할 위험 | publishRate=60 Hz 명시 (Nav2 controller 10 Hz 의 6× 마진) | **P0** ✅ |
| I-3 | OG TF `targetPrims=[BASE_PRIM]` (=`/World/Go2/base`) | OK — articulation 동적 pose 발행 | — | — |
| I-4 | `world_odom_tf_pub.py` 의 정적 `Go2→base` TF + nav2 `robot_base_frame=base` 정합 | OK | — | — |

## 적용된 P0 처리 요약

1. **gp_scene.usd 직접 수정** (1건): `/World/Cube` `active=false` 적용 + `save_stage()`. 백업 `gp_scene.usd.bak.20260521_173334` 보존.
2. **신규 sublayer `gp_scene_overrides.usda`**: 10개 over (Cube/9개 prim) — 동적 prim collider+mass, 시각 마커 비활성, 정적 props MaterialBindingAPI schema.
3. **`camera_publisher.py` 4건 수정**:
   - sublayer prepend 코드 (open_stage 직후, `subLayerPaths.insert(0, ...)`)
   - `_GO2_HOME_XYZ` 에 `GP_GO2_SPAWN_X/Y/Z` env 추가
   - Clock 노드 `publishRate=60.0` ← **라이브 검증 후 정정**: `ROS2PublishClock` 은 `publishRate` input 미보유. OnPlaybackTick render_dt=1/50 → 50Hz 가 발행 주기. 잘못 설정 시 `OmniGraphError: Attribute named 'inputs:publishRate' does not refer to a legal og.Attribute` → kit 종료. 코드에서 해당 줄 제거 완료.
   - safety-net 의 leaf Mesh approximation 을 dynamic/정적 분기 (convexHull/none)

## 검증

`pxr.Usd` 오프라인 composition 테스트 (라이브 stage 미사용, MCP 행 회피):
- spike_ball 의 composed state: `rb=True ce=True mass=2.0 schemas=[PhysicsCollisionAPI, PhysicsMassAPI, MaterialBindingAPI]` ✓
- banana_obstacle: `rb=True ce=True mass=0.3` ✓
- Landmine: `rb=True ce=True mass=1.0` ✓
- Go2_starting_point/militarybase/radar_tower: `ce=False` ✓
- Watchtowers/Fence/Doro: `MaterialBindingAPI` schema ✓
- /World/Cube: `active=False` ✓
- spike_ball PrimStack 최상단 = overrides 레이어 ✓

라이브 시뮬 검증은 차회 `cobot3-start_all` 재기동 시 (sublayer 로드 로그 + 6개 시나리오) 수행.

## 백로그 (P1)

| ID | 항목 | 비고 |
|---|---|---|
| E-1 | Material unbound 10개 purge | 4% 비중, 시연 후 라이브 확인 |
| E-2 | Fence 1650 mesh LOD / PointInstancer | 시연 후 / 시뮬 부하 측정 후 |
| E-3 | spike_ball/Landmine 등 instancing | prototype 분리 + collider 사전 적용 |
| P-2-1 | `/World/Physics_Materials/physics_material` 정식 정의 (현재는 Terrain 내부 material 우회 사용) | sublayer 에 새 material 정의 가능 |

## 영향도 grep

```bash
grep -rn "GP_USE_OVERRIDES\|gp_scene_overrides\|subLayerPaths.insert" \
    /home/rokey/dev_ws/isaac_sim/cobot3/
```

예상 hit: `camera_publisher.py` (3) + 본 문서 + `scene-overrides.md` + `CHANGELOG.md`. 그 외는 0 건이어야 함.
