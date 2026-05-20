"use client";
import { useState } from "react";
import { postJSON, ROBOT_ID } from "@/lib/api";

const PAN_STEP = 8 * Math.PI / 180;    // 8°
const TILT_STEP = 5 * Math.PI / 180;   // 5°

export default function InspectorCameraPanel() {
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  // delta(절대 누적값은 서버에서 관리; UI 는 명령만 발송)
  const [pan, setPan] = useState(0);
  const [tilt, setTilt] = useState(0);
  const [zoom, setZoom] = useState(1.0);

  const send = async (payload: Record<string, unknown>) => {
    setBusy(true);
    try {
      await postJSON(`/robots/${ROBOT_ID}/inspect`, payload);
      setMsg(`inspect → ${JSON.stringify(payload)}`);
    } catch (e: any) {
      setMsg(`실패: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    setPan(0); setTilt(0); setZoom(1.0);
    await send({ reset: true });
  };

  const stepPan = async (sign: number) => {
    const next = pan + sign * PAN_STEP;
    setPan(next);
    await send({ pan: next, absolute: true });
  };
  const stepTilt = async (sign: number) => {
    const next = Math.max(-Math.PI / 3, Math.min(Math.PI / 3,
      tilt + sign * TILT_STEP));
    setTilt(next);
    await send({ tilt: next, absolute: true });
  };
  const stepZoom = async (mul: number) => {
    const next = Math.max(0.5, Math.min(2.0, zoom * mul));
    setZoom(next);
    await send({ zoom: mul, absolute: false });
  };

  return (
    <div className="panel">
      <div className="panel-hd">
        <span>INSPECT CAM</span>
        <span className="text-[11px] text-dim">
          pan {(pan * 180 / Math.PI).toFixed(0)}° ·
          tilt {(tilt * 180 / Math.PI).toFixed(0)}° ·
          ×{zoom.toFixed(2)}
        </span>
      </div>
      <div className="px-3 py-2 grid grid-cols-3 gap-1.5 text-[11px]">
        <div />
        <button onClick={() => stepTilt(+1)} disabled={busy}
                className="py-1.5 rounded bg-zinc-700 hover:bg-zinc-600">▲</button>
        <div />
        <button onClick={() => stepPan(-1)} disabled={busy}
                className="py-1.5 rounded bg-zinc-700 hover:bg-zinc-600">◀</button>
        <button onClick={reset} disabled={busy}
                className="py-1.5 rounded bg-amber-700 hover:bg-amber-600">RESET</button>
        <button onClick={() => stepPan(+1)} disabled={busy}
                className="py-1.5 rounded bg-zinc-700 hover:bg-zinc-600">▶</button>
        <div />
        <button onClick={() => stepTilt(-1)} disabled={busy}
                className="py-1.5 rounded bg-zinc-700 hover:bg-zinc-600">▼</button>
        <div />
        <button onClick={() => stepZoom(1.25)} disabled={busy}
                className="py-1.5 rounded bg-sky-700 hover:bg-sky-600 col-span-1">
          ZOOM +
        </button>
        <div />
        <button onClick={() => stepZoom(0.8)} disabled={busy}
                className="py-1.5 rounded bg-sky-700 hover:bg-sky-600">
          ZOOM −
        </button>
      </div>
      <div className="px-3 pb-2 text-[11px] text-dim font-mono min-h-[16px]">
        {msg || "맵 Shift+클릭 = look_at(world XY)"}
      </div>
    </div>
  );
}
