# Adaptive Gait Mode — Design Spec

**Date**: 2026-05-26
**File**: `main_side/go2_controller.py` (단일 파일 변경)
**Goal**: 평탄/경사 자동 감지로 FLAT/SLOPE 두 `_CMD_BASE` 세트 자동 전환.
평탄지에선 nose-dive 완화, 경사·단차에선 더 공격적 footswing/freq.

## Why

현재 단일 `_CMD_BASE` (footswing=0.22, freq=3.0, body_height=0.05) 는
단차 통과를 위해 평탄지 자세 안정성을 양보한 mid-range 튜닝. 결과:
평탄지 보행 중 trot swing phase 마다 base pitch 진폭이 커져 noses-dive
가시화. WTW 페이퍼 권고는 "low freq + high footswing = stair, high freq +
low footswing = sprint" — 환경별로 분리하는 게 정공.

## Components

`go2_controller.py` 내부 추가:

### 1. CMD 두 세트 (상수)

```python
_CMD_BASE_FLAT = np.array(
    [0,0,0, 0.02, 3.2, 0.5, 0,0, 0.45,
     0.18, 0,0, 0.33, 0.45, 0], dtype=np.float32)

_CMD_BASE_SLOPE = np.array(
    [0,0,0, 0.08, 2.5, 0.5, 0,0, 0.45,
     0.30, 0,0, 0.36, 0.45, 0], dtype=np.float32)
```

| idx | 컬럼          | FLAT | SLOPE | 차이                |
|-----|---------------|------|-------|---------------------|
| 3   | body_height   | 0.02 | 0.08  | 단차 클리어런스      |
| 4   | step_freq     | 3.2  | 2.5   | 단차 swing 시간      |
| 9   | footswing     | 0.18 | 0.30  | 발 들기 높이        |
| 12  | stance_width  | 0.33 | 0.36  | 안정성              |

`vx/vy/vyaw`(0..2), `pitch/roll`(10/11), `stance_l`(13) 는 동일 (네비 명령
적용 영역).

### 2. 환경 감지 (slope_score)

매 정책 tick (50Hz) 호출:

정책 입력으로 이미 계산되는 body-frame `grav` 벡터 (normalized) 활용 —
별도 IMU 파싱 불필요:

- `pitch_now = atan2(-grav[0], -grav[2])` (rad, nose-up=+)
- `pitch_ema = 0.95 * pitch_ema + 0.05 * pitch_now` (≈1s 시정수)
- `roll_now = atan2(grav[1], -grav[2])`
- `roll_ema  = 0.95 * roll_ema + 0.05 * roll_now`
- `slope_score = |pitch_ema| + 0.5 * |roll_ema|`

### 3. FSM (Hysteresis + lock)

```
mode = FLAT  (init)
mode_lock_until = 0

if now < mode_lock_until: keep mode
elif mode == FLAT  and slope_score > 0.15: → SLOPE, lock 2s, log
elif mode == SLOPE and slope_score < 0.08: → FLAT,  lock 2s, log
```

임계값 근거:
- 0.15 rad ≈ 8.6° — 일반 산악 도로 등판 진입 시 도달
- 0.08 rad ≈ 4.6° — 평탄지 noise floor 상한
- 2s lock — 단차 통과 중 짧은 pitch 진동으로 인한 chattering 방지

### 4. `_command()` 통합

```python
# was: cmd = _CMD_BASE.copy()
cmd = self._active_cmd.copy()
```

`self._active_cmd` 는 `_tick_adaptive_gait()` 가 매 tick 갱신.

## Data Flow

```
_tick (50Hz)
   ├─ articulation pose / gravity
   ├─ _tick_oob_check (기존)
   ├─ _tick_adaptive_gait (신설)
   │     ├─ pitch_ema 갱신
   │     ├─ slope_score 계산
   │     ├─ FSM 평가 (lock·hysteresis)
   │     └─ self._active_cmd ← FLAT/SLOPE
   ├─ _tick_fall_recover (기존)
   └─ _command → policy.forward → joint targets
```

## Files Modified

| 파일 | 변경 |
|------|------|
| `main_side/go2_controller.py` | _CMD_BASE_FLAT/SLOPE 상수 2개, __init__ 상태 5개, _tick_adaptive_gait() ~25줄, _command() 1줄 |
| `dev-docs/main-side.md` | go2_controller.py 섹션에 adaptive gait FSM 추가 |
| `dev-docs/CHANGELOG.md` | 2026-05-26 항목 추가 |

총 ~40줄.

## Edge Cases

- **fall 감지 직후**: fall 시 base pitch 극단 → SLOPE 강제 진입할 위험.
  → `_tick_fall_recover` 가 active 상태(`_fallen` 또는 `_recovering`)이면
  `_tick_adaptive_gait` skip + mode 유지.
- **teleport_home 직후**: pitch_ema reset 필요 → `_teleport_home` 에서
  `self._pitch_ema = 0` 추가.
- **OOB cooldown 직후**: 위와 동일 처리로 흡수.
- **stance_override 와 충돌**: 사격 ramp 의 `set_stance_override` 는 가산
  방식이라 그대로 작동. SLOPE 모드 stance_w=0.36 + override stance_w=0.05
  → 최종 0.41.

## Test Plan

| 시나리오 | 기대 결과 |
|---------|----------|
| spawn 직후 평탄지 직진 | FLAT 유지, log "gait: init FLAT" |
| 22cm 단차 진입 | 진입 ~0.5s 내 pitch_ema 상승 → SLOPE 전환 |
| 단차 통과 후 평탄지 | 2s lock 후 slope_score < 0.08 → FLAT 복귀 |
| 경사 5% 진입 | slope_score ~0.05 → FLAT 유지 (낮은 경사) |
| 경사 15% 진입 | slope_score ~0.15 → SLOPE 전환 |
| fall 도중 | mode 변경 없음 |
| 단차 위에서 pitch 짧게 진동 | 2s lock + EMA 흡수로 mode flap 없음 |

## Out of Scope

- 좌우 roll 기반 lateral gait 전환 (별도 spec)
- 학습된 다른 gait (bound, pace) 으로 전환 — 검증된 trot 만 사용
- speed-aware 동적 footswing (속도 ↑ → footswing ↓) — 차후
