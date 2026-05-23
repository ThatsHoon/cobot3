"use client";
import { useState } from "react";
import { postJSON, WeatherCommand } from "@/lib/api";
import {
  Sunrise, Sun, Sunset, Moon,
  Cloud, CloudFog, CloudRain, CloudSnow,
  Wind,
} from "lucide-react";
import SettingsPopover from "./SettingsPopover";

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
        <span>WEATHER · ENV</span>
        <span className="flex items-center gap-2">
          <SettingsPopover title="WIND · DIR & SPD OVERRIDE" width={320}>
            <div className="space-y-2.5 text-[10.5px]">
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={random}
                  onChange={e => {
                    setRandom(e.target.checked);
                    apply({ wind_random_dir: e.target.checked,
                            wind_dir_deg: e.target.checked ? null : dirDeg });
                  }} />
                <span className="text-ink-2 tracking-[0.14em]">RND DIR</span>
                <span className="text-dim text-[9px]">방향 무작위</span>
              </label>
              <div className="flex items-center gap-2">
                <span className="text-dim w-10 tracking-[0.22em]">DIR</span>
                <input type="range" min={0} max={359} value={dirDeg}
                  disabled={random}
                  onChange={e => setDirDeg(Number(e.target.value))}
                  onMouseUp={() => apply({ wind_random_dir: false, wind_dir_deg: dirDeg })}
                  className="flex-1" />
                <span className="w-12 text-right text-ink tabular">{dirDeg}°</span>
              </div>
              <div className="border-t border-line pt-2">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={speed !== null}
                    onChange={e => {
                      const v = e.target.checked ? 5 : null;
                      setSpeed(v);
                      apply({ wind_speed_m_s: v });
                    }} />
                  <span className="text-ink-2 tracking-[0.14em]">SPD OVR</span>
                  <span className="text-dim text-[9px]">속도 직접 지정</span>
                </label>
                <div className="flex items-center gap-2 mt-2">
                  <span className="text-dim w-10 tracking-[0.22em]">SPD</span>
                  <input type="range" min={0} max={18} step={0.5}
                    value={speed ?? 0} disabled={speed === null}
                    onChange={e => setSpeed(Number(e.target.value))}
                    onMouseUp={() => speed !== null && apply({ wind_speed_m_s: speed })}
                    className="flex-1" />
                  <span className="w-16 text-right text-ink tabular">
                    {speed !== null ? <>{speed.toFixed(1)}<span className="text-dim ml-1">m/s</span></> : "auto"}
                  </span>
                </div>
              </div>
            </div>
          </SettingsPopover>
          <span className="panel-idx">SIM/ENV</span>
        </span>
      </div>
      <div className="p-2.5 flex flex-col gap-2 text-[11px]">
        <Row label="TIME">
          {TODS.map(({ value, Icon, label }) => (
            <button key={value}
              onClick={() => { setTod(value); apply({ time_of_day: value }); }}
              disabled={busy}
              data-active={tod === value ? "true" : "false"}
              className="btn flex-1 !py-1.5 !px-0.5 flex flex-col items-center gap-0.5">
              <Icon size={16} strokeWidth={1.6} />
              <span className="text-[9px] tracking-[0.14em]">{label}</span>
            </button>
          ))}
        </Row>

        <Row label="WX">
          {WEATHERS.map(({ value, Icon, label }) => (
            <button key={value}
              onClick={() => { setWx(value); apply({ weather: value }); }}
              disabled={busy}
              data-active={wx === value ? "true" : "false"}
              className="btn flex-1 !py-1.5 !px-0.5 flex flex-col items-center gap-0.5">
              <Icon size={16} strokeWidth={1.6} />
              <span className="text-[9px] tracking-[0.14em]">{label}</span>
            </button>
          ))}
        </Row>

        <Row label={<><Wind size={11} strokeWidth={1.8} /> WIND</>}>
          {WINDS.map(m => (
            <button key={m}
              onClick={() => { setWm(m); apply({ wind_mode: m }); }}
              disabled={busy}
              data-active={wm === m ? "true" : "false"}
              data-tone={wm === m ? "amber" : undefined}
              className="btn flex-1 !py-1.5 !text-[10px] !tracking-[0.14em]">
              {m!.toUpperCase()}
            </button>
          ))}
        </Row>
      </div>
    </div>
  );
}

function Row({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-dim w-12 tracking-[0.22em] text-[10px] flex items-center gap-1">
        {label}
      </span>
      {children}
    </div>
  );
}
