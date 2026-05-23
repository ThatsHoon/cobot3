"use client";
import { useEffect, useRef, useState } from "react";
import { WeaponState } from "@/lib/api";
import { useWeaponSafety } from "./WeaponSafetyContext";
import { Lock, Unlock, GripVertical } from "lucide-react";

const STATE_TONE: Record<string, string> = {
  IDLE: "text-phos",
  COOLDOWN: "text-amber",
  FIRE: "text-alert animate-pulse",
  RAMP_UP: "text-amber",
  RAMP_DOWN: "text-amber",
  HOLD: "text-amber",
};

export default function WeaponFireControl({
  weapon,
  liveFireEvents,
}: {
  weapon: WeaponState | null;
  liveFireEvents: { fire_id: string | null; target: string }[];
}) {
  const {
    safetyOff, setSafetyOff,
    pending, confirmFire, cancelFire, toastMsg,
  } = useWeaponSafety();

  const [resultPending, setResultPending] =
    useState<{ fire_id: string; target: string } | null>(null);
  const seenRef = useRef<Set<string>>(new Set());
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
      const { postJSON, ROBOT_ID } = await import("@/lib/api");
      await postJSON(`/robots/${ROBOT_ID}/fire/result`,
        { fire_id: resultPending.fire_id, hit, miss_reason });
    } catch (e) { console.error(e); }
    finally { setResultPending(null); }
  };

  const state = weapon?.state ?? "IDLE";
  const cooldown = weapon?.cooldown_remaining_s ?? 0;
  const stateColor = STATE_TONE[state] ?? "text-ink-2";

  return (
    <div className="panel relative">
      <div className="panel-hd">
        <span>WEAPON · HITL</span>
        <span className="flex items-center gap-2">
          <span className="panel-idx">FCS/01</span>
          <span className={`font-display tracking-[0.22em] text-[11px] ${stateColor}`}>
            {state}
            {cooldown > 0 ? <span className="ml-1 tabular">{cooldown.toFixed(1)}s</span> : null}
          </span>
        </span>
      </div>

      <div className="p-3 grid grid-cols-12 gap-3">
        {/* 좌측 6col — SAFETY 게이트 */}
        <div className="col-span-12 lg:col-span-6">
          <div className="flex items-baseline justify-between mb-1.5">
            <span className="font-display tracking-[0.32em] text-[10px] text-dim">
              SAFETY GATE
            </span>
            <span className="font-display tracking-[0.22em] text-[10px]">
              <span className={safetyOff ? "text-alert" : "text-phos"}>
                {safetyOff ? "ARMED ●" : "SAFE ●"}
              </span>
            </span>
          </div>
          <SafetySlider value={safetyOff} onChange={setSafetyOff}
                        disabled={state !== "IDLE"} />
          <div className="text-[10px] text-dim mt-2 tracking-[0.06em]">
            {safetyOff
              ? <>SAFETY OFF · DUAL CAMERA 의 표적 BBOX 클릭 시 격발 (좌측으로 드래그하여 잠금)</>
              : <>SAFETY ON · 우측 끝까지 드래그하여 해제</>}
          </div>
        </div>

        {/* 우측 6col — 상태 라이트 패널 */}
        <div className="col-span-12 lg:col-span-6 grid grid-cols-2 gap-2">
          <FcsTile k="STATE" v={state} tone={state === "FIRE" ? "alert" : "phos"} />
          <FcsTile k="COOLDOWN" v={cooldown > 0 ? `${cooldown.toFixed(1)} s` : "READY"}
                   tone={cooldown > 0 ? "amber" : "phos"} />
          <FcsTile k="FIRE-ID" v={weapon?.fire_id?.slice(0, 6) ?? "—"} tone="ink" />
          <FcsTile k="GATE" v={safetyOff ? "OPEN" : "CLOSED"}
                   tone={safetyOff ? "alert" : "phos"} />
        </div>
      </div>

      {/* Toast (안전장치 알림) */}
      {toastMsg && (
        <div className="absolute top-12 left-3 right-3 z-30 border border-amber
                        bg-graphite px-3 py-2 text-[11px] tracking-[0.08em]
                        text-amber font-mono animate-pulse">
          {toastMsg}
        </div>
      )}

      {/* 격발 확인 모달 */}
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
              <button onClick={confirmFire}
                      data-tone="alert" className="btn flex-1 !py-3">
                ▲ FIRE
              </button>
              <button onClick={cancelFire} className="btn !py-3 !px-4">
                CANCEL
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 결과 판정 모달 */}
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
              <button onClick={() => recordResult(true)}
                      data-tone="phos" className="btn flex-1 !py-2.5">
                ✓ HIT
              </button>
              <button onClick={() => recordResult(false, "missed_target")}
                      data-tone="alert" className="btn flex-1 !py-2.5">
                ✗ MISS
              </button>
              <button onClick={() => recordResult(false, "cancelled")}
                      className="btn !py-2.5 !px-3">
                ⊘
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function FcsTile({ k, v, tone }: { k: string; v: string; tone: "phos" | "amber" | "alert" | "ink" }) {
  const c = tone === "phos" ? "text-phos"
    : tone === "amber" ? "text-amber"
    : tone === "alert" ? "text-alert"
    : "text-ink";
  return (
    <div className="border border-line bg-panel-2 px-2.5 py-1.5">
      <div className="text-[8.5px] tracking-[0.34em] text-dim uppercase">{k}</div>
      <div className={`font-display tracking-[0.1em] text-[12.5px] mt-0.5 truncate ${c}`}>{v}</div>
    </div>
  );
}

/** Drag-to-arm 안전장치 슬라이더. 80% 이상 당기면 OFF. */
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
    const x = e.clientX - rect.left;
    const p = Math.max(0, Math.min(1, x / rect.width));
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
        {/* 채워지는 fill */}
        <div className="absolute inset-y-0 left-0 transition-[width]"
             style={{
               width: `${pct * 100}%`,
               background: value
                 ? "linear-gradient(90deg, var(--alert-dim), var(--alert))"
                 : "linear-gradient(90deg, var(--phos-dim), var(--amber))",
               opacity: 0.55,
             }} />
        {/* 80% threshold marker */}
        <div className="absolute top-0 bottom-0 w-px" style={{
          left: "80%",
          background: "var(--phos)",
          boxShadow: "0 0 6px var(--phos)",
        }} />
        {/* 좌·우 라벨 (knob 영역은 회피) */}
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
        {/* knob */}
        <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2
                        w-14 h-12 border-2 flex items-center justify-between px-2.5
                        text-[11px] font-display cursor-grab active:cursor-grabbing"
             style={{
               left: `${pct * 100}%`,
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
