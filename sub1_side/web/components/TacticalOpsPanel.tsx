"use client";
import { useEffect, useRef, useState } from "react";
import { Play, Home, Pause, RotateCw, Lock, Unlock, GripVertical } from "lucide-react";
import {
  postJSON,
  gotoTacticalPoint,
  previewRoute,
  WeaponState,
  PatrolStatePayload,
  RoutingStatePayload,
  AlertPayload,
  ROBOT_ID,
} from "@/lib/api";
import { useWeaponSafety } from "./WeaponSafetyContext";

// --- WEAPON CONFIG ---
const STATE_TONE: Record<string, string> = {
  IDLE: "text-phos",
  COOLDOWN: "text-amber",
  FIRE: "text-alert animate-pulse",
  RAMP_UP: "text-amber",
  RAMP_DOWN: "text-amber",
  HOLD: "text-amber",
};

// --- PATROL CONFIG ---
const PATROL_BTNS: {
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

const PATROL_MODE_TONE: Record<string, string> = {
  IDLE: "text-ink-2",
  PATROL: "text-phos",
  HOME: "text-amber",
  ALERT_STOP: "text-alert animate-pulse",
  STOPPED: "text-amber",
  WAITING_FOR_NAV2: "text-amber",
};

// --- TACTICAL POINTS CONFIG ---
const TP_LIST = ["TP_A", "TP_B", "TP_C", "TP_D"];
const TP_LABEL: Record<string, string> = {
  TP_A: "TP-A 서측",
  TP_B: "TP-B 중앙",
  TP_C: "TP-C 고지",
  TP_D: "TP-D 동측",
};

export default function TacticalOpsPanel({
  weapon,
  liveFireEvents,
  patrolState,
  routingState,
  onPreviewChange,
}: {
  weapon: WeaponState | null;
  liveFireEvents: { fire_id: string | null; target: string }[];
  patrolState: PatrolStatePayload | null;
  routingState?: RoutingStatePayload | null;
  onPreviewChange?: (route: { x: number; y: number }[] | null) => void;
}) {
  // Weapon HITL safety state
  const {
    safetyOff,
    setSafetyOff,
    pending,
    confirmFire,
    cancelFire,
    toastMsg,
  } = useWeaponSafety();

  const [resultPending, setResultPending] = useState<{ fire_id: string; target: string } | null>(null);
  const seenRef = useRef<Set<string>>(new Set());

  // Patrol command state
  const [patrolMsg, setPatrolMsg] = useState("");
  const [patrolBusy, setPatrolBusy] = useState(false);

  // Tactical points state
  const [selectedTp, setSelectedTp] = useState<string | null>(null);
  const [tpLoading, setTpLoading] = useState(false);
  const [tpError, setTpError] = useState<string | null>(null);
  const [abLoading, setAbLoading] = useState(false);

  // Track live fire events for hit decision popup
  useEffect(() => {
    for (const e of liveFireEvents) {
      if (e.fire_id && !seenRef.current.has(e.fire_id)) {
        seenRef.current.add(e.fire_id);
        setResultPending({ fire_id: e.fire_id, target: e.target });
      }
    }
  }, [liveFireEvents]);

  const recordResult = async (hit: boolean, miss_reason?: string) => {
    if (!resultPending) return;
    try {
      await postJSON(`/robots/${ROBOT_ID}/fire/result`, {
        fire_id: resultPending.fire_id,
        hit,
        miss_reason,
      });
    } catch (e) {
      console.error(e);
    } finally {
      setResultPending(null);
    }
  };

  // Weapon details
  const weaponState = weapon?.state ?? "IDLE";
  const cooldown = weapon?.cooldown_remaining_s ?? 0;
  const stateColor = STATE_TONE[weaponState] ?? "text-ink-2";

  // Patrol details
  const patrolMode = patrolState?.mode ?? "—";
  const wp = patrolState?.waypoint;
  const pose = patrolState?.pose;
  const lmReady = patrolState?.landmarks_received;

  const sendPatrolCommand = async (cmd: string) => {
    setPatrolBusy(true);
    try {
      await postJSON("/missions/command", { command: cmd });
      setPatrolMsg(`mission_command → ${cmd}`);
    } catch (e: any) {
      setPatrolMsg(`실패: ${e.message}`);
    } finally {
      setPatrolBusy(false);
    }
  };

  // Tactical Points details
  const isRouting = routingState && !routingState.completed;
  const progress =
    routingState && routingState.total > 0
      ? Math.min(100, Math.round((routingState.current_idx / routingState.total) * 100))
      : 0;

  async function handleSelectTp(tp: string) {
    const next = selectedTp === tp ? null : tp;
    setSelectedTp(next);
    setTpError(null);
    if (!next) {
      onPreviewChange?.(null);
      return;
    }
    try {
      const res = await previewRoute(ROBOT_ID, next);
      onPreviewChange?.(res.route);
    } catch {
      onPreviewChange?.(null);
    }
  }

  async function handleTpMove() {
    if (!selectedTp || tpLoading) return;
    setTpError(null);
    setTpLoading(true);
    try {
      await gotoTacticalPoint(ROBOT_ID, selectedTp);
    } catch (e: any) {
      setTpError(e?.message ?? "명령 전송 실패");
    } finally {
      setTpLoading(false);
    }
  }

  return (
    <div className="panel relative h-full flex flex-col">
      <div className="panel-hd">
        <span>TACTICAL MISSION CONTROL</span>
        <span className="panel-idx">OPS/01</span>
      </div>
      <div className="p-3 grid grid-cols-12 gap-4 flex-1">
        {/* LEFT SECTION (Weapon HITL - 6 Columns) */}
        <div className="col-span-12 lg:col-span-6 border-r border-line pr-4 last:border-r-0">
          <div className="flex items-baseline justify-between mb-2 border-b border-line pb-1.5">
            <span className="font-display tracking-[0.32em] text-[10px] text-phos font-semibold" style={{ textShadow: "0 0 6px var(--phos-glow)" }}>
              WEAPON SAFETY GATE
            </span>
            <span className="font-display tracking-[0.22em] text-[10px]">
              <span className={safetyOff ? "text-alert" : "text-phos"} style={{ textShadow: safetyOff ? "0 0 6px var(--alert)" : "0 0 6px var(--phos-glow)" }}>
                {safetyOff ? "ARMED ●" : "SAFE ●"}
              </span>
            </span>
          </div>

          <SafetySlider value={safetyOff} onChange={setSafetyOff} disabled={weaponState !== "IDLE"} />

          <div className="text-[10px] text-dim mt-2 tracking-[0.06em]">
            {safetyOff
              ? "SAFETY OFF · DUAL CAMERA 의 표적 BBOX 클릭 시 격발 (좌측으로 드래그하여 잠금)"
              : "SAFETY ON · 우측 끝까지 드래그하여 해제"}
          </div>

          <div className="grid grid-cols-4 gap-1.5 mt-3">
            <FcsTile k="STATE" v={weaponState} tone={weaponState === "FIRE" ? "alert" : "phos"} />
            <FcsTile k="COOLDOWN" v={cooldown > 0 ? `${cooldown.toFixed(1)} s` : "READY"} tone={cooldown > 0 ? "amber" : "phos"} />
            <FcsTile k="FIRE-ID" v={weapon?.fire_id?.slice(0, 6) ?? "—"} tone="ink" />
            <FcsTile k="GATE" v={safetyOff ? "OPEN" : "CLOSED"} tone={safetyOff ? "alert" : "phos"} />
          </div>
        </div>

        {/* COMBINED NAVIGATION & PATROL (6 Columns) */}
        <div className="col-span-12 lg:col-span-6 flex flex-col justify-between">
          <div className="flex justify-between items-baseline mb-2 border-b border-line pb-1.5">
            <span className="font-display tracking-[0.2em] text-[10px] text-phos font-semibold" style={{ textShadow: "0 0 6px var(--phos-glow)" }}>TACTICAL NAVIGATION & PATROL</span>
            <span className="text-[9px] font-mono text-phos" style={{ textShadow: "0 0 6px var(--phos-glow)" }}>NAV/01</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 flex-1">
            {/* Tactical Points Sub-panel */}
            <div className="flex flex-col justify-between h-full">
              <div>
                <div className="grid grid-cols-2 gap-1.5">
                  {TP_LIST.map((tp) => {
                    const isActive = routingState?.tp_id === tp && isRouting;
                    const isSel = selectedTp === tp;
                    return (
                      <button
                        key={tp}
                        onClick={() => handleSelectTp(tp)}
                        data-active={isSel || isActive ? "true" : "false"}
                        data-tone={isActive ? "amber" : isSel ? "phos" : undefined}
                        className="btn !py-1.5 !px-2 !text-[9.5px] !tracking-[0.12em] font-mono normal-case">
                        <span className="flex items-center gap-1">
                          <span className="text-dim text-[8px]">›</span>
                          {TP_LABEL[tp] ?? tp}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="space-y-2 mt-2">
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
                  <div className="text-[9.5px] text-phos font-display tracking-[0.15em] py-0.5">
                    ✓ {routingState.tp_id} ARRIVED
                  </div>
                )}
                {tpError && <div className="text-[9.5px] text-alert">{tpError}</div>}

                <button
                  onClick={handleTpMove}
                  disabled={!selectedTp || tpLoading}
                  data-tone="phos"
                  className="btn w-full !py-2 !text-[10px] !tracking-[0.2em] font-display">
                  {tpLoading ? "TX..." : "이동 명령 / DISPATCH"}
                </button>

                {/* A↔B 반복 순찰 — TP_A → TP_B → TP_A 무한 루프 */}
                <button
                  onClick={async () => {
                    setAbLoading(true);
                    try { await postJSON("/missions/command", { command: "ab_patrol" }); }
                    catch { /* 전송 실패는 patrolMsg 로 표시되지 않으므로 silent */ }
                    finally { setAbLoading(false); }
                  }}
                  disabled={abLoading}
                  data-active={patrolMode === "AB_PATROL" ? "true" : "false"}
                  data-tone={patrolMode === "AB_PATROL" ? "phos" : undefined}
                  className="btn w-full !py-2 !text-[10px] !tracking-[0.14em] font-mono">
                  {abLoading ? "TX..." : patrolMode === "AB_PATROL" ? "● A↔B 순찰 中" : "A↔B 반복 순찰"}
                </button>
              </div>
            </div>

            {/* Patrol Command Sub-panel */}
            <div className="flex flex-col justify-between h-full">
              <div>
                <div className="grid grid-cols-4 gap-1.5">
                  {PATROL_BTNS.map(({ cmd, Icon, title, tone }) => (
                    <button
                      key={cmd}
                      onClick={() => sendPatrolCommand(cmd)}
                      disabled={patrolBusy}
                      title={title}
                      aria-label={title}
                      data-tone={tone}
                      className="btn flex items-center justify-center !py-2.5">
                      <Icon size={14} strokeWidth={1.7} />
                    </button>
                  ))}
                </div>
              </div>

              <div className="mt-2 text-[10px] font-mono tabular space-y-0.5 border-t border-line-2 pt-2">
                {wp && (
                  <div className="flex justify-between">
                    <span className="text-dim tracking-[0.18em]">NEXT WP</span>
                    <span className="text-ink">({wp.x.toFixed(1)}, {wp.y.toFixed(1)})</span>
                  </div>
                )}
                {pose && (
                  <div className="flex justify-between">
                    <span className="text-dim tracking-[0.18em]">POSE</span>
                    <span className="text-ink">
                      ({pose.x.toFixed(1)}, {pose.y.toFixed(1)})
                      <span className="text-dim ml-1.5">{(pose.yaw * 180 / Math.PI).toFixed(0)}°</span>
                    </span>
                  </div>
                )}
                {lmReady === false && (
                  <div className="text-amber text-[9.5px] tracking-[0.12em] animate-pulse">
                    ⚠ LANDMARKS NOT RECEIVED
                  </div>
                )}
                {patrolMsg && <div className="text-amber text-[9.5px] pt-1 truncate">{patrolMsg}</div>}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Safety Gate Alert Toast */}
      {toastMsg && (
        <div className="absolute top-12 left-3 right-3 z-30 border border-amber
                        bg-graphite px-3 py-2 text-[11px] tracking-[0.08em]
                        text-amber font-mono animate-pulse">
          {toastMsg}
        </div>
      )}

      {/* FIRE CONFIRMATION Modal */}
      {pending && (
        <div className="absolute inset-0 bg-black/85 flex items-center justify-center z-20">
          <div className="panel w-11/12 max-w-sm" style={{ borderColor: "var(--alert)" }}>
            <div className="panel-hd" style={{ color: "var(--alert)" }}>
              <span>FIRE CONFIRMATION</span>
              <span className="panel-idx">⚠</span>
            </div>
            <div className="p-3 text-[11px] font-mono space-y-2">
              <div>
                <span className="text-dim tracking-[0.18em] mr-2">TARGET</span>
                <span className="text-ink">{pending.target_label}</span>
              </div>
              {pending.look_at_pixel && (
                <div>
                  <span className="text-dim tracking-[0.18em] mr-2">PIXEL</span>
                  <span className="text-ink tabular">
                    ({pending.look_at_pixel[0].toFixed(0)}, {pending.look_at_pixel[1].toFixed(0)})
                  </span>
                </div>
              )}
            </div>
            <div className="flex gap-2 p-3 pt-1">
              <button onClick={confirmFire} data-tone="alert" className="btn flex-1 !py-3">
                ▲ FIRE
              </button>
              <button onClick={cancelFire} className="btn !py-3 !px-4">
                CANCEL
              </button>
            </div>
          </div>
        </div>
      )}

      {/* HIT JUDGMENT Modal */}
      {resultPending && (
        <div className="absolute inset-0 bg-black/85 flex items-center justify-center z-20">
          <div className="panel w-11/12 max-w-sm" style={{ borderColor: "var(--phos)" }}>
            <div className="panel-hd">
              <span>HIT JUDGMENT</span>
              <span className="panel-idx">◎</span>
            </div>
            <div className="p-3 text-[10px] font-mono space-y-1">
              <div>
                <span className="text-dim tracking-[0.18em] mr-2">FIRE-ID</span>
                <span className="text-ink tabular">{resultPending.fire_id.slice(0, 12)}…</span>
              </div>
              <div>
                <span className="text-dim tracking-[0.18em] mr-2">TARGET</span>
                <span className="text-ink truncate">{resultPending.target}</span>
              </div>
            </div>
            <div className="flex gap-2 p-3 pt-1">
              <button onClick={() => recordResult(true)} data-tone="phos" className="btn flex-1 !py-2.5">
                ✓ HIT
              </button>
              <button onClick={() => recordResult(false, "missed_target")} data-tone="alert" className="btn flex-1 !py-2.5">
                ✗ MISS
              </button>
              <button onClick={() => recordResult(false, "cancelled")} className="btn !py-2.5 !px-3">
                ⊘
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Inner helper components
function FcsTile({ k, v, tone }: { k: string; v: string; tone: "phos" | "amber" | "alert" | "ink" }) {
  const c = tone === "phos" ? "text-phos"
    : tone === "amber" ? "text-amber"
    : tone === "alert" ? "text-alert"
    : "text-ink";
  return (
    <div className="border border-line bg-panel-2 px-1.5 py-1">
      <div className="text-[8px] tracking-[0.2em] text-dim uppercase truncate">{k}</div>
      <div className={`font-display tracking-[0.05em] text-[11px] mt-0.5 truncate ${c}`}>{v}</div>
    </div>
  );
}

function SafetySlider({
  value, onChange, disabled,
}: { value: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState(false);
  const [pct, setPct] = useState(value ? 1 : 0);

  useEffect(() => { if (!value) setPct(0); }, [value]);

  const onPoint = (e: React.PointerEvent | PointerEvent) => {
    if (!trackRef.current) return;
    const rect = trackRef.current.getBoundingClientRect();
    const knobWidth = 56;
    const halfKnob = knobWidth / 2;
    const x = e.clientX - rect.left;
    const range = rect.width - knobWidth;
    const p = range > 0 ? Math.max(0, Math.min(1, (x - halfKnob) / range)) : 0;
    setPct(p);
    if (p >= 0.8 && !value) onChange(true);
    if (p < 0.8 && value) onChange(false);
  };

  useEffect(() => {
    if (!drag) return;
    const move = (e: PointerEvent) => onPoint(e);
    const up = () => {
      setDrag(false);
      if (pct < 0.8) { setPct(0); onChange(false); }
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
  }, [drag, pct]);

  return (
    <div className="select-none">
      <div ref={trackRef}
           className={`relative h-12 border ${value ? "border-alert" : "border-line-2"}
                       ${disabled ? "opacity-40" : "cursor-pointer"}`}
           style={{
             background: value
               ? "linear-gradient(90deg, rgba(255,77,77,0.18), rgba(255,77,77,0.05))"
               : "repeating-linear-gradient(45deg, #0a1410, #0a1410 4px, #0c1714 4px, #0c1714 8px)",
           }}
           onPointerDown={e => {
             if (disabled) return;
             (e.target as Element).setPointerCapture(e.pointerId);
             setDrag(true);
             onPoint(e);
           }}>
        <div className="absolute inset-y-0 left-0"
             style={{
               width: `calc(${pct * 100}% - ${pct * 56}px + 28px)`,
               background: value
                 ? "linear-gradient(90deg, var(--alert-dim), var(--alert))"
                 : "linear-gradient(90deg, var(--phos-dim), var(--amber))",
               opacity: 0.55,
               transition: drag ? "none" : "width 0.2s",
             }} />
        <div className="absolute top-0 bottom-0 w-px" style={{
          left: "80%",
          background: "var(--phos)",
          boxShadow: "0 0 6px var(--phos)",
        }} />
        <div className="absolute inset-0 flex items-center justify-between
                        px-9 text-[10px] font-display tracking-[0.32em] pointer-events-none">
          <span className={`transition-opacity ${pct < 0.2 ? "opacity-0" : ""}
                            ${value ? "text-alert/60" : "text-dim"}`}>
            ◂ SAFE
          </span>
          <span className={`transition-opacity ${pct > 0.85 ? "opacity-0" : ""}
                            ${value ? "text-alert" : "text-dim"}`}>
            ARMED ▸
          </span>
        </div>
        <div className="absolute top-1/2 -translate-y-1/2
                        w-14 h-12 border-2 flex items-center justify-between px-2.5
                        text-[11px] font-display cursor-grab active:cursor-grabbing"
             style={{
               left: `calc(${pct * 100}% - ${pct * 56}px)`,
               background: value ? "var(--alert)" : "var(--graphite)",
               borderColor: value ? "var(--alert)" : "var(--phos)",
               color: value ? "#1a0303" : "var(--phos)",
               boxShadow: value
                 ? "0 0 14px -2px var(--alert)"
                 : "0 0 10px -3px var(--phos)",
               transition: drag ? "none" : "left 0.2s, background 0.2s",
             }}>
          <GripVertical size={11} className="opacity-40" />
          {value ? <Unlock size={13} strokeWidth={2.5} /> : <Lock size={13} strokeWidth={2.5} />}
          <GripVertical size={11} className="opacity-40" />
        </div>
      </div>
    </div>
  );
}
