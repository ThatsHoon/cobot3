"use client";
import { useState } from "react";
import { postJSON, ROBOT_ID } from "@/lib/api";
import SettingsPopover from "./SettingsPopover";

const PAN_STEP = 8 * Math.PI / 180;
const TILT_STEP = 5 * Math.PI / 180;
const LIMIT = 70 * Math.PI / 180;
const clamp = (v: number) => Math.max(-LIMIT, Math.min(LIMIT, v));

/** EO turret 카메라 컨트롤. `bare`=true 이면 외곽 panel 래퍼 없이 본문만(설정 ⚙ 포함). */
export default function InspectorCameraPanel({ bare = false }: { bare?: boolean }) {
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
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
    setPan(next); await send({ pan: next, absolute: true });
  };
  const stepTilt = async (sign: number) => {
    const next = clamp(tilt + sign * TILT_STEP);
    setTilt(next); await send({ tilt: next, absolute: true });
  };
  const setAbsPan = async (deg: number) => {
    const next = clamp(deg * Math.PI / 180);
    setPan(next); await send({ pan: next, absolute: true });
  };
  const setAbsTilt = async (deg: number) => {
    const next = clamp(deg * Math.PI / 180);
    setTilt(next); await send({ tilt: next, absolute: true });
  };
  const stepZoom = async (mul: number) => {
    const next = Math.max(0.5, Math.min(2.0, zoom * mul));
    setZoom(next); await send({ zoom: mul, absolute: false });
  };

  const settingsPopover = (
    <SettingsPopover title="EO TURRET · DETAIL">
      <div className="space-y-2.5">
        <Slider k="PAN" min={-70} max={70}
                value={Math.round(pan * 180 / Math.PI)} onChange={setAbsPan} unit="°" />
        <Slider k="TILT" min={-70} max={70}
                value={Math.round(tilt * 180 / Math.PI)} onChange={setAbsTilt} unit="°" />
        <div className="grid grid-cols-2 gap-1.5 pt-1">
          <button onClick={reset} disabled={busy}
                  data-tone="amber" className="btn !py-1.5 !text-[10px]">RESET</button>
          <div className="text-[9.5px] text-dim leading-snug tracking-[0.04em]">
            맵 Shift+클릭 = look_at · DS 좌stick = 회전
          </div>
        </div>
      </div>
    </SettingsPopover>
  );

  /** EO 카메라 키 셀 — 5방향(상하좌우 + 중앙 RESET) — 컴팩트 */
  const dirCell = (
    arrow: string, onClick: () => void, kind: "dir" | "reset" = "dir",
  ) => (
    <button
      onClick={onClick}
      disabled={busy}
      className="h-8 border font-display text-[11.5px] tracking-[0.04em]
                 transition-colors disabled:opacity-40 flex items-center justify-center"
      style={{
        background: kind === "reset"
          ? "linear-gradient(180deg, rgba(244,183,64,0.12), transparent)"
          : "linear-gradient(180deg, #0c1611, #050a08)",
        borderColor: kind === "reset" ? "var(--amber-dim)" : "var(--line-2)",
        color: kind === "reset" ? "var(--amber)" : "var(--ink-2)",
      }}>
      {arrow}
    </button>
  );

  const zoomBtn = (label: string, mul: number) => (
    <button
      onClick={() => stepZoom(mul)}
      disabled={busy}
      className="btn !py-1 !text-[9.5px] !tracking-[0.18em] !px-1">
      {label}
    </button>
  );

  const body = (
    <div className="space-y-1.5">
      <div className="grid grid-cols-3 gap-1">
        <div />
        {dirCell("▲", () => stepTilt(+1))}
        <div />
        {dirCell("◀", () => stepPan(-1))}
        {dirCell("◯", reset, "reset")}
        {dirCell("▶", () => stepPan(+1))}
        <div />
        {dirCell("▼", () => stepTilt(-1))}
        <div />
      </div>
      <div className="grid grid-cols-2 gap-1">
        {zoomBtn("ZOOM +", 1.25)}
        {zoomBtn("ZOOM −", 0.8)}
      </div>
      <div className="grid grid-cols-3 gap-1 text-[9px] font-mono">
        <MicroTile k="PAN"  v={`${(pan * 180 / Math.PI).toFixed(0)}°`} />
        <MicroTile k="TILT" v={`${(tilt * 180 / Math.PI).toFixed(0)}°`} />
        <MicroTile k="ZOOM" v={`×${zoom.toFixed(2)}`} />
      </div>
    </div>
  );

  if (bare) {
    return (
      <div className="p-2 relative h-full">
        <div className="flex items-center justify-between mb-1.5">
          <span className="font-display tracking-[0.24em] text-[10px] text-ink-2">INSPECT</span>
          <span className="flex items-center gap-1.5">
            {settingsPopover}
            <span className="text-[8.5px] tracking-[0.18em] text-dim">EO/05</span>
          </span>
        </div>
        {body}
        {msg && (
          <div className="text-[9.5px] text-dim font-mono mt-1.5 truncate">{msg}</div>
        )}
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-hd">
        <span>INSPECT CAM</span>
        <span className="flex items-center gap-2">
          {settingsPopover}
          <span className="panel-idx">EO/05</span>
        </span>
      </div>
      <div className="p-3">
        {body}
        {msg && (
          <div className="text-[9.5px] text-dim font-mono mt-2 truncate">{msg}</div>
        )}
      </div>
    </div>
  );
}

function MicroTile({ k, v }: { k: string; v: string }) {
  return (
    <div className="border border-line bg-panel-2 px-1.5 py-0.5">
      <div className="text-[7.5px] tracking-[0.28em] text-dim uppercase">{k}</div>
      <div className="font-display tracking-[0.04em] text-[11px] text-phos tabular">{v}</div>
    </div>
  );
}

function Slider({
  k, min, max, value, onChange, unit,
}: {
  k: string; min: number; max: number; value: number;
  onChange: (v: number) => void; unit: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-10 text-[9.5px] tracking-[0.22em] text-dim">{k}</span>
      <input type="range" min={min} max={max} step={1}
             value={value}
             onChange={(e) => onChange(parseInt(e.target.value))}
             className="flex-1" />
      <span className="w-10 text-right text-ink tabular text-[10.5px]">
        {value}<span className="text-dim ml-0.5">{unit}</span>
      </span>
    </div>
  );
}
