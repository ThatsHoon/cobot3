"use client";
import { useCallback, useRef, useState } from "react";
import { postJSON, ROBOT_ID } from "@/lib/api";

type Cmd = { linear: number; angular: number };

const SEND_HZ = 10; // cmd_vel 발행 주기 (ms = 1000/HZ)

export default function TeleopPad() {
  const [speed, setSpeed] = useState(0.4);
  const [active, setActive] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const send = useCallback(async (cmd: Cmd) => {
    try { await postJSON(`/robots/${ROBOT_ID}/cmd_vel`, cmd); } catch {}
  }, []);

  const startCmd = useCallback((key: string, cmd: Cmd) => {
    if (timerRef.current) clearInterval(timerRef.current);
    setActive(key);
    send(cmd);
    timerRef.current = setInterval(() => send(cmd), 1000 / SEND_HZ);
  }, [send]);

  const stopCmd = useCallback(() => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    setActive(null);
    send({ linear: 0, angular: 0 });
  }, [send]);

  const btn = (key: string, label: string, cmd: Cmd) => (
    <button
      className="btn select-none touch-none"
      style={active === key ? { borderColor: "var(--phos)", color: "var(--phos)" } : undefined}
      onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); startCmd(key, cmd); }}
      onPointerUp={stopCmd}
      onPointerCancel={stopCmd}
    >
      {label}
    </button>
  );

  return (
    <div className="panel">
      <div className="panel-hd">TELEOP · 원격 조종</div>
      <div className="p-3 flex flex-col gap-3">
        {/* D-pad */}
        <div className="grid grid-cols-3 gap-1 w-fit mx-auto">
          <div />
          {btn("fwd",  "▲", { linear:  speed, angular: 0 })}
          <div />
          {btn("left", "◀", { linear: 0, angular:  speed })}
          <button className="btn text-alert" onClick={stopCmd}>■</button>
          {btn("right", "▶", { linear: 0, angular: -speed })}
          <div />
          {btn("bwd", "▼", { linear: -speed, angular: 0 })}
          <div />
        </div>

        {/* 속도 슬라이더 */}
        <div className="flex items-center gap-2 text-[11px] text-dim">
          <span className="tracking-[0.15em] w-12">SPEED</span>
          <input
            type="range" min={0.1} max={1.0} step={0.05}
            value={speed}
            onChange={(e) => setSpeed(parseFloat(e.target.value))}
            className="flex-1 accent-[var(--phos)]"
          />
          <span className="w-10 text-right text-ink">{speed.toFixed(2)}</span>
        </div>
      </div>
    </div>
  );
}
