"use client";
import { useEffect, useState } from "react";
import { ROBOT_ID, LandmarksPayload } from "@/lib/api";

/** 상단 헤더 — robot id, WS 연결, zone, 현지 시간 */
export default function StatusHeader({
  wsOk,
  landmarks,
}: {
  wsOk: boolean;
  landmarks: LandmarksPayload | null;
}) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const iv = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(iv);
  }, []);

  const zone = landmarks?.zone ?? "?";
  const time = now.toLocaleTimeString();

  return (
    <header className="flex items-center justify-between h-12 px-3
                       border-b border-line bg-black/40">
      <div className="flex items-baseline gap-3">
        <h1 className="font-display text-base tracking-[0.28em] text-phos">
          GP · C2
        </h1>
        <span className="text-[10px] text-dim tracking-[0.3em]">
          QUADRUPED OPS CONSOLE
        </span>
      </div>
      <div className="flex items-center gap-4 text-[11px] font-mono">
        <span><span className="text-dim">robot </span>
          <span className="text-ink">{ROBOT_ID.toUpperCase()}</span></span>
        <span><span className="text-dim">zone </span>
          <span className={zone === "dmz" ? "text-amber" : "text-phos"}>
            {zone.toUpperCase()}
          </span></span>
        <span className={wsOk ? "text-phos" : "text-alert"}>
          {wsOk ? "STREAM ●" : "OFFLINE ○"}
        </span>
        <span className="text-dim">{time}</span>
      </div>
    </header>
  );
}
