"use client";
import { useEffect, useState } from "react";
import { C2Event } from "@/lib/api";

type LogEntry = { ts: string; type: string; summary: string };

const MAX = 100;

function summarize(e: C2Event): string {
  switch (e.type) {
    case "state":         return `mode=${e.data?.mode ?? "?"}`;
    case "gps":           return `gps lat=${e.data.lat.toFixed(4)}`;
    case "log":           return `${e.name}: ${e.msg.slice(0, 80)}`;
    case "detection":     return `${e.items?.length ?? 0} detections`;
    case "fire":          return `${e.hit ? "HIT" : "MISS"} → ${e.target}`;
    case "alert":         return `ALERT ${e.data.event} conf=${e.data.confidence.toFixed(2)}`;
    case "animal_alert":  return `ANIMAL ${e.data.label} conf=${e.data.confidence.toFixed(2)}`;
    case "patrol_state":  return `patrol=${e.data.mode}`;
    case "fall_alert": {
      const d = (e as any).data ?? {};
      return d.reason
        ? `${d.state}: ${d.reason}`
        : `${d.state} (${d.event})`;
    }
    case "intruder_state": {
      const items = Array.isArray(e.data) ? e.data : (e.data?.items ?? []);
      return `intruder×${items.length}`;
    }
    case "landmarks":     return `landmarks zone=${e.data.zone ?? "cube"}`;
    default:              return String((e as any).type);
  }
}

export default function EventLog({
  events,
}: {
  /** page.tsx 에서 모든 C2Event 를 push (가장 최근이 끝). */
  events: C2Event[];
}) {
  const [rows, setRows] = useState<LogEntry[]>([]);
  // detailed=off (default): type==='log' 만. on: 전체.
  // 2026-05-26 사용자 요청 — wind_state/diag 노이즈 숨기기.
  const [detailed, setDetailed] = useState(false);

  useEffect(() => {
    if (!events.length) return;
    const last = events[events.length - 1];
    const ts = (last as any).ts ?? new Date().toISOString();
    setRows((prev) => [{
      ts, type: last.type, summary: summarize(last),
    }, ...prev].slice(0, MAX));
  }, [events]);

  const visible = detailed ? rows : rows.filter((r) => r.type === "log");

  return (
    <div className="panel h-full flex flex-col">
      <div className="panel-hd flex items-center justify-between gap-2">
        <span>EVENT LOG</span>
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-dim">
            {visible.length}/{rows.length}
          </span>
          <button
            type="button"
            onClick={() => setDetailed((v) => !v)}
            className={[
              "text-[10px] px-1.5 py-0.5 border rounded",
              detailed
                ? "border-phos text-phos bg-phos/10"
                : "border-line text-dim hover:text-ink",
            ].join(" ")}
            title="off: log only · on: 전체 이벤트"
          >
            detailed: {detailed ? "ON" : "OFF"}
          </button>
        </div>
      </div>
      <div className="px-2 py-1 text-[10px] font-mono flex-1 overflow-auto">
        {visible.length === 0 && (
          <div className="text-dim px-2 py-1">
            {rows.length === 0 ? "이벤트 없음" : "(off — log 만 표시)"}
          </div>
        )}
        {visible.map((r, i) => (
          <div key={i} className="flex gap-2 px-2 py-0.5 border-b border-line/40">
            <span className="text-dim shrink-0">
              {new Date(r.ts).toLocaleTimeString().slice(-8)}
            </span>
            <span className="text-phos w-20 shrink-0">{r.type}</span>
            <span className="text-ink truncate">{r.summary}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
