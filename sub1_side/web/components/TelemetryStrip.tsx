"use client";
import { PatrolStatePayload } from "@/lib/api";

type StateData = {
  mode?: string;
  gait?: string;
  battery?: number;
  waypoint?: number;
  extra?: Record<string, unknown>;
};

type GpsData = { lat?: number; lon?: number; alt?: number };
type OdomData = { x?: number; y?: number; z?: number; yaw?: number };

/** 텔레메트리 스트립 — 1줄 핵심 상태 표시 (mode/gait/battery/pose/gps). */
export default function TelemetryStrip({
  state,
  gps,
  odom,
  patrol,
}: {
  state: StateData | null;
  gps: GpsData | null;
  odom: OdomData | null;
  patrol: PatrolStatePayload | null;
}) {
  const battery = state?.battery ?? null;
  const batteryPct = battery != null ? Math.round(battery) : null;
  const batCol =
    batteryPct == null ? "text-dim" :
    batteryPct < 20 ? "text-alert" :
    batteryPct < 50 ? "text-amber" : "text-phos";

  const mode = patrol?.mode ?? state?.mode ?? "—";
  const modeCol = mode === "ALERT_STOP" ? "text-alert animate-pulse" :
                  mode === "PATROL" ? "text-phos" :
                  mode === "HOME" ? "text-sky-400" : "text-dim";

  return (
    <div className="flex items-stretch divide-x divide-line border-b
                    border-line bg-black/30 text-[11px] font-mono">
      <Cell label="mode">
        <span className={modeCol}>{mode}</span>
      </Cell>
      <Cell label="gait">
        <span className="text-ink">{state?.gait ?? "—"}</span>
      </Cell>
      <Cell label="battery">
        {batteryPct == null
          ? <span className="text-dim">—</span>
          : <span className={batCol}>{batteryPct}%</span>}
      </Cell>
      <Cell label="waypoint">
        <span className="text-ink">
          {patrol?.waypoint
            ? `(${patrol.waypoint.x.toFixed(0)}, ${patrol.waypoint.y.toFixed(0)})`
            : "—"}
        </span>
      </Cell>
      <Cell label="pose">
        <span className="text-ink">
          {odom?.x != null
            ? `(${odom.x.toFixed(1)}, ${odom.y!.toFixed(1)}) ${
                ((odom.yaw ?? 0) * 180 / Math.PI).toFixed(0)}°`
            : "—"}
        </span>
      </Cell>
      <Cell label="gps">
        <span className="text-ink">
          {gps?.lat != null
            ? `${gps.lat.toFixed(5)}, ${gps.lon!.toFixed(5)}`
            : "—"}
        </span>
      </Cell>
    </div>
  );
}

function Cell({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col justify-center px-3 py-1.5 flex-1 min-w-0">
      <span className="text-[9px] text-dim uppercase tracking-widest">{label}</span>
      <span className="truncate">{children}</span>
    </div>
  );
}
