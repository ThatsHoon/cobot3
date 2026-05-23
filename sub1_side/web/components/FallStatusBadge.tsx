"use client";
import { useEffect, useRef, useState } from "react";
import { FallPayload } from "@/lib/api";

/** FALL 감지 배지 — fall_alert 이벤트 수신 시 표시. 헤더 row(h-14) 안에 들어감. */
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
    if (last.state === "RECOVERED" || last.state === "UPRIGHT") {
      hideTimer.current = setTimeout(() => setCur(null), 5000);
    }
  }, [liveFallEvents]);

  if (!cur) return null;

  const tone =
    cur.state === "FALLEN"     ? { border: "border-alert", text: "text-alert", pulse: "animate-pulse" } :
    cur.state === "RECOVERING" ? { border: "border-amber", text: "text-amber", pulse: "" } :
    cur.state === "RECOVERED"  ? { border: "border-phos",  text: "text-phos",  pulse: "" } :
                                  { border: "border-line", text: "text-ink-2", pulse: "" };
  const icon =
    cur.state === "FALLEN"     ? "▲" :
    cur.state === "RECOVERING" ? "↻" :
    cur.state === "RECOVERED"  ? "✓" : "●";
  const label =
    cur.state === "FALLEN"     ? "ROBOT FALL" :
    cur.state === "RECOVERING" ? `RECOVERING ${cur.stage ?? "?"}/3` :
    cur.state === "RECOVERED"  ? "RECOVERED" :
                                  "UPRIGHT";

  return (
    <div className={`flex items-center gap-1.5 px-2.5 h-full text-[10px] font-display
                     tracking-[0.2em] border-l ${tone.border} ${tone.text} ${tone.pulse}`}
         style={{ background: cur.state === "FALLEN" ? "rgba(255,77,77,0.08)" : undefined }}>
      <span className="text-[12px] leading-none">{icon}</span>
      <span>{label}</span>
      <span className="text-dim text-[8.5px] ml-1 tabular">
        UP={cur.up_z.toFixed(2)}
      </span>
    </div>
  );
}
