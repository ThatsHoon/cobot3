"use client";
import { useState } from "react";

/**
 * Go2 12-DOF 관절 텔레메트리.
 * 2026-05-24: 구 M0609 arm + ANYmal leg 표시 제거. Go2 4족 12-DOF 만 표시.
 *
 * 관절 순서 (Unitree Go2 walk-these-ways 정책 기준, /robot/leg_joint_states):
 *   FL_hip, FL_thigh, FL_calf,
 *   FR_hip, FR_thigh, FR_calf,
 *   RL_hip, RL_thigh, RL_calf,
 *   RR_hip, RR_thigh, RR_calf
 */

const LEGS = [
  { id: "FL", label: "FL · Front Left",  color: "var(--phos)" },
  { id: "FR", label: "FR · Front Right", color: "var(--amber)" },
  { id: "RL", label: "RL · Rear Left",   color: "var(--phos)" },
  { id: "RR", label: "RR · Rear Right",  color: "var(--amber)" },
];
const JOINTS = ["hip", "thigh", "calf"];

export default function DiagnosticsStrip({
  legQ,
}: {
  legQ: number[];
}) {
  const [open, setOpen] = useState(true);

  // 12-DOF 를 4×3 으로 분할
  const cells = (legIdx: number) => {
    const start = legIdx * 3;
    return JOINTS.map((joint, j) => {
      const q = legQ[start + j];
      const has = typeof q === "number" && isFinite(q);
      // rad 기준 ±π/2 를 100% 로 매핑 (대부분 관절 가동범위 내)
      const pct = has ? Math.min(100, (Math.abs(q!) / (Math.PI / 2)) * 100) : 0;
      return { joint, q: has ? q! : null, pct };
    });
  };

  return (
    <div className="panel">
      <button
        onClick={() => setOpen((o) => !o)}
        className="panel-hd w-full text-left"
      >
        <span>
          DIAGNOSTICS · Go2 12-DOF JOINT TELEMETRY
          {legQ.length === 0 && (
            <span className="ml-2 text-dim text-[10px]">(no data)</span>
          )}
        </span>
        <span className="text-dim">{open ? "▲ 접기" : "▼ 펼치기"}</span>
      </button>
      {open && (
        <div className="p-3 grid grid-cols-2 lg:grid-cols-4 gap-3">
          {LEGS.map((leg, li) => (
            <div key={leg.id}>
              <div className="text-[10px] text-dim tracking-[0.2em] mb-1 flex justify-between">
                <span>{leg.label}</span>
                <span className="font-mono text-[9px] text-dim">
                  q[{li * 3}-{li * 3 + 2}]
                </span>
              </div>
              <div className="flex gap-1">
                {cells(li).map((c) => (
                  <div key={c.joint} className="flex-1">
                    <div className="text-[8px] text-dim text-center mb-0.5">
                      {c.joint}
                    </div>
                    <div className="spark h-10">
                      <i
                        style={{
                          height: `${c.pct}%`,
                          background: leg.color,
                        }}
                      />
                    </div>
                    <div className="text-[9px] font-mono text-center mt-0.5 leading-tight">
                      {c.q == null
                        ? <span className="text-dim">—</span>
                        : <span className="text-ink">{c.q.toFixed(2)}</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
