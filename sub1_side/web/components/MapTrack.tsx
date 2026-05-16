"use client";
import { useEffect, useRef, useState } from "react";
import { postJSON, ROBOT_ID } from "@/lib/api";

type Pt = { x: number; y: number };

/**
 * GPS/ODOM 궤적 + 경로 표시, 클릭 → goto 명령 (설계 §10.3).
 * sim 좌표 추정: ODOM xy 우선, 없으면 GPS lat/lon.
 * EXTENT(±m) 안에서 캔버스에 매핑. 클릭 좌표를 sim xy 로 역산해 POST.
 */
const EXTENT = 60; // ±60 m 표시 범위

export default function MapTrack({
  track,
  cur,
}: {
  track: Pt[];
  cur: Pt | null;
}) {
  const cv = useRef<HTMLCanvasElement>(null);
  const [pending, setPending] = useState<Pt | null>(null);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    const c = cv.current;
    if (!c) return;
    const ctx = c.getContext("2d")!;
    const W = (c.width = c.clientWidth);
    const H = (c.height = c.clientHeight);
    const toPx = (p: Pt) => ({
      px: W / 2 + (p.x / EXTENT) * (W / 2),
      py: H / 2 - (p.y / EXTENT) * (H / 2),
    });

    ctx.clearRect(0, 0, W, H);
    // 링 그리드
    ctx.strokeStyle = "rgba(70,244,168,0.18)";
    for (let r = 1; r <= 3; r++) {
      ctx.beginPath();
      ctx.arc(W / 2, H / 2, (Math.min(W, H) / 2) * (r / 3), 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.beginPath();
    ctx.moveTo(W / 2, 0);
    ctx.lineTo(W / 2, H);
    ctx.moveTo(0, H / 2);
    ctx.lineTo(W, H / 2);
    ctx.stroke();

    // 궤적
    ctx.strokeStyle = "rgba(70,244,168,0.55)";
    ctx.beginPath();
    track.forEach((p, i) => {
      const { px, py } = toPx(p);
      i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
    });
    ctx.stroke();

    // 현재 위치
    if (cur) {
      const { px, py } = toPx(cur);
      ctx.fillStyle = "#46f4a8";
      ctx.beginPath();
      ctx.arc(px, py, 5, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "rgba(70,244,168,0.4)";
      ctx.beginPath();
      ctx.arc(px, py, 11, 0, Math.PI * 2);
      ctx.stroke();
    }
    // 보류 목표
    if (pending) {
      const { px, py } = toPx(pending);
      ctx.strokeStyle = "#f4b740";
      ctx.beginPath();
      ctx.moveTo(px - 7, py);
      ctx.lineTo(px + 7, py);
      ctx.moveTo(px, py - 7);
      ctx.lineTo(px, py + 7);
      ctx.stroke();
    }
  }, [track, cur, pending]);

  const onClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const c = cv.current!;
    const rect = c.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;
    const x = ((px - rect.width / 2) / (rect.width / 2)) * EXTENT;
    const y = (-(py - rect.height / 2) / (rect.height / 2)) * EXTENT;
    setPending({ x, y });
    setMsg(`목표 지정: ${x.toFixed(1)}, ${y.toFixed(1)} — 더블클릭으로 전송`);
  };

  const onDouble = async () => {
    if (!pending) return;
    try {
      await postJSON(`/robots/${ROBOT_ID}/goto`, pending);
      setMsg(`GOTO 전송됨 → ${pending.x.toFixed(1)}, ${pending.y.toFixed(1)}`);
      setPending(null);
    } catch (e: any) {
      setMsg(`전송 실패: ${e.message}`);
    }
  };

  return (
    <div className="panel h-full flex flex-col">
      <div className="panel-hd">
        <span>TACTICAL MAP · {ROBOT_ID.toUpperCase()}</span>
        <span className="text-dim">±{EXTENT} m</span>
      </div>
      <div className="relative flex-1">
        <canvas
          ref={cv}
          onClick={onClick}
          onDoubleClick={onDouble}
          className="absolute inset-0 w-full h-full cursor-crosshair"
        />
      </div>
      <div className="px-3 py-1.5 text-[11px] text-amber border-t border-line min-h-[26px]">
        {msg || "맵 클릭=목표지정 · 더블클릭=GOTO 전송"}
      </div>
    </div>
  );
}
