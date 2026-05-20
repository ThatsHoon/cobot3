"use client";
import { useState } from "react";
import { postJSON, PatrolStatePayload } from "@/lib/api";

const BTNS: { cmd: string; label: string; cls: string }[] = [
  { cmd: "sortie", label: "출격",   cls: "bg-emerald-700 hover:bg-emerald-600" },
  { cmd: "home",   label: "복귀",   cls: "bg-sky-700 hover:bg-sky-600" },
  { cmd: "stop",   label: "정지",   cls: "bg-rose-700 hover:bg-rose-600" },
  { cmd: "resume", label: "재개",   cls: "bg-amber-700 hover:bg-amber-600" },
  { cmd: "idle",   label: "대기",   cls: "bg-zinc-700 hover:bg-zinc-600" },
];

const MODE_CLASS: Record<string, string> = {
  IDLE:        "text-zinc-400",
  PATROL:      "text-emerald-400",
  HOME:        "text-sky-400",
  ALERT_STOP:  "text-rose-400 animate-pulse",
  STOPPED:     "text-amber-400",
  WAITING_FOR_NAV2: "text-amber-300",
};

export default function PatrolControls({
  patrolState,
}: {
  patrolState: PatrolStatePayload | null;
}) {
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const send = async (cmd: string) => {
    setBusy(true);
    try {
      await postJSON("/missions/command", { command: cmd });
      setMsg(`mission_command → ${cmd}`);
    } catch (e: any) {
      setMsg(`실패: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const mode = patrolState?.mode ?? "—";
  const wp = patrolState?.waypoint;
  const pose = patrolState?.pose;
  const lmReady = patrolState?.landmarks_received;

  return (
    <div className="panel">
      <div className="panel-hd">
        <span>PATROL</span>
        <span className={`text-[11px] ${MODE_CLASS[mode] ?? "text-dim"}`}>
          {mode}
          {lmReady === false && <span className="text-amber"> · LM 대기</span>}
        </span>
      </div>
      <div className="px-3 py-2 grid grid-cols-5 gap-1.5">
        {BTNS.map((b) => (
          <button
            key={b.cmd}
            onClick={() => send(b.cmd)}
            disabled={busy}
            className={`text-[11px] py-1.5 rounded ${b.cls} ` +
                       "disabled:opacity-40 disabled:cursor-not-allowed"}
          >
            {b.label}
          </button>
        ))}
      </div>
      <div className="px-3 pb-2 text-[11px] text-dim font-mono">
        {wp && (
          <div>
            wp: ({wp.x.toFixed(1)}, {wp.y.toFixed(1)})
          </div>
        )}
        {pose && (
          <div>
            pose: ({pose.x.toFixed(1)}, {pose.y.toFixed(1)})
            yaw={(pose.yaw * 180 / Math.PI).toFixed(0)}°
          </div>
        )}
        {msg && <div className="text-amber pt-0.5">{msg}</div>}
      </div>
    </div>
  );
}
