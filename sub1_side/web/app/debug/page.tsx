"use client";

import { useEffect, useState } from "react";

/** 디버그 페이지 — Lichtblick(Foxglove) iframe 풀스크린.
 *
 * 패널 구성은 `sub1_side/lichtblick/layout.json` 의 default-layout 으로 결정:
 * 좌측 3D!go2 (URDF + PointCloud + TF + odom follow) + 우측 Plot×3
 * (joint_position / foot_position / cmd_vel) + Image 패널.
 * 이미지 #5 (Lichtblick 표준) 와 동일 퀄리티.
 */
export default function DebugPage() {
  const [src, setSrc] = useState("");
  const [lichtblickUrl, setLichtblickUrl] = useState("");
  const [wsUrl, setWsUrl] = useState("");

  useEffect(() => {
    const host = window.location.hostname;
    const lb = `http://${host}:8080`;
    const ws = `ws://${host}:8765`;
    setLichtblickUrl(lb);
    setWsUrl(ws);
    setSrc(`${lb}/?ds=foxglove-websocket&ds.url=${encodeURIComponent(ws)}`);
  }, []);

  return (
    <main className="relative z-10 flex flex-col"
          style={{ height: "100dvh" }}>
      <header className="flex items-center justify-between h-12 px-3
                         border-b border-line bg-black/40 flex-shrink-0">
        <div className="flex items-baseline gap-3">
          <h1 className="font-display text-base tracking-[0.28em] text-phos">
            DEBUG · FOXGLOVE
          </h1>
          <span className="text-[10px] text-dim tracking-[0.3em]">
            LICHTBLICK · 3D · JOINT · CMD_VEL · IMAGE
          </span>
        </div>
        <div className="text-right text-[10px] text-dim font-mono leading-tight">
          <div className="text-ink">{lichtblickUrl || "…"}</div>
          <div>{wsUrl || "ws://…:8765"}
            <span className="ml-1 text-phos">(foxglove_bridge)</span></div>
        </div>
      </header>
      <div className="flex-1 min-h-0 bg-black">
        {src ? (
          <iframe
            src={src}
            title="Lichtblick"
            className="w-full h-full border-0"
            allow="fullscreen"
          />
        ) : (
          <div className="w-full h-full grid place-items-center text-dim
                          text-xs tracking-[0.3em]">
            INITIALIZING…
          </div>
        )}
      </div>
    </main>
  );
}
