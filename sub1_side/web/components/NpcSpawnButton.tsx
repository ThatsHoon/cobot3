"use client";
import { useState } from "react";
import { postJSON, ROBOT_ID } from "@/lib/api";
import SettingsPopover from "./SettingsPopover";

export default function NpcSpawnButton() {
  const [busy, setBusy] = useState(false);
  const [last, setLast] = useState<string>("");
  const [fwd, setFwd] = useState(20);
  const [z, setZ] = useState(5);
  const [count, setCount] = useState(1);

  const spawn = async () => {
    setBusy(true);
    try {
      const r = await postJSON<{ ok: boolean; payload: any }>(
        `/robots/${ROBOT_ID}/spawn_npc`,
        { forward_m: fwd, z_offset: z, count },
      );
      setLast(`OK · fwd=${r.payload.forward_m} m  z+${r.payload.z_offset} m  ×${r.payload.count}`);
    } catch (e: any) {
      setLast(`실패: ${e?.message ?? e}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel">
      <div className="panel-hd">
        <span>NPC INJECTION</span>
        <span className="flex items-center gap-2">
          <SettingsPopover title="INJECTION · PARAMS">
            <div className="space-y-2.5">
              <Slider k="FWD"   unit="m"  min={-30} max={50} step={1}
                      value={fwd}   onChange={setFwd}   showPlus />
              <Slider k="DROP"  unit="m"  min={1}   max={20} step={0.5}
                      value={z}     onChange={setZ}     prefix="+" />
              <Slider k="COUNT" unit=""   min={1}   max={5}  step={1}
                      value={count} onChange={setCount} />
            </div>
          </SettingsPopover>
          <span className="panel-idx">SIM/NPC</span>
        </span>
      </div>
      <div className="p-3 flex flex-col gap-2 text-[11px] font-mono">
        <div className="grid grid-cols-3 gap-1.5">
          <Tile k="FWD"   v={`${fwd >= 0 ? "+" : ""}${fwd}`} u="m" />
          <Tile k="DROP"  v={`+${z}`} u="m" />
          <Tile k="COUNT" v={`${count}`} u="" />
        </div>
        <button
          onClick={spawn}
          disabled={busy}
          data-tone="phos"
          className="btn mt-1">
          {busy ? "INJECTING ..." : "▼  NPC INJECT  ▼"}
        </button>
        {last && (
          <div className="text-[10px] text-dim tabular pt-0.5 truncate">{last}</div>
        )}
      </div>
    </div>
  );
}

function Tile({ k, v, u }: { k: string; v: string; u: string }) {
  return (
    <div className="border border-line bg-panel-2 px-2 py-1">
      <div className="text-[8.5px] tracking-[0.32em] text-dim uppercase">{k}</div>
      <div className="font-display text-[13px] tabular text-phos">
        {v}{u && <span className="text-dim ml-1 text-[10px]">{u}</span>}
      </div>
    </div>
  );
}

function Slider({
  k, unit, min, max, step, value, onChange, prefix, showPlus,
}: {
  k: string; unit: string; min: number; max: number; step: number;
  value: number; onChange: (v: number) => void;
  prefix?: string; showPlus?: boolean;
}) {
  const display = showPlus && value >= 0 ? `+${value}` : (prefix ?? "") + value;
  return (
    <div className="flex items-center gap-2">
      <span className="tracking-[0.22em] w-12 text-dim text-[10px]">{k}</span>
      <input type="range" min={min} max={max} step={step}
             value={value}
             onChange={(e) => onChange(parseFloat(e.target.value))}
             className="flex-1" />
      <span className="w-14 text-right text-ink tabular text-[10.5px]">
        {display}<span className="text-dim ml-1">{unit}</span>
      </span>
    </div>
  );
}
