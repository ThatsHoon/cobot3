"use client";
import { useEffect, useRef, useState } from "react";
import { postJSON, getApiBase, ROBOT_ID, WeaponState } from "@/lib/api";

/** HITL 사격 패널 — inspect 카메라 위 crosshair + FIRE 버튼 + 결과 모달.
 *  AlertsLog 의 [TRACK] 버튼이 alert bbox 중심으로 inspect 카메라 회전.
 *  운용자가 inspect 영상의 crosshair 가 표적 정중앙인 것 확인 후 FIRE.
 *  사격 후 자동 [Hit / Miss / Cancel] 모달.
 */
type PendingResult = { fire_id: string; target: string };

export default function WeaponFireControl({
  weapon,
  liveFireEvents,
}: {
  weapon: WeaponState | null;
  liveFireEvents: { fire_id: string | null; target: string }[];
}) {
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<PendingResult | null>(null);
  const [lastErr, setLastErr] = useState<string | null>(null);
  // 마지막 fire 자동으로 모달 띄움
  const seenRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    for (const e of liveFireEvents) {
      if (e.fire_id && !seenRef.current.has(e.fire_id)) {
        seenRef.current.add(e.fire_id);
        setPending({ fire_id: e.fire_id, target: e.target });
      }
    }
  }, [liveFireEvents]);

  const fire = async () => {
    if (busy || weapon?.state !== "IDLE") return;
    setBusy(true); setLastErr(null);
    try {
      await postJSON(`/robots/${ROBOT_ID}/fire`,
        { target: "operator_selected", operator: "c2" });
    } catch (e: any) {
      setLastErr(String(e?.message || e));
    } finally {
      setBusy(false);
    }
  };

  const recordResult = async (hit: boolean, miss_reason?: string) => {
    if (!pending) return;
    try {
      await postJSON(`/robots/${ROBOT_ID}/fire/result`,
        { fire_id: pending.fire_id, hit, miss_reason });
    } catch (e) {
      console.error("fire/result POST", e);
    } finally {
      setPending(null);
    }
  };

  const state = weapon?.state ?? "IDLE";
  const cooldown = weapon?.cooldown_remaining_s ?? 0;
  const canFire = state === "IDLE" && cooldown === 0 && !busy;
  const stateColor =
    state === "IDLE"      ? "text-phos" :
    state === "COOLDOWN"  ? "text-amber-400" :
    state === "FIRE"      ? "text-rose-500 animate-pulse" :
    "text-yellow-300";

  const mjpegSrc = `${getApiBase()}/c2/video/mjpeg?camera=inspect`;

  return (
    <div className="panel relative">
      <div className="panel-hd">
        <span>WEAPON · HITL</span>
        <span className={`text-[10px] tracking-widest ${stateColor}`}>{state}</span>
      </div>
      <div className="relative aspect-video bg-black">
        <img src={mjpegSrc} alt="inspect" className="w-full h-full object-cover" />
        {/* Crosshair overlay (muzzle 방향 = inspect 중심) */}
        <svg className="absolute inset-0 w-full h-full pointer-events-none"
             viewBox="0 0 100 100" preserveAspectRatio="none">
          <line x1="50" y1="42" x2="50" y2="58" stroke="rgba(255,80,80,0.85)"
                strokeWidth="0.35" vectorEffect="non-scaling-stroke" />
          <line x1="42" y1="50" x2="58" y2="50" stroke="rgba(255,80,80,0.85)"
                strokeWidth="0.35" vectorEffect="non-scaling-stroke" />
          <circle cx="50" cy="50" r="3.2" stroke="rgba(255,80,80,0.55)"
                  strokeWidth="0.25" fill="none"
                  vectorEffect="non-scaling-stroke" />
          <circle cx="50" cy="50" r="0.5" fill="rgba(255,80,80,0.9)" />
        </svg>
        <div className="absolute top-2 left-2 text-[10px] text-phos font-mono
                        bg-black/60 px-2 py-0.5 tracking-wider">
          INSPECT · CROSSHAIR (= weapon dir)
        </div>
      </div>
      <div className="p-2 flex items-center gap-3">
        <button onClick={fire} disabled={!canFire}
          className={`flex-1 px-3 py-3 rounded font-display tracking-widest
                      ${canFire ? "bg-rose-600 hover:bg-rose-500 text-white"
                               : "bg-zinc-700/60 text-dim cursor-not-allowed"}`}>
          {state === "COOLDOWN" ? `COOLDOWN ${cooldown.toFixed(1)}s` :
           state === "IDLE"    ? "🎯 FIRE" : state}
        </button>
        <div className="text-[10px] text-dim leading-tight">
          alert TRACK<br/>→ inspect 회전<br/>→ FIRE
        </div>
      </div>
      {lastErr && (
        <div className="px-2 pb-2 text-[10px] text-rose-400">err: {lastErr}</div>
      )}

      {/* 결과 판정 모달 */}
      {pending && (
        <div className="absolute inset-0 bg-black/85 flex items-center justify-center z-20">
          <div className="bg-zinc-900 border-2 border-phos p-4 rounded max-w-xs w-11/12">
            <div className="text-phos font-display tracking-widest mb-2">
              🎯 HIT JUDGMENT
            </div>
            <div className="text-[10px] text-dim mb-3 font-mono break-all">
              fire_id: {pending.fire_id.slice(0, 8)}…
              <br/>target: {pending.target}
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
