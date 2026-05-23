"use client";
import { WindState } from "@/lib/api";

/** 풍속·풍향 시각화 — 화살표 + 보퍼트 라벨 + 수치. 헤더 row(h-14) 안에 정렬. */
function beaufort(speed: number): { idx: number; label: string; tone: string } {
  if (speed < 0.3)  return { idx: 0, label: "CALM",       tone: "text-dim"   };
  if (speed < 1.6)  return { idx: 1, label: "LIGHT AIR",  tone: "text-ink-2" };
  if (speed < 3.4)  return { idx: 2, label: "LIGHT BR",   tone: "text-ink-2" };
  if (speed < 5.5)  return { idx: 3, label: "GENTLE BR",  tone: "text-phos"  };
  if (speed < 8.0)  return { idx: 4, label: "MOD BREEZE", tone: "text-phos"  };
  if (speed < 10.8) return { idx: 5, label: "FRESH BR",   tone: "text-amber" };
  if (speed < 13.9) return { idx: 6, label: "STRONG BR",  tone: "text-amber" };
  if (speed < 17.2) return { idx: 7, label: "NEAR GALE",  tone: "text-alert" };
  return                  { idx: 8, label: "GALE",       tone: "text-alert" };
}

export default function WindGauge({ wind }: { wind: WindState | null }) {
  if (!wind) {
    return (
      <div className="flex items-center gap-2 px-3 h-full text-[10px] text-dim w-[170px] flex-shrink-0 font-mono">
        <span className="tracking-[0.22em]">WIND</span><span>—</span>
      </div>
    );
  }
  const b = beaufort(wind.speed);
  // dir_deg 는 atan2(vy,vx) — east=0°, north=90°. CSS rotate 시계방향 보정.
  const rot = 90 - wind.dir_deg;
  const len = Math.min(1.0, wind.speed / 18.0);
  const shaftLen = 14 + 14 * len;
  return (
    <div className="flex items-center gap-2 px-2.5 h-full text-[10px] font-mono
                    border-l border-line w-[170px] flex-shrink-0">
      <svg width="32" height="32" viewBox="-16 -16 32 32" className="flex-shrink-0">
        <circle r="14" fill="none" stroke="var(--line)" strokeWidth="0.6" />
        <g transform={`rotate(${rot})`}>
          <line x1="0" y1={shaftLen / 2} x2="0" y2={-shaftLen / 2}
                stroke="currentColor" strokeWidth="1.6" className={b.tone} />
          <polygon points={`-3,${-shaftLen / 2 + 5} 0,${-shaftLen / 2} 3,${-shaftLen / 2 + 5}`}
                   fill="currentColor" className={b.tone} />
        </g>
        <circle r="1.2" fill="currentColor" className="text-dim" />
      </svg>
      <div className="flex flex-col leading-tight min-w-0 overflow-hidden tabular">
        <span className={`text-[8.5px] tracking-[0.22em] ${b.tone}`}>WIND · B{b.idx}</span>
        <span className="text-ink">{wind.speed.toFixed(1)}<span className="text-dim ml-1">m/s</span></span>
        <span className="text-dim text-[8.5px] tracking-[0.18em]">
          {wind.dir_deg.toFixed(0)}° · {b.label}
        </span>
      </div>
    </div>
  );
}
