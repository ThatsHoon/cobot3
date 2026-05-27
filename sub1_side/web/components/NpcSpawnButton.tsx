"use client";
import { useState } from "react";
import { postJSON, ROBOT_ID } from "@/lib/api";
import SettingsPopover from "./SettingsPopover";

/**
 * 군인 NPC 소환 버튼.
 * 직사각형 범위(x=166~226, y=906~915, z=4.8) 내 랜덤 위치에 소환.
 * walking → fence(-Y) 방향 이동 → 무기 피격 시 dying 애니메이션.
 */
export default function NpcSpawnButton() {
  const [busy, setBusy]   = useState(false);
  const [last, setLast]   = useState<string>("");
  const [count, setCount] = useState(1);

  const spawn = async () => {
    setBusy(true);
    try {
      const r = await postJSON<{ ok: boolean; payload: any }>(
        `/robots/${ROBOT_ID}/spawn_soldier`,
        { count },
      );
      setLast(`OK · ×${r.payload.count}`);
    } catch (e: any) {
      setLast(`실패: ${e?.message ?? e}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel">
      <div className="panel-hd">
        <span>SOLDIER SPAWN</span>
        <span className="flex items-center gap-2">
          <SettingsPopover title="SPAWN · PARAMS">
            <div className="space-y-2.5">
              <Slider k="COUNT" unit="" min={1} max={5} step={1}
                      value={count} onChange={setCount} />
            </div>
          </SettingsPopover>
          <span className="panel-idx">SIM/NPC</span>
        </span>
      </div>
      <div className="p-3 flex flex-col gap-2 text-[11px] font-mono">
        <div className="grid grid-cols-1 gap-1.5">
          <Tile k="COUNT" v={`${count}`} u="" />
        </div>
        <button
          onClick={spawn}
          disabled={busy}
          data-tone="phos"
          className="btn mt-1">
          {busy ? "SPAWNING ..." : "SOLDIER SPAWN"}
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
  k, unit, min, max, step, value, onChange,
}: {
  k: string; unit: string; min: number; max: number; step: number;
  value: number; onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="tracking-[0.22em] w-12 text-dim text-[10px]">{k}</span>
      <input type="range" min={min} max={max} step={step}
             value={value}
             onChange={(e) => onChange(parseFloat(e.target.value))}
             className="flex-1" />
      <span className="w-14 text-right text-ink tabular text-[10.5px]">
        {value}<span className="text-dim ml-1">{unit}</span>
      </span>
    </div>
  );
}
