"use client";
import { useState } from "react";
import { postJSON, ROBOT_ID } from "@/lib/api";

export default function NpcSpawnButton() {
  const [busy, setBusy] = useState(false);
  const [last, setLast] = useState<string>("");
  const [fwd, setFwd] = useState(20);
  const [z, setZ] = useState(5);
  const [count, setCount] = useState(1);

  const spawn = async () => {
    setBusy(true);
    try {
      const r = await postJSON<{ok: boolean; payload: any}>(
        `/robots/${ROBOT_ID}/spawn_npc`,
        { forward_m: fwd, z_offset: z, count },
      );
      setLast(`소환 OK: fwd=${r.payload.forward_m}m z+${r.payload.z_offset}m × ${r.payload.count}`);
    } catch (e: any) {
      setLast(`실패: ${e?.message ?? e}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel">
      <div className="panel-hd">NPC 소환 · 사람 형체 낙하</div>
      <div className="p-3 flex flex-col gap-2 text-[11px]">
        <div className="flex items-center gap-2">
          <span className="tracking-[0.15em] w-12">FWD</span>
          <input type="range" min={-30} max={50} step={1}
                 value={fwd} onChange={(e) => setFwd(parseInt(e.target.value))}
                 className="flex-1 accent-[var(--phos)]" />
          <span className="w-12 text-right text-ink">{fwd} m</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="tracking-[0.15em] w-12">DROP</span>
          <input type="range" min={1} max={20} step={0.5}
                 value={z} onChange={(e) => setZ(parseFloat(e.target.value))}
                 className="flex-1 accent-[var(--phos)]" />
          <span className="w-12 text-right text-ink">+{z} m</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="tracking-[0.15em] w-12">COUNT</span>
          <input type="range" min={1} max={5} step={1}
                 value={count} onChange={(e) => setCount(parseInt(e.target.value))}
                 className="flex-1 accent-[var(--phos)]" />
          <span className="w-12 text-right text-ink">{count}</span>
        </div>
        <button
          onClick={spawn}
          disabled={busy}
          className="btn select-none mt-1"
          style={{ borderColor: "var(--phos)", color: "var(--phos)" }}>
          {busy ? "…" : `NPC 소환 (전방 ${fwd}m · z+${z}m · ${count}명)`}
        </button>
        {last && <div className="text-[10px] text-dim">{last}</div>}
      </div>
    </div>
  );
}
