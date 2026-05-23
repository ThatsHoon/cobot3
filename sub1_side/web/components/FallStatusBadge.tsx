"use client";
import { useEffect, useRef, useState } from "react";
import { FallPayload } from "@/lib/api";

/** FALL 감지 배지 — fall_alert 이벤트 수신 시 우상단 헤더 옆에 표시.
 *  FALLEN=빨강 깜빡임, RECOVERING=주황 stage 표시, RECOVERED=초록 5초 후 자동 숨김.
 *  UPRIGHT 가 들어오거나 8초 안에 새 알람 없으면 자동 사라짐.
 */
export default function FallStatusBadge({
  liveFallEvents,
}: {
  liveFallEvents: { ts: string; data: FallPayload }[];
}) {
  const [cur, setCur] = useState<FallPayload | null>(null);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!liveFallEvents.length) return;
    const last = liveFallEvents[liveFallEvents.length - 1].data;
    setCur(last);
    if (hideTimer.current) clearTimeout(hideTimer.current);
    // RECOVERED/UPRIGHT 는 5초 후 자동 숨김. FALLEN/RECOVERING 은 계속 표시.
    if (last.state === "RECOVERED" || last.state === "UPRIGHT") {
      hideTimer.current = setTimeout(() => setCur(null), 5000);
    }
  }, [liveFallEvents]);

  if (!cur) return null;

  const style =
    cur.state === "FALLEN"     ? "bg-rose-600/90  text-white animate-pulse" :
    cur.state === "RECOVERING" ? "bg-amber-500/90 text-black" :
    cur.state === "RECOVERED"  ? "bg-emerald-600/80 text-white" :
                                 "bg-zinc-700/60  text-white";
  const icon =
    cur.state === "FALLEN"     ? "⚠" :
    cur.state === "RECOVERING" ? "↻" :
    cur.state === "RECOVERED"  ? "✓" : "●";
  const label =
    cur.state === "FALLEN"     ? "ROBOT FALL" :
    cur.state === "RECOVERING" ? `RECOVERING (stage ${cur.stage ?? "?"}/3)` :
    cur.state === "RECOVERED"  ? "RECOVERED" :
                                 "UPRIGHT";

  return (
    <span className={`flex items-center gap-1.5 px-2 py-0.5 rounded
                      text-[11px] font-mono tracking-wider ${style}`}>
      <span className="text-[13px] leading-none">{icon}</span>
      <span>{label}</span>
      <span className="opacity-70">
        up_z={cur.up_z.toFixed(2)}
      </span>
    </span>
  );
}
