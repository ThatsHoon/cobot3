"""DualSense 게임패드 teleop — sub1 backend (FastAPI uvicorn).

연결: USB 또는 Bluetooth pair, hid-playstation 드라이버 + SDL2 / pygame.
폴링: 30Hz 데몬 thread. 메인 asyncio 와 분리 — ros_bridge.pub_cmd_vel /
pub_mission 가 rclpy thread-safe publisher 라 직접 호출 가능.

매핑 (2026-05-20 사용자 사양):
  L-stick L:    무시
  R-stick L/R:  cmd_vel.angular.z = ±wz_max  (좌/우 제자리 회전)
  R-stick U/D:  무시
  D-pad ↑/↓:    cmd_vel.linear.x = ±vx_max   (제자리 전후진)
  D-pad ←/→:    cmd_vel.linear.y = ±vy_max   (제자리 좌우 평행)
  L2 (hold):    speed_scale −= step  (min 0.1)
  R2 (hold):    speed_scale += step  (max 1.6)
  × edge:       /mission_command "stop" ↔ "resume" 토글
  △ edge:       /mission_command "sortie"
  ○ edge:       /mission_command "home"

WHY graceful 비활성: pygame 미설치/joystick 없음 → 서비스 자체는 정상.
"""
import os
import threading
import time

try:
    import pygame
except Exception:
    pygame = None

# SDL2 + hid-playstation 표준 매핑 (DualSense 5)
AXIS_LX, AXIS_LY, AXIS_L2 = 0, 1, 2
AXIS_RX, AXIS_RY, AXIS_R2 = 3, 4, 5
BTN_CROSS, BTN_CIRCLE, BTN_SQUARE, BTN_TRIANGLE = 0, 1, 3, 2

# DPAD: pygame hat (1축 단방) 사용 — get_hat(0) = (x, y), x∈{-1,0,+1}, y∈{-1,0,+1}
# +y = ↑, +x = →

DEADZONE = 0.30
POLL_HZ = 30
RESCAN_INTERVAL_S = 1.0
TRIGGER_THRESHOLD = 0.5          # L2/R2 hold threshold
SPEED_STEP = 0.05                 # L2/R2 hold 0.1초마다 ±0.05
SPEED_STEP_PERIOD_S = 0.10
SPEED_MIN, SPEED_MAX = 0.1, 1.6

# cmd_vel limit (Go2 walk-these-ways 학습 분포 안전 범위)
VX_MAX = 1.2   # m/s
VY_MAX = 0.6
WZ_MAX = 1.0   # rad/s

# inspect 짐벌 — L-stick 매핑 (사용자 사양 2026-05-20)
import math as _math
INSPECT_LIM_RAD = _math.radians(70.0)   # 정면 ±70°
# 2026-05-24: 정밀 조준용 2°/s 로 통일 (웹 UI / look_at_pixel / DS 컨트롤러 공통).
INSPECT_RATE_RAD_PER_S = _math.radians(2.0)    # full-stick 2°/s


