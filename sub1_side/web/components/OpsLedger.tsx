"use client";

export type LedgerItem = {
  ts: string;
  sev: "info" | "warn" | "alert" | "hit";
  tag: string;
  msg: string;
};

const SEV_C: Record<LedgerItem["sev"], string> = {
  info: "text-dim",
  warn: "text-amber",
  alert: "text-alert",
  hit: "text-phos",
};

/**
 * 작전 로그 — 탐지·사격·rosout WARN 을 시간순 단일 원장으로 통합.
 * 담당자는 분산된 로그가 아니라 "사건의 흐름"을 본다.
 */
export default function OpsLedger({ items }: { items: LedgerItem[] }) {
  // 자동 하단 스크롤 제거 — 사용자가 스크롤 위치를 직접 제어

  return (
    <div className="panel h-full flex flex-col">
      <div className="panel-hd">
        <span>OPERATIONS LEDGER · 작전 로그</span>
        <span className="text-dim">{items.length}</span>
      </div>
      <div className="flex-1 overflow-auto px-3 py-2 text-[12px]">
        {items.length === 0 && (
          <div className="text-dim">사건 없음 — 탐지·사격·경고 통합 표시</div>
        )}
        {items.map((it, i) => (
          <div
            key={i}
            className={`led-row sev-${it.sev} pl-2 py-1 mb-0.5 flex gap-2`}
          >
            <span className="text-dim shrink-0">{it.ts.slice(11, 19)}</span>
            <span
              className={`${SEV_C[it.sev]} shrink-0 w-16 tracking-wider`}
            >
              {it.tag}
            </span>
            <span className="text-ink break-all">{it.msg}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
