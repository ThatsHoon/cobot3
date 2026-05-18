"use client";

import { useEffect, useState } from "react";

// 디버그 전용 페이지 — Lichtblick(Foxglove) 뷰어를 iframe 으로 임베드한다.
// URL 을 window.location.hostname 기준으로 동적 구성 → LAN 어느 PC 에서든
// C2 PC(Lichtblick:8080, foxglove_bridge:8765)를 정확히 가리킴.
export default function DebugPage() {
  const [src, setSrc] = useState<string>("");
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
    <main
      className="relative z-10 flex flex-col gap-3"
      style={{ height: "100dvh", padding: "0.75rem" }}
    >
      <header className="flex items-end justify-between flex-shrink-0">
        <div>
          <h1 className="font-display text-xl tracking-[0.28em] text-phos">
            DEBUG · FOXGLOVE
          </h1>
          <p className="text-[10px] text-dim tracking-[0.35em] mt-0.5">
            LICHTBLICK · ROS2 텔레메트리/영상 진단
          </p>
        </div>
        <div className="text-right text-[10px] text-dim leading-relaxed">
          <span className="text-ink">{lichtblickUrl || "…"}</span>
          <br />
          <span>{wsUrl || "ws://…:8765"}</span>
          <span className="ml-1 text-phos">(foxglove_bridge)</span>
        </div>
      </header>

      <div className="panel flex-1 min-h-0 flex flex-col overflow-hidden">
        <div className="panel-hd flex-shrink-0">
          <span>VIEWER</span>
          <span className="text-phos">LIVE</span>
        </div>
        <div className="flex-1 min-h-0 bg-black">
          {src ? (
            <iframe
              src={src}
              title="Lichtblick"
              className="w-full h-full border-0"
              allow="fullscreen"
            />
          ) : (
            <div className="w-full h-full grid place-items-center text-dim text-xs tracking-[0.3em]">
              INITIALIZING…
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
