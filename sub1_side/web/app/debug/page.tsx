"use client";

import { useCallback, useState } from "react";
import TopicHealthMonitor from "@/components/TopicHealthMonitor";
import ImmersiveCameraView from "@/components/ImmersiveCameraView";
import RawJsonInspector from "@/components/RawJsonInspector";
import EventLog from "@/components/EventLog";
import DiagnosticsStrip from "@/components/DiagnosticsStrip";
import DualSenseStatus from "@/components/DualSenseStatus";
import { C2Event, useEvents } from "@/lib/api";

/** 디버그 페이지 — Immersive(URDF+sphere) + Topic Health + RawJSON + DualSense.
 *
 * 2026-05-21 변경: Lichtblick iframe 제거 (사용 안 함). Immersive 가 row1 전체.
 *
 * 레이아웃 (12-column grid):
 *   row1 (12col, big): ImmersiveCameraView (Go2 URDF + rear/inspect sphere, 북향 고정)
 *   row2 좌 5col: TopicHealthMonitor (rx 카운터)
 *   row2 중 4col: RawJsonInspector (patrol/landmarks/intruders JSON)
 *   row2 우 3col: DualSenseStatus
 *   row3 (12col): DiagnosticsStrip (관절 메트릭)
 *   row4 (12col, 160px): EventLog
 */
export default function DebugPage() {
  const [eventStream, setEventStream] = useState<C2Event[]>([]);
  const [legQ, setLegQ] = useState<number[]>([]);
  const [armQ] = useState<number[]>([]);
  const [yaw, setYaw] = useState(0);

  const onEvent = useCallback((e: C2Event) => {
    setEventStream((p) => [...p.slice(-149), e]);
    if (e.type === "state") {
      const d: any = e.data;
      const od = d?.leg_q || d?.legs;
      if (Array.isArray(od)) setLegQ(od);
      const y = d?.odom?.yaw;
      if (typeof y === "number") setYaw(y);
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
            IMMERSIVE · TOPIC-HEALTH · RAW-JSON · DUALSENSE
          </span>
        </div>
        <div className="text-right text-[10px] text-dim font-mono leading-tight">
          <div>yaw <span className="text-ink">{(yaw * 180 / Math.PI).toFixed(1)}°</span></div>
        </div>
      </header>

      <div className="flex-1 min-h-0 grid grid-cols-12 gap-2 p-2"
           style={{ gridTemplateRows: "minmax(0,3.5fr) minmax(0,1fr) auto auto" }}>
        {/* row1: ImmersiveCameraView 전체 (Lichtblick 제거) */}
        <div className="col-span-12 min-h-0">
          <ImmersiveCameraView yaw={yaw} />
        </div>

        {/* row2 좌: 토픽 헬스 모니터 */}
        <div className="col-span-5 min-h-0">
          <TopicHealthMonitor />
        </div>

        {/* row2 중: Raw JSON 인스펙터 */}
        <div className="col-span-4 min-h-0">
          <RawJsonInspector />
        </div>

        {/* row2 우: DualSense */}
        <div className="col-span-3 min-h-0 flex flex-col gap-2">
          <DualSenseStatus />
        </div>

        {/* row3: 관절 메트릭 (DiagnosticsStrip) */}
        <div className="col-span-12">
          <DiagnosticsStrip armQ={armQ} legQ={legQ} />
        </div>

        {/* row4: EventLog */}
        <div className="col-span-12 h-[160px]">
          <EventLog events={eventStream} />
        </div>
      </div>
    </main>
  );
}
