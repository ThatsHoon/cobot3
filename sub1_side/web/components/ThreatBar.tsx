"use client";
import { useEffect, useState } from "react";

export type Contact = {
  ts: string;
  class_name: string;
  conf: number;
  bbox: number[];
};

/** 최상위 위협 상태 — 담당자가 가장 먼저 보는 한 줄. */
export default function ThreatBar({
  contact,
  lastTs,
}: {
  contact: Contact | null;
  lastTs: number | null;
}) {
  const [age, setAge] = useState(0);
  useEffect(() => {
    const iv = setInterval(
      () => setAge(lastTs ? (Date.now() - lastTs) / 1000 : 0),
      250
    );
    return () => clearInterval(iv);
  }, [lastTs]);

  const active = !!contact;

  return (
    <div className={`threat ${active ? "contact" : ""} flex items-stretch`}>
      <span className="threat-rail" />
      <div className="flex-1 flex items-center justify-between px-5 py-3">
        <div className="flex items-center gap-5">
          <div
            className="font-display text-3xl tracking-[0.18em]"
            style={{ color: active ? "var(--alert)" : "var(--phos)" }}
          >
            {active ? "● 접촉 / CONTACT" : "○ 경계 정상 / SECURE"}
          </div>
          {active && (
            <div className="text-sm text-ink leading-tight">
              <div className="tracking-widest">
                {contact!.class_name.toUpperCase()} ·{" "}
                <span className="text-alert">
                  {(contact!.conf * 100).toFixed(0)}%
                </span>
              </div>
              <div className="text-[11px] text-dim">
                마지막 탐지 {age.toFixed(1)}s 전
              </div>
            </div>
          )}
        </div>
        <div className="text-right text-[11px] tracking-[0.25em] text-dim">
          {active ? (
            <span className="text-amber">교전 절차 활성 — 확성기 경고 후 사격</span>
          ) : (
            <span>철조망 경계선 감시중 · 이상 없음</span>
          )}
        </div>
      </div>
    </div>
  );
}
