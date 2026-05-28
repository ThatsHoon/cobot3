"use client";
import { useState } from "react";
import { postJSON, ROBOT_ID } from "@/lib/api";
import SettingsPopover from "./SettingsPopover";

/**
 * NPC/동물/드론 소환 패널.
 * - SOLDIER : x=166~226, y=906~915, z=4.8 랜덤 소환 (walking → fence 방향)
 * - WOLF/DEER/BOAR/DRONE : 동일 영역 랜덤 소환 (접근 오브젝트 on-demand)
 */

type AnimalKind = "wolf" | "deer" | "boar" | "drone";

const ANIMAL_LABELS: { kind: AnimalKind; label: string; ko: string }[] = [
  { kind: "wolf",  label: "WOLF",  ko: "늑대" },
  { kind: "deer",  label: "DEER",  ko: "사슴" },
  { kind: "boar",  label: "BOAR",  ko: "돼지" },
  { kind: "drone", label: "DRONE", ko: "드론" },
];

export default function NpcSpawnButton() {
  const [soldierCount, setSoldierCount] = useState(1);
  const [busySoldier, setBusySoldier]   = useState(false);
  const [busyAnimal, setBusyAnimal]     = useState<AnimalKind | null>(null);
  const [last, setLast]                 = useState<string>("");

  const spawnSoldier = async () => {
    setBusySoldier(true);
    try {
      const r = await postJSON<{ ok: boolean; payload: any }>(
        `/robots/${ROBOT_ID}/spawn_soldier`,
        { count: soldierCount },
      );
      setLast(`SOLDIER OK · ×${r.payload.count}`);
    } catch (e: any) {
      setLast(`실패: ${e?.message ?? e}`);
    } finally {
      setBusySoldier(false);
    }
  };

  const spawnAnimal = async (kind: AnimalKind) => {
    setBusyAnimal(kind);
    try {
      await postJSON<{ ok: boolean; payload: any }>(
        `/robots/${ROBOT_ID}/spawn_animal`,
        { kind, count: 1 },
      );
      setLast(`${kind.toUpperCase()} OK`);
    } catch (e: any) {
      setLast(`실패: ${e?.message ?? e}`);
    } finally {
      setBusyAnimal(null);
    }
  };

  return (
    <div className="panel">
      <div className="panel-hd">
        <span>NPC SPAWN</span>
        <span className="flex items-center gap-2">
          <SettingsPopover title="SPAWN · PARAMS">
            <div className="space-y-2.5">
              <Slider k="SOLDIER COUNT" unit="" min={1} max={5} step={1}
                      value={soldierCount} onChange={setSoldierCount} />
            </div>
          </SettingsPopover>
          <span className="panel-idx">SIM/NPC</span>
        </span>
      </div>
      <div className="p-3 flex flex-col gap-2 text-[11px] font-mono">
        {/* 군인 소환 */}
        <button
          onClick={spawnSoldier}
          disabled={busySoldier}
          data-tone="phos"
          className="btn">
          {busySoldier ? "SPAWNING ..." : `SOLDIER SPAWN ×${soldierCount}`}
        </button>

        {/* 동물/드론 소환 — 2열 그리드 */}
        <div className="grid grid-cols-2 gap-1.5 mt-1">
          {ANIMAL_LABELS.map(({ kind, label, ko }) => (
            <button
              key={kind}
              onClick={() => spawnAnimal(kind)}
              disabled={busyAnimal !== null}
              data-tone="amber"
              className="btn text-[10px]">
              {busyAnimal === kind
                ? "..."
                : `${label} (${ko})`}
            </button>
          ))}
        </div>

        {last && (
          <div className="text-[10px] text-dim tabular pt-0.5 truncate">{last}</div>
        )}
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
      <span className="tracking-[0.22em] w-24 text-dim text-[10px]">{k}</span>
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
