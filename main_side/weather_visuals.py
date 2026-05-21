"""weather_visuals.py — Sun/Dome 조명 + 비/눈/안개 procedural geometry.

원본: ThatsHoon/cobot3 'hi' 브랜치 isaacsim/anymal_gp_terrain.py 의
TIME_OF_DAY_PRESETS / WEATHER_PRESETS / _add_weather_effects /
_apply_environment_visuals / _update_weather_effects 발췌·재구성.

cobot3 적용 변경점:
- DomeLight: gp_scene.usd 의 기존 /World/DomeLight_01 재사용 (있으면), 없으면 신규
- DistantLight: /World/Sun 신규 정의 (gp_scene 에 sun 없음)
- center_xy: robot_xy_provider() 콜백으로 매 update 마다 Go2 base 추적
- area: 80m 기본 (Go2 근처만 시각효과 — 산악 지형 전체 cover 불필요)

사용:
    from weather_visuals import WeatherVisuals
    vis = WeatherVisuals(stage, robot_xy_provider=lambda: (px, py))
    vis.set_mode(time_of_day="noon", weather="rain")
    # physics callback 에서 vis.update(dt)
"""
from typing import Callable, Tuple, Optional
import numpy as np
from pxr import UsdGeom, UsdLux, Gf, Sdf

WEATHER_EFFECTS_PATH = "/World/WeatherEffects"
SUN_PATH = "/World/Sun"
DOME_PATH_PREFERRED = "/World/DomeLight_01"   # gp_scene 기존
DOME_PATH_FALLBACK  = "/World/DomeLight"

TIME_OF_DAY_PRESETS = {
    "morning": {"sun_rotation": (-20.0, 0.0, 58.0),  "sun_intensity": 1250.0,
                "sun_color": (1.0, 0.70, 0.42),
                "dome_intensity": 470.0, "dome_color": (0.76, 0.88, 1.0)},
    "noon":    {"sun_rotation": (-55.0, 0.0, 35.0),  "sun_intensity": 1800.0,
                "sun_color": (1.0, 0.96, 0.84),
                "dome_intensity": 650.0, "dome_color": (0.86, 0.92, 1.0)},
    "evening": {"sun_rotation": (-12.0, 0.0, -62.0), "sun_intensity": 950.0,
                "sun_color": (1.0, 0.48, 0.26),
                "dome_intensity": 360.0, "dome_color": (0.56, 0.62, 0.82)},
    "night":   {"sun_rotation": (-5.0, 0.0, 120.0),  "sun_intensity": 60.0,
                "sun_color": (0.35, 0.48, 0.78),
                "dome_intensity": 95.0,  "dome_color": (0.08, 0.11, 0.19)},
}
WEATHER_PRESETS = {
    "clear":  {"sun_multiplier": 1.0,  "dome_multiplier": 1.0,
               "tint": (1.0, 1.0, 1.0),  "tint_strength": 0.0,  "effect": None},
    "cloudy": {"sun_multiplier": 0.38, "dome_multiplier": 0.88,
               "tint": (0.62, 0.68, 0.74), "tint_strength": 0.45, "effect": None},
    "fog":    {"sun_multiplier": 0.25, "dome_multiplier": 0.72,
               "tint": (0.62, 0.70, 0.74), "tint_strength": 0.60, "effect": "fog"},
    "rain":   {"sun_multiplier": 0.28, "dome_multiplier": 0.68,
               "tint": (0.48, 0.58, 0.68), "tint_strength": 0.62, "effect": "rain"},
    "snow":   {"sun_multiplier": 0.55, "dome_multiplier": 1.18,
               "tint": (0.78, 0.88, 1.0),  "tint_strength": 0.50, "effect": "snow"},
}


def _mix_color(base, tint, strength):
    s = float(np.clip(strength, 0.0, 1.0))
    b = np.asarray(base, dtype=float); t = np.asarray(tint, dtype=float)
    return tuple(float(v) for v in np.clip(b * (1.0 - s) + t * s, 0.0, 1.0))


def _set_visible(stage, path: str, visible: bool) -> None:
    prim = stage.GetPrimAtPath(path)
    if prim and prim.IsValid():
        UsdGeom.Imageable(prim).GetVisibilityAttr().Set(
            "inherited" if visible else "invisible")


def _curve_lines(stage, path: str, lines, width: float, color):
    pts, counts = [], []
    for line in lines:
        counts.append(len(line))
        pts.extend([Gf.Vec3f(*p) for p in line])
    c = UsdGeom.BasisCurves.Define(stage, Sdf.Path(path))
    c.CreateTypeAttr(UsdGeom.Tokens.linear)
    c.CreateCurveVertexCountsAttr(counts)
    c.CreatePointsAttr(pts)
    c.CreateWidthsAttr([width])
    c.CreateDisplayColorAttr([Gf.Vec3f(*color)])
    return c


