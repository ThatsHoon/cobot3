"use client";
import { useEffect, useState } from "react";
import { Activity, CircleDot, CircleSlash } from "lucide-react";
import { getApiBase } from "@/lib/api";

/**
 * Topic health monitor — 1Hz polling /c2/sample → ros_bridge.latest + rx
 * 카운터로 토픽별 수신 상태 시각화.
 *
 * 색상: live (rx 증가) / stale (rx 정체 >5s) / dead (rx=0)
 */
type Sample = {
  latest: Record<string, any>;
  rx: Record<string, number> | null;
};

const TOPICS = [
  { key: "state",         topic: "/robot/state" },
  { key: "gps",           topic: "/robot/gps" },
  { key: "odom",          topic: "/robot/odom" },
  { key: "leg",           topic: "/robot/leg_joint_states" },
  { key: "video_rear",    topic: "/c2/rear/compressed" },
  { key: "video_inspect", topic: "/c2/inspect/compressed" },
  { key: "video_overhead",topic: "/c2/overhead/compressed" },
  { key: "patrol_state",  topic: "/patrol_state" },
  { key: "landmarks",     topic: "/scene/landmarks" },
  { key: "intruders",     topic: "/intruder_states" },
  { key: "rosout",        topic: "/rosout" },
];

export default function TopicHealthMonitor() {
  const [sample, setSample] = useState<Sample | null>(null);
  const [prev, setPrev] = useState<Record<string, number>>({});
  const [staleSince, setStaleSince] = useState<Record<string, number>>({});

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const r = await fetch(`${getApiBase()}/c2/sample`, { cache: "no-store" });
        if (alive && r.ok) {
          const d = await r.json();
          setSample(d);
        }
      } catch {}
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  useEffect(() => {
    if (!sample?.rx) return;
    const now = Date.now();
    const newStale: Record<string, number> = {};
    Object.entries(sample.rx).forEach(([k, v]) => {
      if (v === prev[k]) {
        newStale[k] = staleSince[k] ?? now;
      } else {
        newStale[k] = now;
      }
    });
    setStaleSince(newStale);
    setPrev(sample.rx);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sample]);

  const statusFor = (key: string) => {
    if (!sample?.rx) return { color: "text-zinc-500", Icon: CircleSlash, label: "—" };
    const count = sample.rx[key] ?? 0;
    if (count === 0) return { color: "text-rose-400", Icon: CircleSlash, label: "DEAD" };
    const staleMs = Date.now() - (staleSince[key] ?? 0);
    if (staleMs > 5000) return { color: "text-amber-400", Icon: CircleDot, label: "STALE" };
    return { color: "text-emerald-400", Icon: Activity, label: "LIVE" };
  };

  return (
    <div className="panel h-full flex flex-col">
      <div className="panel-hd">
        <span>TOPIC HEALTH</span>
        <span className="text-[10px] text-dim">1Hz · /c2/sample</span>
      </div>
      <div className="p-2 overflow-y-auto flex-1 min-h-0 text-[11px] font-mono">
        <table className="w-full">
          <thead className="text-dim text-[10px]">
            <tr>
              <th className="text-left pb-1">KEY</th>
              <th className="text-left pb-1">TOPIC</th>
              <th className="text-right pb-1">RX</th>
              <th className="text-right pb-1">STATUS</th>
            </tr>
          </thead>
          <tbody>
            {TOPICS.map(({ key, topic }) => {
              const { color, Icon, label } = statusFor(key);
              const count = sample?.rx?.[key] ?? 0;
              return (
                <tr key={key} className="border-t border-line/40">
                  <td className="py-0.5 text-ink">{key}</td>
                  <td className="py-0.5 text-dim">{topic}</td>
                  <td className="py-0.5 text-right text-ink">{count}</td>
                  <td className={`py-0.5 text-right ${color}`}>
                    <span className="inline-flex items-center gap-1 justify-end">
                      <Icon size={11} />{label}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
