"use client";
import { useEffect, useState } from "react";
import { getApiBase } from "@/lib/api";

type Status = {
  connected: boolean;
  name: string;
  speed_scale: number;
  pygame_available: boolean;
  polling_hz: number;
  limits: { vx: number; vy: number; wz: number };
  inspect?: { pan_deg: number; tilt_deg: number; limit_deg: number };
  mapping: Record<string, string>;
};

export default function DualSenseStatus() {
  const [st, setSt] = useState<Status | null>(null);
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const r = await fetch(`${getApiBase()}/c2/dualsense/status`,
                              { cache: "no-store" });
        if (alive && r.ok) setSt(await r.json());
      } catch {}
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const dot = st?.connected ? "bg-emerald-400" : "bg-zinc-600";
  const label = st?.connected ? st.name : "미연결";

  return (
    <div className="panel">
      <div className="panel-hd">
        <span>DUALSENSE</span>
        <span className="flex items-center gap-1.5 text-[10px] text-dim">
          <span className={`inline-block w-2 h-2 rounded-full ${dot}`}></span>
          {label}
          {st?.connected && (
            <span className="text-ink ml-2">SPD ×{st.speed_scale.toFixed(2)}</span>
          )}
        </span>
      </div>
      <div className="p-3 text-[10px] text-dim space-y-1">
        {!st?.pygame_available && (
          <div className="text-amber">⚠ pygame 미설치 — `pip install pygame`</div>
        )}
        <div className="grid grid-cols-2 gap-x-2 gap-y-0.5">
          <span>L-stick</span>    <span className="text-ink">INSPECT pan/tilt (±70°)</span>
          <span>R-stick L/R</span><span className="text-ink">좌/우 회전</span>
          <span>D-pad ↑↓</span>   <span className="text-ink">전후진</span>
          <span>D-pad ←→</span>   <span className="text-ink">좌우 평행</span>
          <span>L2 hold</span>    <span className="text-ink">속도 −</span>
          <span>R2 hold</span>    <span className="text-ink">속도 +</span>
          <span>× (Cross)</span>  <span className="text-ink">정지/재개 토글</span>
          <span>△ (Triangle)</span><span className="text-ink">출격</span>
          <span>○ (Circle)</span> <span className="text-ink">복귀</span>
        </div>
        {st?.inspect && (
          <div className="pt-1 mt-1 border-t border-line text-[10px] text-dim">
            INSPECT: pan {st.inspect.pan_deg.toFixed(0)}° · tilt {st.inspect.tilt_deg.toFixed(0)}°
          </div>
        )}
      </div>
    </div>
  );
}
