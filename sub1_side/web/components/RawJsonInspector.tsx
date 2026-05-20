"use client";
import { useEffect, useState } from "react";
import { getApiBase } from "@/lib/api";

/**
 * Raw JSON inspector — String JSON 토픽들의 최신 메시지를 펴서 표시.
 * patrol_state / landmarks / intruders / state(robot) — 1Hz polling.
 */
const KEYS = ["patrol_state", "landmarks", "intruders", "state", "odom", "gps"];

export default function RawJsonInspector() {
  const [latest, setLatest] = useState<Record<string, any>>({});
  const [selected, setSelected] = useState<string>("patrol_state");

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const r = await fetch(`${getApiBase()}/c2/sample`, { cache: "no-store" });
        if (alive && r.ok) {
          const d = await r.json();
          setLatest(d.latest || {});
        }
      } catch {}
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const value = latest[selected];
  const pretty = value !== undefined
    ? JSON.stringify(value, null, 2)
    : "(no data yet)";

  return (
    <div className="panel h-full flex flex-col">
      <div className="panel-hd">
        <span>RAW JSON INSPECTOR</span>
        <span className="text-[10px] text-dim">1Hz · ros_bridge.latest</span>
      </div>
      <div className="px-2 pt-1 flex flex-wrap gap-1">
        {KEYS.map((k) => (
          <button
            key={k}
            onClick={() => setSelected(k)}
            className={`text-[10px] px-2 py-0.5 rounded font-mono ` +
              (selected === k
                ? "bg-phos/20 text-phos border border-phos"
                : "bg-zinc-800 text-dim hover:bg-zinc-700 border border-transparent")}>
            {k}
          </button>
        ))}
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto p-2">
        <pre className="text-[10px] font-mono text-ink whitespace-pre-wrap leading-tight">
          {pretty}
        </pre>
      </div>
    </div>
  );
}
