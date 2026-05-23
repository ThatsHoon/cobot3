"use client";
import { useEffect, useState } from "react";
import { AlertPayload } from "@/lib/api";

type AnimalAlertRow = {
  ts: string;
  label: string;
  conf: number;
  bbox?: [number, number, number, number];
  ack?: boolean;
};

const MAX_ROWS = 20;

export default function AnimalAlertsLog({
  liveEvents,
}: {
  /** WS animal_alert 이벤트들. page.tsx 가 누적 푸시. */
  liveEvents: { ts: string; data: AlertPayload & { label: string } }[];
}) {
  const [rows, setRows] = useState<AnimalAlertRow[]>([]);

  useEffect(() => {
    if (!liveEvents.length) return;
    const last = liveEvents[liveEvents.length - 1];
    setRows((prev) => [{
      ts: last.ts,
      label: last.data.label,
      conf: last.data.confidence,
      bbox: last.data.bbox_xyxy,
      ack: false,
    }, ...prev].slice(0, MAX_ROWS));
  }, [liveEvents]);

  return (
    <div className="panel h-full flex flex-col">
      <div className="panel-hd">
        <span>ANIMAL ALERTS</span>
        <span className="text-[11px] text-dim">
          {rows.filter(r => !r.ack).length} open
        </span>
      </div>
      <div className="px-2 py-1 h-[192px] overflow-auto text-[11px] font-mono">
        {rows.length === 0 && (
          <div className="text-dim px-2 py-1">동물 알람 없음</div>
        )}
        {rows.map((r, i) => (
          <div key={i}
               className={`flex items-center justify-between gap-2 px-2 py-1.5 border-b border-line ` +
                          `${!r.ack ? "animal-unack-pulse" : ""} ` +
                          `${r.ack ? "opacity-30" : ""}`}>
            <div className="flex-1 min-w-0">
              <div className="text-amber font-display tracking-[0.04em]">
                {r.label.toUpperCase()}
                <span className="text-dim ml-2 tabular">
                  conf <span className="text-ink-2">{r.conf.toFixed(2)}</span>
                </span>
              </div>
              <div className="text-dim text-[10px] tabular">
                {new Date(r.ts).toLocaleTimeString("en-GB")}
              </div>
            </div>
            {!r.ack && (
              <button
                onClick={() => setRows(p => p.map((x, j) =>
                  j === i ? { ...x, ack: true } : x))}
                className="btn !py-1 !px-2 !text-[9.5px] !tracking-[0.18em]"
                title="acknowledge">
                ACK
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
