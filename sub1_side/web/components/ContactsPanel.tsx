"use client";
import { Contact } from "./ThreatBar";

/** 최근 탐지 접촉 목록 — 영상 옆에 두어 "무엇이/얼마나 확실히" 즉시 파악. */
export default function ContactsPanel({ items }: { items: Contact[] }) {
  return (
    <div className="panel h-full flex flex-col">
      <div className="panel-hd">
        <span>CONTACTS · 탐지 접촉</span>
        <span className={items.length ? "text-alert" : "text-dim"}>
          {items.length}
        </span>
      </div>
      <div className="flex-1 overflow-auto">
        {items.length === 0 && (
          <div className="p-4 text-[12px] text-dim tracking-wide">
            탐지 없음 — YOLO 분석 대기
          </div>
        )}
        {items.map((c, i) => (
          <div
            key={i}
            className="px-4 py-2.5 border-b border-line/60 flex items-center gap-3"
          >
            <div
              className="w-1.5 self-stretch"
              style={{ background: "var(--alert)" }}
            />
            <div className="flex-1 min-w-0">
              <div className="flex justify-between text-[13px]">
                <span className="tracking-widest text-ink">
                  {c.class_name.toUpperCase()}
                </span>
                <span className="text-dim">{c.ts.slice(11, 19)}</span>
              </div>
              <div className="mt-1 h-1.5 bg-line">
                <div
                  className="h-full bg-alert"
                  style={{ width: `${Math.min(100, c.conf * 100)}%` }}
                />
              </div>
              <div className="text-[10px] text-dim mt-1">
                conf {(c.conf * 100).toFixed(0)}% · bbox{" "}
                {c.bbox.map((v) => v.toFixed(0)).join(",")}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
