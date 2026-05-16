"use client";

type S = {
  state?: { mode?: string; gait?: string; battery?: number; waypoint?: number };
  gps?: { lat?: number; lon?: number };
};

function Tile({
  k,
  v,
  tone,
}: {
  k: string;
  v: string;
  tone?: string;
}) {
  return (
    <div className="tile">
      <div className="k">{k}</div>
      <div className="v" style={{ color: tone || "var(--ink)" }}>
        {v}
      </div>
    </div>
  );
}

/** 대응 가능 여부를 한눈에 — MODE/배터리/링크/웨이포인트/GPS 컴팩트 타일. */
export default function ReadinessStrip({
  s,
  wsOk,
}: {
  s: S;
  wsOk: boolean;
}) {
  const st = s.state || {};
  const mode = st.mode || "—";
  const batt = st.battery ?? null;
  const modeTone =
    mode === "FIRE"
      ? "var(--alert)"
      : mode === "AIM"
      ? "var(--amber)"
      : mode === "—"
      ? "var(--dim)"
      : "var(--phos)";
  return (
    <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
      <Tile k="MODE" v={mode} tone={modeTone} />
      <Tile
        k="BATTERY"
        v={batt == null ? "—" : `${batt.toFixed(0)}%`}
        tone={
          batt != null && batt < 20 ? "var(--alert)" : "var(--ink)"
        }
      />
      <Tile
        k="LINK"
        v={wsOk ? "UP" : "DOWN"}
        tone={wsOk ? "var(--phos)" : "var(--alert)"}
      />
      <Tile k="WAYPOINT" v={st.waypoint != null ? `#${st.waypoint}` : "—"} />
      <Tile
        k="GPS"
        v={
          s.gps?.lat != null
            ? `${s.gps.lat.toFixed(4)},${s.gps.lon?.toFixed(4)}`
            : "NO FIX"
        }
        tone={s.gps?.lat != null ? "var(--ink)" : "var(--amber)"}
      />
    </div>
  );
}
