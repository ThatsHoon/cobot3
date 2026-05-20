"use client";

import { useEffect, useState } from "react";
import TripleCameraView from "@/components/TripleCameraView";
import TopicHealthMonitor from "@/components/TopicHealthMonitor";
import RawJsonInspector from "@/components/RawJsonInspector";

/** 디버그 페이지 — Lichtblick(Foxglove) + cobot3 고유 시각화 통합.
 *
 * 레이아웃 (12-column grid):
 *   상단 좌 8col: Lichtblick iframe (3D/Plot/TF/Image)
 *   상단 우 4col: TripleCameraView (REAR/INSPECT/OVERHEAD MJPEG)
 *   하단 좌 8col: TopicHealthMonitor (rx 카운터 + 상태)
 *   하단 우 4col: RawJsonInspector (patrol/landmarks/intruders JSON)
 *
 * Lichtblick layout 은 `sub1_side/lichtblick/layout.json` (URDF + Plot×3).
 * cobot3 패널들은 /c2/sample endpoint (1Hz polling) 로 ros_bridge.latest 읽음.
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
      <header className="flex items-center justify-between h-10 px-3
                         border-b border-line bg-black/40 flex-shrink-0">
        <div className="flex items-baseline gap-3">
          <h1 className="font-display text-base tracking-[0.28em] text-phos">
            DEBUG · MULTI-PANEL
          </h1>
          <span className="text-[10px] text-dim tracking-[0.3em]">
            LICHTBLICK · 3-CAMERA · TOPIC-HEALTH · RAW-JSON
          </span>
        </div>
        <div className="text-right text-[10px] text-dim font-mono leading-tight">
          <div className="text-ink">{lichtblickUrl || "…"}</div>
          <div>{wsUrl || "ws://…:8765"}
            <span className="ml-1 text-phos">(foxglove_bridge)</span></div>
        </div>
      </header>

      <div className="flex-1 min-h-0 grid grid-cols-12 grid-rows-2 gap-2 p-2">
        {/* 상단 좌: Lichtblick (3D + Plot + TF + Image) */}
        <div className="col-span-8 row-span-1 min-h-0 bg-black border border-line/40">
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

        {/* 상단 우: 3-카메라 grid */}
        <div className="col-span-4 row-span-1 min-h-0">
          <TripleCameraView />
        </div>

        {/* 하단 좌: 토픽 헬스 모니터 */}
        <div className="col-span-8 row-span-1 min-h-0">
          <TopicHealthMonitor />
        </div>

        {/* 하단 우: Raw JSON 인스펙터 */}
        <div className="col-span-4 row-span-1 min-h-0">
          <RawJsonInspector />
        </div>
      </div>
    </main>
  );
}
