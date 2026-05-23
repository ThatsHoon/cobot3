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

const MODE_TONE: Record<string, string> = {
  PATROL: "text-phos",
  HOME: "text-amber",
  IDLE: "text-ink-2",
  STOPPED: "text-amber",
  ALERT_STOP: "text-alert animate-pulse",
  ROUTING: "text-phos",
  WAITING_FOR_NAV2: "text-amber",
};

/** 텔레메트리 스트립 — 1줄 핵심 상태 표시 */
export default function TelemetryStrip({
  state, gps, odom, patrol,
}: {
  state: StateData | null;
  gps: GpsData | null;
  odom: OdomData | null;
  patrol: PatrolStatePayload | null;
}) {
  const battery = state?.battery ?? null;
  const batteryPct = battery != null ? Math.round(battery) : null;
  const batTone =
    batteryPct == null ? "text-dim" :
    batteryPct < 20 ? "text-alert" :
    batteryPct < 50 ? "text-amber" : "text-phos";

  const mode = patrol?.mode ?? state?.mode ?? "—";
  const modeCls = MODE_TONE[mode] ?? "text-ink-2";

  const yawDeg = odom?.x != null ? ((odom.yaw ?? 0) * 180 / Math.PI).toFixed(0) : null;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6
                    border-b border-line
                    bg-gradient-to-b from-black/40 to-transparent">
      <Cell>
        <span className="k">MODE</span>
        <span className={`v ${modeCls}`}>{mode}</span>
      </Cell>

      <Cell>
        <span className="k">GAIT</span>
        <span className="v">{state?.gait?.toUpperCase() ?? "—"}</span>
      </Cell>

      <Cell>
        <span className="k">BATTERY</span>
        <span className={`v ${batTone}`}>
          {batteryPct != null ? batteryPct : "—"}
          <span className="u">%</span>
        </span>
        {batteryPct != null && (
          <div className="mt-1 h-[3px] bg-line">
            <div
              className={
                batteryPct < 20 ? "h-full bg-alert" :
                batteryPct < 50 ? "h-full bg-amber" : "h-full bg-phos"
              }
              style={{ width: `${batteryPct}%` }} />
          </div>
        )}
      </Cell>

      <Cell>
        <span className="k">WAYPOINT</span>
        <span className="v truncate">
          {patrol?.waypoint
            ? <>({patrol.waypoint.x.toFixed(0)}, {patrol.waypoint.y.toFixed(0)})</>
            : "—"}
        </span>
      </Cell>

      <Cell>
        <span className="k">POSE</span>
        <span className="v truncate">
          {odom?.x != null
            ? <>({odom.x.toFixed(1)}, {odom.y!.toFixed(1)})
                <span className="u ml-2">{yawDeg}°</span>
              </>
            : "—"}
        </span>
      </Cell>

      <Cell>
        <span className="k">GPS</span>
        <span className="v truncate" title={gps?.lat != null ? `${gps.lat}, ${gps.lon}` : ""}>
          {gps?.lat != null
            ? <>{gps.lat.toFixed(5)}, {gps.lon!.toFixed(5)}</>
            : "—"}
        </span>
        {gps?.alt != null && (
          <span className="text-[8.5px] tracking-[0.2em] text-dim mt-0.5">
            ALT {gps.alt.toFixed(0)}<span className="ml-0.5">m</span>
          </span>
        )}
      </Cell>
    </div>
  );
}

function Cell({ children }: { children: React.ReactNode }) {
  return (
    <div className="stat min-w-0
                    border-line
                    [&:not(:first-child)]:border-l
                    sm:[&:nth-child(3n+1)]:border-l-0 sm:[&:not(:first-child)]:border-l
                    lg:[&:nth-child(n)]:border-l-0 lg:[&:not(:first-child)]:border-l">
      {children}
    </div>
  );
}
