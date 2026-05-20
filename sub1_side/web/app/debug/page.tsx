"use client";

import { useEffect, useState, useCallback } from "react";
import TopicHealthMonitor from "@/components/TopicHealthMonitor";
import RawJsonInspector from "@/components/RawJsonInspector";
import EventLog from "@/components/EventLog";
import DiagnosticsStrip from "@/components/DiagnosticsStrip";
import DualSenseStatus from "@/components/DualSenseStatus";
import { C2Event, useEvents } from "@/lib/api";

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
  const [eventStream, setEventStream] = useState<C2Event[]>([]);
  const [legQ, setLegQ] = useState<number[]>([]);
  const [armQ, setArmQ] = useState<number[]>([]);

  useEffect(() => {
    const host = window.location.hostname;
    const lb = `http://${host}:8080`;
    const ws = `ws://${host}:8765`;
    setLichtblickUrl(lb);
    setWsUrl(ws);
    setSrc(`${lb}/?ds=foxglove-websocket&ds.url=${encodeURIComponent(ws)}`);
  }, []);

  const onEvent = useCallback((e: C2Event) => {
    setEventStream((p) => [...p.slice(-149), e]);
    if (e.type === "state") {
      const od = (e.data as any)?.leg_q || (e.data as any)?.legs;
      if (Array.isArray(od)) setLegQ(od);
    }
  }, []);
  useEvents(onEvent);

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

      <div className="flex-1 min-h-0 grid grid-cols-12 gap-2 p-2"
           style={{ gridTemplateRows: "minmax(0,3.5fr) minmax(0,1fr) auto auto" }}>
        {/* row1 전체 (12col): Lichtblick — Go2 URDF + 3D + 카메라 + Plot 통합.
            layout.json 의 3D!go2 (62%) + Image×3 + Plot×2 로 Spot SDK 스타일
            시각화. CRT scanline 오버레이로 watch-officer 미감.
            (2026-05-20 TripleCameraView 제거 + 높이 확대 3.5fr) */}
        <div className="col-span-12 min-h-0 bg-black border border-line/40
                        rounded-sm overflow-hidden relative">
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
          {/* scanline + vignette 오버레이 */}
          <div className="absolute inset-0 pointer-events-none opacity-12"
               style={{
                 background: "repeating-linear-gradient(0deg, rgba(0,255,128,0) 0px, rgba(0,255,128,0) 2px, rgba(0,255,128,0.06) 3px, rgba(0,255,128,0) 4px)",
               }} />
          <div className="absolute inset-0 pointer-events-none"
               style={{
                 boxShadow: "inset 0 0 120px rgba(0,0,0,0.6)",
               }} />
        </div>

        {/* row2 좌: 토픽 헬스 모니터 */}
        <div className="col-span-5 min-h-0">
          <TopicHealthMonitor />
        </div>

        {/* row2 중: Raw JSON 인스펙터 */}
        <div className="col-span-4 min-h-0">
          <RawJsonInspector />
        </div>

        {/* row2 우: DualSense + 추가 정보 */}
        <div className="col-span-3 min-h-0 flex flex-col gap-2">
          <DualSenseStatus />
        </div>

        {/* row3: 관절 메트릭 (DiagnosticsStrip) */}
        <div className="col-span-12">
          <DiagnosticsStrip armQ={armQ} legQ={legQ} />
        </div>

        {/* row4: EventLog (로그) */}
        <div className="col-span-12 h-[160px]">
          <EventLog events={eventStream} />
        </div>
      </div>
    </main>
  );
}
