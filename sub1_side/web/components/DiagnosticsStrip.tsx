"use client";
import { useState } from "react";

/**
 * 관절 텔레메트리는 운영보다 엔지니어링 데이터 — 슬림 접이식 스트립으로 강등.
 * 평소 접힘, 필요 시 펼쳐 m0609 q[6] / ANYmal q[12] 확인.
 */
export default function DiagnosticsStrip({
  armQ,
  legQ,
}: {
  armQ: number[];
  legQ: number[];
}) {
  const [open, setOpen] = useState(true);
  const bars = (arr: number[], n: number, color: string, scale: number) =>
    (arr.length ? arr : Array(n).fill(null)).map((q, i) => (
      <div key={i} className="spark h-7 flex-1">
        <i
          style={{
            height: q == null ? 0 : `${Math.min(100, Math.abs(q) * scale)}%`,
            background: color,
          }}
        />
      </div>
    ));

  return (
    <div className="panel">
      <button
        onClick={() => setOpen((o) => !o)}
        className="panel-hd w-full text-left"
      >
        <span>DIAGNOSTICS · 관절 텔레메트리</span>
        <span className="text-dim">{open ? "▲ 접기" : "▼ 펼치기"}</span>
      </button>
      {open && (
        <div className="p-3 grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div>
            <div className="text-[10px] text-dim tracking-[0.2em] mb-1">
              ARM · m0609 q[6]
            </div>
            <div className="flex gap-1">
              {bars(armQ, 6, "var(--phos)", 30)}
            </div>
          </div>
          <div>
            <div className="text-[10px] text-dim tracking-[0.2em] mb-1">
              LEG · ANYmal q[12]
            </div>
            <div className="flex gap-0.5">
              {bars(legQ, 12, "var(--amber)", 25)}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