class DualSenseService:
    """sub1 backend 측 DualSense polling 서비스.

    - ros_bridge: pub_cmd_vel(lin, ang, vy), pub_mission(cmd) 호출자.
    - patrol_state_getter: callable → dict (mode 등) — × 토글에서 mode 확인.
    """

    def __init__(self, ros_bridge, patrol_state_getter):
        self._ros = ros_bridge
        self._get_patrol = patrol_state_getter
        self._thread = None
        self._stopped = True
        self._joystick = None
        self._connected = False
        self._name = ""
        self._speed_scale = 1.0
        self._last_dpad = (0, 0)
        self._last_btns = {}
        self._stop_or_resume_next = "stop"   # × 토글 fallback (mode 미수신 시)
        self._l2_next_fire_t = 0.0
        self._r2_next_fire_t = 0.0
        self._last_cmd_zero = True   # cmd_vel 마지막이 0 인지 (jitter 발행 회피)
        # inspect 짐벌 상태 (L-stick 누적). 백엔드 절대값 발행.
        self._inspect_pan = 0.0
        self._inspect_tilt = 0.0
        self._last_inspect_t = 0.0

    # ── status -----------------------------------------------------------
    def status(self) -> dict:
        return {
            "connected": self._connected,
            "name": self._name,
            "speed_scale": round(self._speed_scale, 2),
            "limits": {"vx": VX_MAX, "vy": VY_MAX, "wz": WZ_MAX},
            "polling_hz": POLL_HZ,
            "pygame_available": pygame is not None,
            "inspect": {
                "pan_deg":  round(_math.degrees(self._inspect_pan), 1),
                "tilt_deg": round(_math.degrees(self._inspect_tilt), 1),
                "limit_deg": 70.0,
            },
            "mapping": {
                "left_stick_L/R":  "inspect pan ±70°",
                "left_stick_U/D":  "inspect tilt ±70°",
                "right_stick_L/R": "yaw left/right",
                "dpad_up/down":    "forward/back",
                "dpad_left/right": "strafe left/right",
                "L2_hold":         "inspect zoom in",
                "R2_hold":         "inspect zoom out",
                "cross":           "stop / resume toggle",
                "triangle":        "sortie",
                "circle":          "home",
            },
        }

    # ── lifecycle --------------------------------------------------------
    def start(self):
        if pygame is None:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stopped = False
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="dualsense-worker")
        self._thread.start()

    def stop(self):
        self._stopped = True
        if self._connected:
            self._safe_stop_cmd()

    # ── internal ---------------------------------------------------------
    def _ensure_pygame(self):
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        if not pygame.get_init():
            pygame.init()
        if not pygame.joystick.get_init():
            pygame.joystick.init()

    def _try_open(self) -> bool:
        try:
            self._ensure_pygame()
        except Exception:
            return False
        pygame.joystick.quit()
        pygame.joystick.init()
        for i in range(pygame.joystick.get_count()):
            try:
                j = pygame.joystick.Joystick(i)
                j.init()
                name = j.get_name() or "?"
                if any(k in name for k in
                       ("DualSense", "Wireless Controller", "Sony")):
                    self._joystick = j
                    self._connected = True
                    self._name = name
                    return True
            except Exception:
                continue
        return False

    def _close(self):
        if self._connected:
            self._safe_stop_cmd()
        if self._joystick is not None:
            try:
                self._joystick.quit()
            except Exception:
                pass
            self._joystick = None
        self._connected = False
        self._name = ""

    def _safe_stop_cmd(self):
        try:
            self._ros.pub_cmd_vel(0.0, 0.0, vy=0.0)
        except Exception:
            pass

    def _publish_mission(self, cmd: str):
        try:
            self._ros.pub_mission(cmd)
        except Exception:
            pass

    def _handle_cross_edge(self):
        """× 토글: patrol_state.mode 가 PAUSED 면 resume, 아니면 stop."""
        mode = None
        try:
            st = self._get_patrol() or {}
            mode = str(st.get("mode") or "").upper()
        except Exception:
            pass
        if mode == "PAUSED":
            cmd = "resume"
        else:
            cmd = "stop"
        self._publish_mission(cmd)

    def _run(self):
        period = 1.0 / POLL_HZ
        last_rescan = 0.0
        last_speed_t = 0.0
        while not self._stopped:
            t0 = time.monotonic()
            try:
                if not self._connected:
                    if t0 - last_rescan >= RESCAN_INTERVAL_S:
                        last_rescan = t0
                        self._try_open()
                    if not self._connected:
                        time.sleep(0.2)
                        continue

                # 이벤트 처리 (button edge)
                for ev in pygame.event.get():
                    if ev.type == pygame.JOYBUTTONDOWN:
                        if ev.button == BTN_CROSS:
                            self._handle_cross_edge()
                        elif ev.button == BTN_TRIANGLE:
                            self._publish_mission("sortie")
                        elif ev.button == BTN_CIRCLE:
                            self._publish_mission("home")

                j = self._joystick
                try:
                    nax = j.get_numaxes()
                except Exception:
                    self._close()
                    continue

                # ── L-stick → inspect 짐벌 pan/tilt (사용자 사양) ──
                # LX 좌(-1)/우(+1) → pan delta (음수 = 좌). LY 위(-1)/아래(+1) → tilt
                # delta (스틱 위=카메라 위=+tilt 라 -ly_raw 부호 반전).
                lx_raw = j.get_axis(AXIS_LX) if nax > AXIS_LX else 0.0
                ly_raw = j.get_axis(AXIS_LY) if nax > AXIS_LY else 0.0
                dt_ck = 1.0 / POLL_HZ
                if abs(lx_raw) >= DEADZONE:
                    sign = 1.0 if lx_raw > 0 else -1.0
                    self._inspect_pan += sign * (abs(lx_raw) ** 1.2) \
                        * INSPECT_RATE_RAD_PER_S * dt_ck
                    self._inspect_pan = max(-INSPECT_LIM_RAD,
                                            min(INSPECT_LIM_RAD, self._inspect_pan))
                if abs(ly_raw) >= DEADZONE:
                    sign = -1.0 if ly_raw > 0 else 1.0   # ly>0 = 스틱 아래 = -tilt
                    self._inspect_tilt += sign * (abs(ly_raw) ** 1.2) \
                        * INSPECT_RATE_RAD_PER_S * dt_ck
                    self._inspect_tilt = max(-INSPECT_LIM_RAD,
                                             min(INSPECT_LIM_RAD, self._inspect_tilt))
                # 5Hz 절대값 발행 — full-stick 시 9° step. 변화 없으면 skip.
                now_t = time.monotonic()
                if (abs(lx_raw) >= DEADZONE or abs(ly_raw) >= DEADZONE) \
                        and (now_t - self._last_inspect_t) >= 0.20:
                    try:
                        self._ros.pub_inspect_cmd({
                            "pan": self._inspect_pan,
                            "tilt": self._inspect_tilt,
                            "absolute": True,
                        })
                    except Exception:
                        pass
                    self._last_inspect_t = now_t

                # ── L2/R2 hold → inspect camera zoom in/out (사용자 사양 2026-05-20) ──
                # L2 = zoom in (focal +, 0.2s 마다 ×1.1), R2 = zoom out (×0.9)
                l2 = (j.get_axis(AXIS_L2) + 1.0) * 0.5 if nax > AXIS_L2 else 0.0
                r2 = (j.get_axis(AXIS_R2) + 1.0) * 0.5 if nax > AXIS_R2 else 0.0
                now = time.monotonic()
                if l2 >= TRIGGER_THRESHOLD and now >= self._l2_next_fire_t:
                    try:
                        self._ros.pub_inspect_cmd({"zoom": 1.10, "absolute": False})
                    except Exception:
                        pass
                    self._l2_next_fire_t = now + 0.20
                if r2 >= TRIGGER_THRESHOLD and now >= self._r2_next_fire_t:
                    try:
                        self._ros.pub_inspect_cmd({"zoom": 0.90, "absolute": False})
                    except Exception:
                        pass
                    self._r2_next_fire_t = now + 0.20

                # ── cmd_vel 결정 ──
                # 우선순위: D-pad (제자리) > R-stick (yaw). 동시 입력 시 D-pad 우선.
                hat = j.get_hat(0) if j.get_numhats() > 0 else (0, 0)
                hx, hy = hat   # +x=오른쪽, +y=위쪽 (pygame 표준)
                rx = j.get_axis(AXIS_RX) if nax > AXIS_RX else 0.0

                vx = vy = wz = 0.0
                # D-pad 입력 우선
                if hx or hy:
                    if hy > 0:
                        vx = VX_MAX
                    elif hy < 0:
                        vx = -VX_MAX
                    if hx > 0:
                        vy = -VY_MAX   # → = 우평행 = robot −Y
                    elif hx < 0:
                        vy = VY_MAX    # ← = 좌평행 = robot +Y
                else:
                    if abs(rx) >= DEADZONE:
                        sign = -1.0 if rx > 0 else 1.0   # 우=−wz, 좌=+wz
                        wz = sign * (abs(rx) ** 1.2) * WZ_MAX

                # speed_scale 적용
                vx *= self._speed_scale
                vy *= self._speed_scale
                wz *= self._speed_scale

                is_zero = (vx == 0.0 and vy == 0.0 and wz == 0.0)
                if not is_zero or not self._last_cmd_zero:
                    # 0→0 jitter 회피: 0 인 상태가 연속이면 발행 생략 (1회만 발행)
                    self._ros.pub_cmd_vel(vx, wz, vy=vy)
                self._last_cmd_zero = is_zero

            except Exception:
                self._close()

            elapsed = time.monotonic() - t0
            if elapsed < period:
                time.sleep(period - elapsed)

        self._close()
