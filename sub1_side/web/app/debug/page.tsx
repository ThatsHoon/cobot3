"use client";

import { LICHTBLICK_URL } from "@/lib/api";

// 디버그 전용 페이지 — Lichtblick(Foxglove) 뷰어를 iframe 으로 임베드한다.
// 메인 콘솔(/) 은 건드리지 않는다(별 라우트, 루트 layout 자동 상속).
// 같은-PC 임시 모드에서는 web_server(C2_INGEST_REPUBLISH=1)가 /ingest 로
// 받은 텔레메트리를 ROS2 로 재발행 → foxglove_bridge(:8765) → Lichtblick.
export default function DebugPage() {
  const src = `${LICHTBLICK_URL}/?ds=foxglove-websocket&ds.url=ws://localhost:8765`;
  return (
    <main className="relative z-10 min-h-screen p-4 flex flex-col gap-3">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="font-display text-xl tracking-[0.28em] text-phos">
            DEBUG · FOXGLOVE
          </h1>
          <p className="text-[10px] text-dim tracking-[0.35em] mt-0.5">
            LICHTBLICK · ROS2 텔레메트리/영상 진단
          </p>
        </div>
        <div className="text-right text-[10px] text-dim leading-relaxed">
          <span className="text-ink">{LICHTBLICK_URL}</span>
          <br />
          ws://localhost:8765 (foxglove_bridge)
        </div>
      </header>

      <div className="panel flex-1 min-h-0 flex flex-col">
        <div className="panel-hd">
          <span>VIEWER</span>
          <span className="text-phos">LIVE</span>
        </div>
        <div className="flex-1 min-h-0 bg-black">
          <iframe
            src={src}
            title="Lichtblick"
            className="w-full h-full border-0"
            allow="fullscreen"
          />
        </div>
      </div>
    </main>
  );
}
