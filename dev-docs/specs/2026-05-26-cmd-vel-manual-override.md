# Manual cmd_vel Override Mux — Design Spec

**Date**: 2026-05-26
**Files**: `cmd_vel_safety_filter.py` (확장), `sub1_side/server/config.py`,
`sub1_side/server/ros_bridge.py`
**Goal**: ROUTING/PATROL 진행 중 manual joystick/방향키 cmd 가 ~1s 우선되도록
time-based mux. 별도 노드 신설 없이 기존 safety_filter 안에서 통합.

## Why

`/robot/cmd_vel` 단일 topic 에 Nav2 chain (safety_filter ~20Hz) + C2 manual
publish 둘 다 → last-msg-wins race → manual 1 tick 적용 후 ~50ms 안에 nav cmd
가 덮어씀. 사용자 체감 "무시됨".

## Architecture

```
Nav2 → /cmd_vel_nav → smoother → /cmd_vel_nav2_raw ─┐
                                                    ├─→ cmd_vel_safety_filter ─→ /robot/cmd_vel ─→ OG
C2 web manual ──────────────→ /robot/cmd_vel_manual ─┘                                  ↑
                                                                                    last_manual_ts
                                                                                    mux: manual<1s = manual 우선
```

## Components

### 1. `cmd_vel_safety_filter.py` 확장

- 새 subscription: `/robot/cmd_vel_manual` (RELIABLE, depth 10)
- 새 상태: `self._last_manual_ts: float = 0.0`
- 새 상태: `self._last_manual_twist: Twist = Twist()`
- 새 파라미터: `manual_override_s = 1.0` (manual 우선 지속)
- 콜백 `_on_manual_cmd(twist)`:
  - `self._last_manual_twist = twist`
  - `self._last_manual_ts = time.monotonic()`
  - 즉시 `_publish(twist)` 호출 (50ms 기다리지 않음)
- 기존 `_on_nav_raw(twist)` 콜백 시작에:
  ```python
  if time.monotonic() - self._last_manual_ts < self._manual_override_s:
      return  # manual 우선 — nav cmd skip
  ```
- 출력은 그대로 `/robot/cmd_vel` (변경 없음)

### 2. C2 `config.py`

```python
TOPICS = {
    ...
    "cmd_vel":          "/robot/cmd_vel",          # 최종 출구 (safety_filter 발행)
    "cmd_vel_manual":   "/robot/cmd_vel_manual",   # C2 manual override 입력
    ...
}
```

### 3. C2 `ros_bridge.py`

- `_cmd_pub` 의 topic 을 `T["cmd_vel"]` → `T["cmd_vel_manual"]` 로 변경
- 기존 `pub_cmd_vel` 메서드 시그니처 유지 — C2 web/DualSense 코드 변경 없음

## Data Flow

```
manual (50Hz)
  └→ /robot/cmd_vel_manual
       └→ safety_filter._on_manual_cmd
            ├─ last_manual_ts ← now
            └─ publish → /robot/cmd_vel  (즉시)

nav_raw (~20Hz)
  └→ /cmd_vel_nav2_raw
       └→ safety_filter._on_nav_raw
            ├─ if now - last_manual_ts < 1.0: return  ← skip
            └─ publish → /robot/cmd_vel
```

## Edge Cases

- **manual stream 끊기면**: 1s 후 자동 nav cmd 재개 → 사용자가 손 떼면 자연
  ROUTING 복귀
- **manual=Twist(0)**: 명시적 정지 cmd 도 1s 동안 nav 차단 → 의도된 "잠시 멈춤"
  동작
- **PAUSED 모드**: 기존 `ros_bridge.pub_cmd_vel` 의 PAUSED 차단 그대로 — manual
  도 보내지 않으니 safety_filter 도 publish 안 함
- **fall recover stop_burst**: nav2_patrol `_publish_stop` 도 `/robot/cmd_vel`
  직접 → 변경 영향 없음 (safety_filter 우회). manual override 와 무관

## Test Plan

| 시나리오 | 기대 |
|---|---|
| ROUTING 중 정지 (manual 없음) | Nav2 cmd 그대로 — 변화 없음 |
| ROUTING 중 manual 직진 1초 | manual 직진 1초 → 손 떼면 nav 복귀 |
| ROUTING 중 manual 우회전 5초 | 5초 전부 manual — 마지막 manual cmd 가 1s 까지 우선 |
| manual cmd 정확 1.0s 후 nav 복귀 | 1.0s 직후 nav cmd 재개 (~50ms 지연) |

## Files Modified

| 파일 | 변경 |
|------|------|
| `main_side/cmd_vel_safety_filter.py` | manual sub + mux 로직 (~20줄) |
| `sub1_side/server/config.py` | TOPICS 에 cmd_vel_manual 추가 (1줄) |
| `sub1_side/server/ros_bridge.py` | _cmd_pub topic 변경 (1줄) |
| `dev-docs/CHANGELOG.md` | 항목 추가 |

총 ~25줄.
