"use client";
import { useState } from "react";
import { postJSON, WeatherCommand } from "@/lib/api";
import {
  Sunrise, Sun, Sunset, Moon,
  Cloud, CloudFog, CloudRain, CloudSnow,
  Wind,
} from "lucide-react";

/** 날씨·바람 제어 패널. POST /weather → /weather/command (Main camera_publisher
 *  + wind_publisher 양쪽 구독). hi 브랜치의 time_of_day + weather + 신규
 *  wind_mode/dir/speed 통합.
 *  2026-05-21: 이모지 → lucide-react 아이콘 (퀄리티 향상).
 */
type Icon = typeof Sun;
const TODS: { value: WeatherCommand["time_of_day"]; Icon: Icon; label: string }[] = [
  { value: "morning", Icon: Sunrise, label: "MORN" },
  { value: "noon",    Icon: Sun,     label: "NOON" },
  { value: "evening", Icon: Sunset,  label: "EVE"  },
  { value: "night",   Icon: Moon,    label: "NGHT" },
];
const WEATHERS: { value: WeatherCommand["weather"]; Icon: Icon; label: string }[] = [
  { value: "clear",  Icon: Sun,       label: "CLEAR"  },
  { value: "cloudy", Icon: Cloud,     label: "CLOUDY" },
  { value: "fog",    Icon: CloudFog,  label: "FOG"    },
  { value: "rain",   Icon: CloudRain, label: "RAIN"   },
  { value: "snow",   Icon: CloudSnow, label: "SNOW"   },
];
const WINDS: WeatherCommand["wind_mode"][] = ["calm", "breeze", "windy", "gale", "storm"];

export default function WeatherControl() {
  const [tod, setTod] = useState<WeatherCommand["time_of_day"]>("noon");
  const [wx, setWx] = useState<WeatherCommand["weather"]>("clear");
  const [wm, setWm] = useState<WeatherCommand["wind_mode"]>("calm");
  const [random, setRandom] = useState(true);
  const [dirDeg, setDirDeg] = useState(0);
  const [speed, setSpeed] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  const apply = async (patch: WeatherCommand) => {
    setBusy(true);
    try {
      await postJSON("/weather", patch);
    } catch (e) {
      console.error("weather POST", e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel">
      <div className="panel-hd">
        <span>WEATHER</span>
        <span className="text-[10px] text-dim">SIM ENV CONTROL</span>
      </div>
      <div className="p-2 flex flex-col gap-2 text-[11px]">
        {/* TIME OF DAY */}
        <div className="flex items-center gap-1">
          <span className="text-dim w-12">TIME</span>
          {TODS.map(({ value, Icon, label }) => (
            <button key={value}
              onClick={() => { setTod(value); apply({ time_of_day: value }); }}
              disabled={busy}
              className={`flex-1 flex flex-col items-center gap-0.5 px-1 py-1.5 border ${tod === value
                ? "border-phos bg-phos/15 text-phos"
                : "border-line text-ink hover:bg-zinc-800"}`}>
              <Icon size={18} strokeWidth={1.8} />
              <span className="text-[9px] tracking-wider">{label}</span>
            </button>
          ))}
        </div>

        {/* WEATHER */}
        <div className="flex items-center gap-1">
          <span className="text-dim w-12">WX</span>
          {WEATHERS.map(({ value, Icon, label }) => (
            <button key={value}
              onClick={() => { setWx(value); apply({ weather: value }); }}
              disabled={busy}
              className={`flex-1 flex flex-col items-center gap-0.5 px-1 py-1.5 border ${wx === value
                ? "border-phos bg-phos/15 text-phos"
                : "border-line text-ink hover:bg-zinc-800"}`}>
              <Icon size={18} strokeWidth={1.8} />
              <span className="text-[9px] tracking-wider">{label}</span>
            </button>
          ))}
        </div>

        {/* WIND MODE */}
        <div className="flex items-center gap-1">
          <span className="text-dim w-12 flex items-center gap-1">
            <Wind size={12} strokeWidth={1.8} /> WIND
          </span>
          {WINDS.map(m => (
            <button key={m}
              onClick={() => { setWm(m); apply({ wind_mode: m }); }}
              disabled={busy}
              className={`flex-1 px-1 py-1.5 border uppercase tracking-wider ${wm === m
                ? "border-amber-400 bg-amber-400/15 text-amber-300"
                : "border-line text-ink hover:bg-zinc-800"}`}>
              {m}
            </button>
          ))}
        </div>

        {/* DIR + SPEED override */}
        <div className="flex items-center gap-2 mt-1">
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={random}
              onChange={e => {
                setRandom(e.target.checked);
                apply({ wind_random_dir: e.target.checked,
                        wind_dir_deg: e.target.checked ? null : dirDeg });
              }} />
            <span className="text-dim">RND DIR</span>
          </label>
          <div className="flex items-center gap-1 flex-1">
            <span className="text-dim w-12">DIR</span>
            <input type="range" min={0} max={359} value={dirDeg}
              disabled={random}
              onChange={e => setDirDeg(Number(e.target.value))}
              onMouseUp={() => apply({ wind_random_dir: false, wind_dir_deg: dirDeg })}
              className="flex-1" />
            <span className="font-mono w-10 text-right">{dirDeg}°</span>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={speed !== null}
              onChange={e => {
                const v = e.target.checked ? 5 : null;
                setSpeed(v);
                apply({ wind_speed_m_s: v });
              }} />
            <span className="text-dim">SPD OVR</span>
          </label>
          <input type="range" min={0} max={18} step={0.5}
            value={speed ?? 0} disabled={speed === null}
            onChange={e => setSpeed(Number(e.target.value))}
            onMouseUp={() => speed !== null && apply({ wind_speed_m_s: speed })}
            className="flex-1" />
          <span className="font-mono w-12 text-right">
            {speed !== null ? `${speed.toFixed(1)} m/s` : "auto"}
          </span>
        </div>
      </div>
    </div>
  );
}
