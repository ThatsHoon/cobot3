"use client";
import { useState } from "react";
import { postJSON, ROBOT_ID } from "@/lib/api";

// 2026-05-20: 사용자 사양 — 정면 ±70° 제한
const PAN_STEP = 8 * Math.PI / 180;
const TILT_STEP = 5 * Math.PI / 180;
const LIMIT = 70 * Math.PI / 180;
const clamp = (v: number) => Math.max(-LIMIT, Math.min(LIMIT, v));

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
    const next = clamp(pan + sign * PAN_STEP);
    setPan(next);
    await send({ pan: next, absolute: true });
  };
  const stepTilt = async (sign: number) => {
    const next = clamp(tilt + sign * TILT_STEP);
    setTilt(next);
    await send({ tilt: next, absolute: true });
  };
  const setAbsPan = async (deg: number) => {
    const next = clamp(deg * Math.PI / 180);
    setPan(next);
    await send({ pan: next, absolute: true });
  };
  const setAbsTilt = async (deg: number) => {
    const next = clamp(deg * Math.PI / 180);
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

      {/* 절대 슬라이더 (±70°) — 사용자 사양 2026-05-20 */}
      <div className="px-3 pb-2 space-y-1.5 text-[10px]">
        <div className="flex items-center gap-2">
          <span className="tracking-[0.15em] w-10 text-dim">PAN</span>
          <input type="range" min={-70} max={70} step={1}
                 value={Math.round(pan * 180 / Math.PI)}
                 onChange={(e) => setAbsPan(parseInt(e.target.value))}
                 className="flex-1 accent-[var(--phos)]" />
          <span className="w-10 text-right text-ink">
            {(pan * 180 / Math.PI).toFixed(0)}°
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="tracking-[0.15em] w-10 text-dim">TILT</span>
          <input type="range" min={-70} max={70} step={1}
                 value={Math.round(tilt * 180 / Math.PI)}
                 onChange={(e) => setAbsTilt(parseInt(e.target.value))}
                 className="flex-1 accent-[var(--phos)]" />
          <span className="w-10 text-right text-ink">
            {(tilt * 180 / Math.PI).toFixed(0)}°
          </span>
        </div>
      </div>

      <div className="px-3 pb-2 text-[11px] text-dim font-mono min-h-[16px]">
        {msg || "맵 Shift+클릭 = look_at · DS 좌stick = 카메라 회전"}
      </div>
    </div>
  );
}
