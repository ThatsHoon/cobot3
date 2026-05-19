"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

const SpotSurroundView = dynamic(
  () => import("@/components/SpotSurroundView"),
  { ssr: false, loading: () => <div className="w-full h-full grid place-items-center text-dim text-xs tracking-[0.3em]">LOADING 3D…</div> }
);

export default function DebugPage() {
  const [src, setSrc] = useState<string>("");
  const [lichtblickUrl, setLichtblickUrl] = useState("");
  const [wsUrl, setWsUrl] = useState("");
  const [apiBase, setApiBase] = useState("");

  useEffect(() => {
    const host = window.location.hostname;
    const lb = `http://${host}:8080`;
    const ws = `ws://${host}:8765`;
    setLichtblickUrl(lb);
    setWsUrl(ws);
    setSrc(`${lb}/?ds=foxglove-websocket&ds.url=${encodeURIComponent(ws)}`);
    setApiBase(`http://${host}:8000`);
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

      {/* 3D Surround View */}
      <div className="panel flex-shrink-0 flex flex-col overflow-hidden" style={{ height: "280px" }}>
        <div className="panel-hd flex-shrink-0">
          <span>SPOT · 3D SURROUND VIEW</span>
          <span className="text-phos">LIVE YAW</span>
        </div>
        <div className="flex-1 min-h-0 bg-[#080c10]">
          {apiBase ? (
            <SpotSurroundView apiBase={apiBase} />
          ) : (
            <div className="w-full h-full grid place-items-center text-dim text-xs tracking-[0.3em]">
              INITIALIZING…
            </div>
          )}
        </div>
      </div>

      {/* Lichtblick iframe */}
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
