"use client";
import { useState } from "react";
import { gotoTacticalPoint, previewRoute, postJSON, RoutingStatePayload, ROBOT_ID } from "@/lib/api";

const TP_LIST = ["TP_A", "TP_B", "TP_C", "TP_D"];
const TP_LABEL: Record<string, string> = {
  TP_A: "TP-A 서측",
  TP_B: "TP-B 중앙",
  TP_C: "TP-C 고지",
  TP_D: "TP-D 동측",
};

interface Props {
  routingState?: RoutingStatePayload | null;
  patrolMode?: string | null;
  onPreviewChange?: (route: { x: number; y: number }[] | null) => void;
}

export default function TacticalPointsPanel({ routingState, patrolMode, onPreviewChange }: Props) {
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [abLoading, setAbLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isRouting = routingState && !routingState.completed;
  const isAbPatrol = patrolMode === "AB_PATROL";

  async function handleAbPatrol() {
    setAbLoading(true);
    setError(null);
    try {
      await postJSON("/missions/command", { command: "ab_patrol" });
    } catch (e: any) {
      setError(e?.message ?? "A↔B 순찰 명령 전송 실패");
    } finally {
      setAbLoading(false);
    }
  }
  const progress =
    routingState && routingState.total > 0
      ? Math.min(100, Math.round((routingState.current_idx / routingState.total) * 100))
      : 0;

  async function handleSelect(tp: string) {
    const next = selected === tp ? null : tp;
    setSelected(next);
    setError(null);
    if (!next) { onPreviewChange?.(null); return; }
    try {
      const res = await previewRoute(ROBOT_ID, next);
      onPreviewChange?.(res.route);
    } catch {
      onPreviewChange?.(null);
    }
  }

  async function handleMove() {
    if (!selected || loading) return;
    setError(null);
    setLoading(true);
    try {
      await gotoTacticalPoint(ROBOT_ID, selected);
    } catch (e: any) {
      setError(e?.message ?? "명령 전송 실패");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="panel">
      <div className="panel-hd">
        <span>TACTICAL POINTS</span>
        <span className="panel-idx">TP/04</span>
      </div>
      <div className="p-2.5 space-y-2">
        <div className="grid grid-cols-2 gap-1.5">
          {TP_LIST.map((tp) => {
            const isActive = routingState?.tp_id === tp && isRouting;
            const isSel = selected === tp;
            return (
              <button
                key={tp}
                onClick={() => handleSelect(tp)}
                data-active={isSel || isActive ? "true" : "false"}
                data-tone={isActive ? "amber" : isSel ? "phos" : undefined}
                className="btn !py-1.5 !px-2 !text-[10px] !tracking-[0.12em]
                           font-mono normal-case">
                <span className="flex items-center gap-1.5">
                  <span className="text-dim text-[9px]">›</span>
                  {TP_LABEL[tp] ?? tp}
                </span>
              </button>
            );
          })}
        </div>

        {isRouting && (
          <div className="space-y-1">
            <div className="flex justify-between text-[9.5px] font-mono tabular">
              <span className="text-amber tracking-[0.18em]">
                {routingState!.tp_id} EN-ROUTE
              </span>
              <span className="text-ink-2">
                {routingState!.current_idx}/{routingState!.total}
              </span>
            </div>
            <div className="h-[3px] bg-line">
              <div
                className="h-full bg-amber transition-all duration-300"
                style={{ width: `${progress}%`, boxShadow: "0 0 6px var(--amber)" }} />
            </div>
          </div>
        )}
        {routingState?.completed && (
          <div className="text-[10px] text-phos font-display tracking-[0.2em]">
            ✓ {routingState.tp_id} ARRIVED
          </div>
        )}

        {error && <div className="text-[10px] text-alert">{error}</div>}

        <button
          onClick={handleMove}
          disabled={!selected || loading}
          data-tone="phos"
          className="btn w-full !py-2">
          {loading ? "TX..." : "이동 명령 / DISPATCH"}
        </button>

        {/* A↔B 반복 순찰 — TP_A → TP_B → TP_A 무한 루프 */}
        <button
          onClick={handleAbPatrol}
          disabled={abLoading}
          data-active={isAbPatrol ? "true" : "false"}
          data-tone={isAbPatrol ? "phos" : undefined}
          className="btn w-full !py-2 !text-[10px] !tracking-[0.14em] font-mono">
          {abLoading ? "TX..." : isAbPatrol ? "● A↔B 순찰 中" : "A↔B 반복 순찰"}
        </button>
      </div>
    </div>
  );
}
