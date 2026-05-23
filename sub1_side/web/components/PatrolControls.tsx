"use client";
import { useState } from "react";
import { Play, Home, Pause, RotateCw } from "lucide-react";
import { postJSON, PatrolStatePayload } from "@/lib/api";

const BTNS: {
  cmd: string;
  Icon: typeof Play;
  title: string;
  tone: "phos" | "amber" | "alert";
}[] = [
  { cmd: "sortie", Icon: Play,     title: "출격",  tone: "phos"  },
  { cmd: "home",   Icon: Home,     title: "복귀",  tone: "amber" },
  { cmd: "stop",   Icon: Pause,    title: "정지",  tone: "amber" },
  { cmd: "resume", Icon: RotateCw, title: "재개",  tone: "phos"  },
];

const MODE_TONE: Record<string, string> = {
  IDLE: "text-ink-2",
  PATROL: "text-phos",
  HOME: "text-amber",
  ALERT_STOP: "text-alert animate-pulse",
  STOPPED: "text-amber",
  WAITING_FOR_NAV2: "text-amber",
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
        <span className="flex items-center gap-2">
          <span className="panel-idx">CMD/01</span>
          <span className={`font-display tracking-[0.18em] text-[11px] ${MODE_TONE[mode] ?? "text-dim"}`}>
            {mode}
          </span>
          {lmReady === false && <span className="text-amber text-[10px]">· LM WAIT</span>}
        </span>
      </div>
      <div className="px-3 py-2.5 grid grid-cols-4 gap-1.5">
        {BTNS.map(({ cmd, Icon, title, tone }) => (
          <button
            key={cmd}
            onClick={() => send(cmd)}
            disabled={busy}
            title={title}
            aria-label={title}
            data-tone={tone}
            className="btn flex items-center justify-center !py-2.5">
            <Icon size={16} strokeWidth={1.7} />
          </button>
        ))}
      </div>
      <div className="px-3 pb-2.5 text-[10.5px] font-mono tabular space-y-0.5">
        {wp && (
          <div className="flex justify-between">
            <span className="text-dim tracking-[0.18em]">WP</span>
            <span className="text-ink">({wp.x.toFixed(1)}, {wp.y.toFixed(1)})</span>
          </div>
        )}
        {pose && (
          <div className="flex justify-between">
            <span className="text-dim tracking-[0.18em]">POSE</span>
            <span className="text-ink">
              ({pose.x.toFixed(1)}, {pose.y.toFixed(1)})
              <span className="text-dim ml-2">{(pose.yaw * 180 / Math.PI).toFixed(0)}°</span>
            </span>
          </div>
        )}
        {msg && <div className="text-amber text-[10px] pt-1">{msg}</div>}
      </div>
    </div>
  );
}
