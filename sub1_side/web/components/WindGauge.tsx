"use client";
import { WindState } from "@/lib/api";

/** 풍속·풍향 시각화 — 큰 화살표 + 보퍼트 라벨 + 수치.
 *  /wind/state (5Hz throttled) 구독한 page.tsx 가 prop 으로 전달.
 *  화살표는 풍향(바람이 가리키는 방향, 즉 from→to)으로 회전.
 */
function beaufort(speed: number): { idx: number; label: string; color: string } {
  // Beaufort scale (0~12). 18 m/s ≈ 8.
  if (speed < 0.3)  return { idx: 0,  label: "CALM",       color: "text-zinc-500" };
  if (speed < 1.6)  return { idx: 1,  label: "LIGHT AIR",  color: "text-zinc-400" };
  if (speed < 3.4)  return { idx: 2,  label: "LIGHT BR",   color: "text-cyan-400" };
  if (speed < 5.5)  return { idx: 3,  label: "GENTLE BR",  color: "text-cyan-300" };
  if (speed < 8.0)  return { idx: 4,  label: "MOD BREEZE", color: "text-emerald-400" };
  if (speed < 10.8) return { idx: 5,  label: "FRESH BR",   color: "text-yellow-400" };
  if (speed < 13.9) return { idx: 6,  label: "STRONG BR",  color: "text-orange-400" };
  if (speed < 17.2) return { idx: 7,  label: "NEAR GALE",  color: "text-orange-500" };
  return                  { idx: 8,  label: "GALE",       color: "text-rose-500" };
}

export default function WindGauge({ wind }: { wind: WindState | null }) {
  if (!wind) {
    return (
      <div className="flex items-center gap-2 px-2 text-[11px] text-dim">
        <span>WIND</span><span>—</span>
      </div>
    );
  }
  const b = beaufort(wind.speed);
  // SVG 화살표 회전: dir_deg 는 atan2(vy,vx) — east=0°, north=90°.
  // CSS rotate 는 시계방향 — 보정: deg = 90 - dir_deg (north=top, east=right)
  const rot = 90 - wind.dir_deg;
  const len = Math.min(1.0, wind.speed / 18.0);  // 정규화
  const shaftLen = 18 + 16 * len;                // 18~34 px
  return (
    <div className="flex items-center gap-2 px-2 py-1 text-[11px] font-mono
                    bg-black/40 border border-line rounded">
      <svg width="44" height="44" viewBox="-22 -22 44 44">
        <g transform={`rotate(${rot})`}>
          <line x1="0" y1={shaftLen / 2} x2="0" y2={-shaftLen / 2}
                stroke="currentColor" strokeWidth="2" className={b.color} />
          <polygon points={`-4,${-shaftLen / 2 + 6} 0,${-shaftLen / 2} 4,${-shaftLen / 2 + 6}`}
                   fill="currentColor" className={b.color} />
        </g>
        <circle r="1.5" fill="currentColor" className="text-dim" />
      </svg>
      <div className="flex flex-col leading-tight">
        <span className={`text-[10px] tracking-widest ${b.color}`}>WIND · B{b.idx}</span>
        <span>{wind.speed.toFixed(1)} m/s</span>
        <span className="text-dim">{wind.dir_deg.toFixed(0)}° · {b.label}</span>
      </div>
    </div>
  );
}
