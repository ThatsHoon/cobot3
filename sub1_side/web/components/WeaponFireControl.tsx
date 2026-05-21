"use client";
import { useEffect, useRef, useState } from "react";
import { WeaponState } from "@/lib/api";
import { useWeaponSafety } from "./WeaponSafetyContext";

/** 무기 콘솔 — 안전장치 드래그 바 + weapon state + 격발 확인 모달 + 결과 모달.
 *  영상은 DualCameraView 에서만 표시. 격발 trigger 는 DualCameraView 의
 *  bbox/좌표 클릭 → useWeaponSafety.requestFire() → 여기서 모달.
 *
 *  안전장치: 좌→우 드래그 80% 이상 → safety_off=true. 격발 후 자동 잠금.
 */
export default function WeaponFireControl({
  weapon,
  liveFireEvents,
}: {
  weapon: WeaponState | null;
  liveFireEvents: { fire_id: string | null; target: string }[];
}) {
  const { safetyOff, setSafetyOff,
          pending, confirmFire, cancelFire,
          toastMsg } = useWeaponSafety();

  // 결과 모달 (Hit/Miss) — fire_result 는 자동 띄움 (기존 흐름 유지)
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
  const stateColor =
    state === "IDLE"     ? "text-phos" :
    state === "COOLDOWN" ? "text-amber-400" :
    state === "FIRE"     ? "text-rose-500 animate-pulse" :
    "text-yellow-300";

  return (
    <div className="panel relative">
      <div className="panel-hd">
        <span>WEAPON · HITL</span>
        <span className={`text-[10px] tracking-widest ${stateColor}`}>
          {state}{cooldown > 0 ? ` · ${cooldown.toFixed(1)}s` : ""}
        </span>
      </div>
      <div className="p-3 flex flex-col gap-3">
        <SafetySlider value={safetyOff} onChange={setSafetyOff}
                      disabled={state !== "IDLE"} />
        <div className="text-[10px] text-dim leading-relaxed">
          {safetyOff
            ? "✅ SAFETY OFF — DUAL CAMERA 에서 표적 클릭으로 격발 (격발 후 자동 잠김)"
            : "🔒 SAFETY ON — 우측 끝까지 드래그하여 해제"}
        </div>
      </div>

      {/* Toast (안전장치 알림) */}
      {toastMsg && (
        <div className="absolute top-12 left-2 right-2 z-30 bg-amber-600 text-white
                        px-3 py-2 text-[12px] rounded shadow-lg animate-pulse">
          {toastMsg}
        </div>
      )}

      {/* 격발 확인 모달 */}
      {pending && (
        <div className="absolute inset-0 bg-black/85 flex items-center justify-center z-20">
          <div className="bg-zinc-900 border-2 border-rose-500 p-4 rounded max-w-sm w-11/12">
            <div className="text-rose-400 font-display tracking-widest mb-2 text-base">
              ⚠ FIRE CONFIRMATION
            </div>
            <div className="text-[11px] text-dim mb-3 font-mono">
              target: <span className="text-ink">{pending.target_label}</span>
              {pending.look_at_pixel && (
                <span className="block">
                  pixel: ({pending.look_at_pixel[0].toFixed(0)},
                  {pending.look_at_pixel[1].toFixed(0)})
                </span>
              )}
            </div>
            <div className="flex gap-2">
              <button onClick={confirmFire}
                className="flex-1 py-3 bg-rose-600 hover:bg-rose-500 text-white
                           font-display tracking-widest">
                🎯 FIRE
              </button>
              <button onClick={cancelFire}
                className="px-4 py-3 bg-zinc-700 hover:bg-zinc-600 text-white">
                CANCEL
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 결과 판정 모달 (사격 완료 후 자동) */}
      {resultPending && (
        <div className="absolute inset-0 bg-black/85 flex items-center justify-center z-20">
          <div className="bg-zinc-900 border-2 border-phos p-4 rounded max-w-sm w-11/12">
            <div className="text-phos font-display tracking-widest mb-2">
              🎯 HIT JUDGMENT
            </div>
            <div className="text-[10px] text-dim mb-3 font-mono break-all">
              fire_id: {resultPending.fire_id.slice(0, 8)}…<br/>
              target: {resultPending.target}
            </div>
            <div className="flex gap-2">
              <button onClick={() => recordResult(true)}
                className="flex-1 py-2 bg-emerald-600 hover:bg-emerald-500 text-white">
                ✓ HIT
              </button>
              <button onClick={() => recordResult(false, "missed_target")}
                className="flex-1 py-2 bg-rose-600 hover:bg-rose-500 text-white">
                ✗ MISS
              </button>
              <button onClick={() => recordResult(false, "cancelled")}
                className="px-2 py-2 bg-zinc-700 hover:bg-zinc-600 text-white">
                ⊘
              </button>
            </div>
          </div>
        </div>
      )}
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

  // value 가 외부에서 false 로 reset 되면 슬라이더도 0
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
      // 80% 미만이면 0 으로 스냅백
      if (pct < 0.8) { setPct(0); onChange(false); }
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
  }, [drag, pct]);

  const barColor = value ? "bg-rose-600" : disabled ? "bg-zinc-600" : "bg-amber-500";
  const labelLeft = value ? "OFF" : "ARM →";
  const labelRight = value ? "ARMED" : "SAFE";

  return (
    <div className="select-none">
      <div className="flex justify-between text-[10px] tracking-widest mb-1">
        <span className="text-zinc-500">{labelLeft}</span>
        <span className={value ? "text-rose-400" : "text-emerald-400"}>{labelRight}</span>
      </div>
      <div ref={trackRef}
           className={`relative h-9 rounded-sm border-2 ${value
             ? "border-rose-500 bg-rose-950/40"
             : "border-line bg-zinc-900"} ${disabled ? "opacity-40" : "cursor-pointer"}`}
           onPointerDown={e => {
             if (disabled) return;
             (e.target as Element).setPointerCapture(e.pointerId);
             setDrag(true);
             onPoint(e);
           }}>
        {/* fill */}
        <div className={`absolute inset-y-0 left-0 ${barColor} opacity-50
                         transition-[width] ${drag ? "" : "duration-200"}`}
             style={{ width: `${pct * 100}%` }} />
        {/* knob */}
        <div className={`absolute top-1/2 -translate-y-1/2 -translate-x-1/2
                         w-8 h-8 rounded ${barColor} border-2 border-black
                         shadow-lg flex items-center justify-center`}
             style={{ left: `${pct * 100}%`,
                      transition: drag ? "none" : "left 0.2s" }}>
          <span className="text-[14px] text-white">{value ? "🔓" : "🔒"}</span>
        </div>
        {/* threshold marker */}
        <div className="absolute top-0 bottom-0 w-px bg-zinc-600"
             style={{ left: "80%" }} />
      </div>
    </div>
  );
}