class WeatherVisuals:
    """Time-of-day + weather preset 적용 + 비/눈/안개 procedural 애니메이션."""

    def __init__(self, stage,
                 robot_xy_provider: Optional[Callable[[], Tuple[float, float]]] = None,
                 area: float = 80.0):
        self._stage = stage
        self._area = float(area)
        self._robot_xy = robot_xy_provider or (lambda: (0.0, 0.0))
        self._time_of_day = "noon"
        self._weather = "clear"
        self._visual_time = 0.0
        self._lights = self._setup_lights()
        self._fx = self._build_effects()
        self.set_mode(self._time_of_day, self._weather)

    def _setup_lights(self) -> dict:
        stage = self._stage
        # DomeLight: 기존(/DomeLight_01) 재사용, 없으면 fallback 신규
        dome_prim = stage.GetPrimAtPath(DOME_PATH_PREFERRED)
        if dome_prim and dome_prim.IsValid():
            dome = UsdLux.DomeLight(dome_prim)
        else:
            dome = UsdLux.DomeLight.Define(stage, Sdf.Path(DOME_PATH_FALLBACK))
        dome_int = dome.GetIntensityAttr() or dome.CreateIntensityAttr(650.0)
        dome_col = dome.GetColorAttr() or dome.CreateColorAttr(Gf.Vec3f(0.86, 0.92, 1.0))

        # Sun: 신규 정의 (gp_scene 미존재)
        sun_prim = stage.GetPrimAtPath(SUN_PATH)
        if not (sun_prim and sun_prim.IsValid()):
            sun = UsdLux.DistantLight.Define(stage, Sdf.Path(SUN_PATH))
            sun.CreateAngleAttr(0.7)
        else:
            sun = UsdLux.DistantLight(sun_prim)
        sun_int = sun.GetIntensityAttr() or sun.CreateIntensityAttr(1800.0)
        sun_col = sun.GetColorAttr() or sun.CreateColorAttr(Gf.Vec3f(1.0, 0.96, 0.84))
        # rotate op (idempotent)
        xf = UsdGeom.Xformable(sun.GetPrim())
        rot_op = None
        for op in xf.GetOrderedXformOps():
            if op.GetOpType() == UsdGeom.XformOp.TypeRotateXYZ:
                rot_op = op; break
        if rot_op is None:
            rot_op = xf.AddRotateXYZOp()
        return {"sun_int": sun_int, "sun_col": sun_col, "sun_rot": rot_op,
                "dome_int": dome_int, "dome_col": dome_col}

    def _build_effects(self) -> dict:
        stage = self._stage
        stage.DefinePrim(WEATHER_EFFECTS_PATH, "Xform")
        rng = np.random.default_rng(20260521)
        area = self._area

        # Rain (BasisCurves 220 streaks)
        rain_lines, rain_bases, rain_speeds = [], [], []
        for _ in range(220):
            x, y = rng.uniform(-area, area, 2)
            z = rng.uniform(2.2, 8.8)
            rain_bases.append((float(x), float(y), float(z)))
            rain_speeds.append(float(rng.uniform(5.5, 8.0)))
            rain_lines.append(((float(x), float(y), float(z)),
                               (float(x - 0.18), float(y - 0.36), float(z - 1.05))))
        rain_path = f"{WEATHER_EFFECTS_PATH}/RainStreaks"
        rain_c = _curve_lines(stage, rain_path, rain_lines, 0.012, (0.50, 0.62, 0.72))

        # Fog (BasisCurves bands)
        fog_lines, fog_bases = [], []
        for band, y in enumerate(np.linspace(-area, area, 18)):
            for z in (0.45, 0.95, 1.45):
                off = 0.6 * np.sin(band * 0.8 + z)
                fog_bases.append((float(y), float(z), float(off), float(band)))
                fog_lines.append(((-area, float(y + off), float(z)),
                                  (area, float(y - off), float(z + 0.08))))
        fog_path = f"{WEATHER_EFFECTS_PATH}/FogBands"
        fog_c = _curve_lines(stage, fog_path, fog_lines, 0.075, (0.55, 0.62, 0.65))

        # Snow (Points 260)
        snow_pts, snow_bases, snow_speeds, snow_phases, snow_w = [], [], [], [], []
        for _ in range(260):
            x, y = rng.uniform(-area, area, 2)
            z = rng.uniform(1.0, 7.6)
            snow_bases.append((float(x), float(y), float(z)))
            snow_speeds.append(float(rng.uniform(0.45, 1.1)))
            snow_phases.append(float(rng.uniform(0.0, np.pi * 2.0)))
            snow_pts.append(Gf.Vec3f(float(x), float(y), float(z)))
            snow_w.append(float(rng.uniform(0.035, 0.075)))
        snow = UsdGeom.Points.Define(stage, Sdf.Path(f"{WEATHER_EFFECTS_PATH}/SnowFlakes"))
        snow.CreatePointsAttr(snow_pts)
        snow.CreateWidthsAttr(snow_w)
        snow.CreateDisplayColorAttr([Gf.Vec3f(0.90, 0.96, 1.0)])

        for path in (rain_path, fog_path, str(snow.GetPath())):
            _set_visible(stage, path, False)

        return {
            "paths": {"rain": rain_path, "fog": fog_path,
                      "snow": str(snow.GetPath())},
            "rain": {"pts": rain_c.GetPointsAttr(), "col": rain_c.GetDisplayColorAttr(),
                     "color": (0.50, 0.62, 0.72),
                     "bases": np.asarray(rain_bases),
                     "speeds": np.asarray(rain_speeds)},
            "fog":  {"pts": fog_c.GetPointsAttr(), "col": fog_c.GetDisplayColorAttr(),
                     "color": (0.55, 0.62, 0.65),
                     "bases": np.asarray(fog_bases)},
            "snow": {"pts": snow.GetPointsAttr(), "col": snow.GetDisplayColorAttr(),
                     "color": (0.90, 0.96, 1.0),
                     "bases": np.asarray(snow_bases),
                     "speeds": np.asarray(snow_speeds),
                     "phases": np.asarray(snow_phases)},
        }

    # ---------- public API ----------

    def set_mode(self, time_of_day: Optional[str] = None,
                 weather: Optional[str] = None) -> None:
        if time_of_day and time_of_day in TIME_OF_DAY_PRESETS:
            self._time_of_day = time_of_day
        if weather and weather in WEATHER_PRESETS:
            self._weather = weather
        self._apply_lights()
        active = WEATHER_PRESETS[self._weather]["effect"]
        for name, path in self._fx["paths"].items():
            visible = (active == name)
            _set_visible(self._stage, path, visible)
            data = self._fx[name]
            dim = 0.34 if self._time_of_day == "night" else 1.0
            col = tuple(float(c) * dim for c in data["color"])
            data["col"].Set([Gf.Vec3f(*col)])

    def _apply_lights(self) -> None:
        t = TIME_OF_DAY_PRESETS[self._time_of_day]
        w = WEATHER_PRESETS[self._weather]
        sun_i = float(t["sun_intensity"] * w["sun_multiplier"])
        dome_i = float(t["dome_intensity"] * w["dome_multiplier"])
        tint_s = float(w["tint_strength"])
        if self._time_of_day == "night":
            tint_s *= 0.16
            sun_i = min(sun_i, float(t["sun_intensity"]))
            dome_i = min(dome_i, float(t["dome_intensity"]))
        sun_c = _mix_color(t["sun_color"],  w["tint"], tint_s)
        dome_c = _mix_color(t["dome_color"], w["tint"], tint_s)
        L = self._lights
        L["sun_int"].Set(sun_i)
        L["sun_col"].Set(Gf.Vec3f(*sun_c))
        L["sun_rot"].Set(Gf.Vec3f(*t["sun_rotation"]))
        L["dome_int"].Set(dome_i)
        L["dome_col"].Set(Gf.Vec3f(*dome_c))

    def update(self, dt: float) -> None:
        """매 step 호출 — 활성 effect 의 점 위치 갱신 (rain/snow drift, fog scroll)."""
        self._visual_time += float(dt)
        active = WEATHER_PRESETS[self._weather]["effect"]
        if active is None:
            return
        cx, cy = self._robot_xy()
        t = self._visual_time
        area = self._area

        if active == "rain":
            d = self._fx["rain"]
            bases, speeds = d["bases"], d["speeds"]
            z = 1.6 + np.mod(bases[:, 2] - t * speeds - 1.6, 7.0)
            dx, dy = -0.65 * t, -1.15 * t
            x = cx - area + np.mod(bases[:, 0] + area + dx, area * 2.0)
            y = cy - area + np.mod(bases[:, 1] + area + dy, area * 2.0)
            pts = []
            for px, py, pz in zip(x, y, z):
                pts.append(Gf.Vec3f(float(px), float(py), float(pz)))
                pts.append(Gf.Vec3f(float(px - 0.18),
                                    float(py - 0.36), float(pz - 1.05)))
            d["pts"].Set(pts)
        elif active == "snow":
            d = self._fx["snow"]
            b, sp, ph = d["bases"], d["speeds"], d["phases"]
            z = 1.1 + np.mod(b[:, 2] - t * sp - 1.1, 6.8)
            x = cx + b[:, 0] + 0.45 * np.sin(t * 1.4 + ph)
            y = cy + b[:, 1] + 0.35 * np.cos(t * 1.1 + ph * 0.7)
            d["pts"].Set([Gf.Vec3f(float(px), float(py), float(pz))
                          for px, py, pz in zip(x, y, z)])
        elif active == "fog":
            d = self._fx["fog"]
            pts = []
            for by, bz, bo, bi in d["bases"]:
                scroll = np.sin(t * 0.34 + bi * 0.8)
                wave = 0.45 * np.sin(t * 0.72 + bi + bz)
                y0 = cy + by + bo + wave
                y1 = cy + by - bo + wave * 0.35
                xs = 1.5 * scroll
                pts.append(Gf.Vec3f(float(cx - area + xs), float(y0), float(bz)))
                pts.append(Gf.Vec3f(float(cx + area + xs), float(y1), float(bz + 0.08)))
            d["pts"].Set(pts)

    @property
    def time_of_day(self) -> str:
        return self._time_of_day

    @property
    def weather(self) -> str:
        return self._weather
