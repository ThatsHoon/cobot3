"use client";
import { useEffect, useState } from "react";
import { ROBOT_ID, LandmarksPayload } from "@/lib/api";

/** 상단 헤더 — robot id, WS 연결, zone, 현지 시간 */
export default function StatusHeader({
  wsOk,
  landmarks,
}: {
  wsOk: boolean;
  landmarks: LandmarksPayload | null;
}) {
  const [time, setTime] = useState<string>("");
  const [date, setDate] = useState<string>("");
  useEffect(() => {
    const tick = () => {
      const d = new Date();
      setTime(d.toLocaleTimeString("en-GB"));
      setDate(d.toISOString().slice(0, 10));
    };
    tick();
    const iv = setInterval(tick, 1000);
    return () => clearInterval(iv);
  }, []);

  const zone = landmarks?.zone ?? "?";

  return (
    <header className="flex items-stretch h-full
                       bg-gradient-to-b from-black/55 to-transparent">
      {/* 좌측 워드마크 */}
      <div className="flex items-center gap-4 pl-4 pr-5 border-r border-line">
        <div className="flex flex-col leading-none">
          <span className="text-[8.5px] tracking-[0.36em] text-dim">
            CMD&nbsp;·&nbsp;CTRL&nbsp;·&nbsp;01&nbsp;&nbsp;STN/C2-01
          </span>
          <h1 className="font-display text-[18px] tracking-[0.22em] text-phos
                         mt-1"
              style={{ textShadow: "0 0 14px rgba(70,244,168,0.45)" }}>
            GP&nbsp;·&nbsp;C<sub className="text-[11px] tracking-normal">2</sub>
          </h1>
        </div>
        <div className="flex flex-col gap-0.5 leading-none">
          <span className="text-[8.5px] tracking-[0.36em] text-dim">QUADRUPED OPS CONSOLE</span>
          <span className="text-[8.5px] tracking-[0.36em] text-phos/70">
            BORDER&nbsp;·&nbsp;SECTOR&nbsp;A
          </span>
        </div>
      </div>

      {/* 가운데: 미션 메타 */}
      <div className="flex items-center gap-5 px-5 text-[10px] font-mono tabular">
        <Meta k="UNIT" v={ROBOT_ID.toUpperCase()} tone="phos" />
        <Meta k="ZONE" v={zone.toUpperCase()} tone={zone === "dmz" ? "amber" : "phos"} />
        <Meta k="MODE" v="C2 / LAN+TUNNEL" tone="ink" />
      </div>

      {/* 우측: 연결·시계 */}
      <div className="ml-auto flex items-stretch divide-x divide-line border-l border-line">
        <div className="flex items-center gap-2 px-4 text-[10px] font-display tracking-[0.28em]">
          <span className={`led ${wsOk ? "" : "opacity-40"}`}
                style={{ color: wsOk ? "var(--phos)" : "var(--alert)" }} />
          <span className={wsOk ? "text-phos" : "text-alert"}>
            {wsOk ? "STREAM" : "OFFLINE"}
          </span>
        </div>
        <div className="flex flex-col justify-center px-4 text-right leading-none">
          <span className="text-[8.5px] tracking-[0.3em] text-dim mb-0.5">UTC LOCAL</span>
          <span className="font-display tracking-[0.12em] text-[15px] text-ink tabular">
            {time || "--:--:--"}
          </span>
          <span className="text-[8.5px] text-dim tracking-[0.18em] mt-0.5">{date}</span>
        </div>
      </div>
    </header>
  );
}

function Meta({
  k, v, tone,
}: { k: string; v: string; tone: "phos" | "amber" | "alert" | "ink" }) {
  const c =
    tone === "phos" ? "text-phos" :
    tone === "amber" ? "text-amber" :
    tone === "alert" ? "text-alert" : "text-ink";
  return (
    <span className="flex items-baseline gap-1.5">
      <span className="text-dim tracking-[0.32em]">{k}</span>
      <span className={`font-display tracking-[0.16em] text-[12px] ${c}`}>{v}</span>
    </span>
  );
}
