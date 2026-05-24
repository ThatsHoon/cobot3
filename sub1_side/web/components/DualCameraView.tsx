"use client";
import { useEffect, useRef, useState } from "react";
import { getApiBase, AlertPayload } from "@/lib/api";
import { useWeaponSafety } from "./WeaponSafetyContext";

const INSPECT_W = 1280;
const INSPECT_H = 720;

type CameraId = "inspect" | "rear" | "tp_a" | "tp_b" | "tp_c" | "tp_d" | "tp_grid";

// 2026-05-24: TP_A~D 는 서버 mosaic(tp_grid)로 단일 MJPEG 사용. 브라우저 HTTP/1.1
// origin당 6 connection 제한 회피 (inspect+rear+overhead+tp_grid = 4 streams).
// 백엔드 _build_tp_grid_frame() 의 셀 순서와 동기 (TL, TR, BL, BR).
const TP_CAMERAS: { id: "tp_a" | "tp_b" | "tp_c" | "tp_d"; label: string; sub: string }[] = [
  { id: "tp_a", label: "TP-A", sub: "01 · WATCH-ALPHA" },
  { id: "tp_b", label: "TP-B", sub: "02 · WATCH-BRAVO" },
  { id: "tp_c", label: "TP-C", sub: "03 · WATCH-CHARLIE" },
  { id: "tp_d", label: "TP-D", sub: "04 · WATCH-DELTA" },
];

export default function DualCameraView({
  liveAlerts,
  tpDetections,
}: {
  liveAlerts?: { ts: string; data: AlertPayload }[];
  tpDetections?: { ts: string; camera: string }[];
}) {
  const now = Date.now();
  const recent = (liveAlerts || []).filter(e =>
    now - new Date(e.ts).getTime() < 5000);

  // TP 카메라별 최근 5초 감지 수
  const tpCounts: Record<string, number> = {};
  (tpDetections || []).filter(d => now - new Date(d.ts).getTime() < 5000)
    .forEach(d => { tpCounts[d.camera] = (tpCounts[d.camera] ?? 0) + 1; });

  return (
    <div className="panel h-full flex flex-col">
      <div className="panel-hd">
        <span>DUAL CAMERA · REALSENSE</span>
        <span className="flex items-center gap-2">
          <span className="panel-idx tabular">
            MJPEG · 5 FPS · BBOX {String(recent.length).padStart(2, "0")}
          </span>
        </span>
      </div>
      {/* --- 기존 inspect + rear --- */}
      <div className="grid grid-cols-2 gap-1.5 p-1.5 pb-0">
        <InspectCamera alerts={recent} />
        <RearCamera />
      </div>
      {/* --- 전술 고정 관측소 카메라 TP_A~D --- */}
      <div className="flex items-center gap-2 px-1.5 pt-1.5 pb-0">
        <span className="text-[8px] font-display tracking-[0.22em] text-dim">
          TACTICAL CAMS · FIXED OBS
        </span>
        <span className="flex-1 h-px bg-line" />
      </div>
      <TacticalGrid tpCounts={tpCounts} />
    </div>
  );
}

/** TP_A~D 4채널을 단일 MJPEG(tp_grid) + 가로 1×4 셀 오버레이로 렌더.
 *  서버 mosaic 1280×180 strip 사용 → MJPEG 연결 1개로 4채널 표시
 *  (browser HTTP/1.1 connection limit 회피). */
function TacticalGrid({ tpCounts }: { tpCounts: Record<string, number> }) {
  const src = useMjpegSrc("tp_grid");
  return (
    <div className="p-1.5 flex-1 min-h-0">
      {/* aspect 1280:180 ≈ 64:9 (4셀 가로 strip) */}
      <div className="relative bg-black w-full codecorner"
           style={{ aspectRatio: "64 / 9" }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {src && <img src={src} alt="TP_GRID"
                     className="absolute inset-0 w-full h-full object-cover" />}
        {/* 4 셀 오버레이 (가로 grid-cols-4) */}
        <div className="absolute inset-0 grid grid-cols-4 pointer-events-none">
          {TP_CAMERAS.map(({ id, label, sub }) => (
            <div key={id} className="relative">
              <CamBadge label={label} side="left" tone="amber" sub={sub} />
              {(tpCounts[id] ?? 0) > 0 && (
                <CamBadge label={`DET ${String(tpCounts[id]).padStart(2, "0")}`}
                          side="right" tone="alert" pulse />
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** 마운트 전엔 src 비워서 SSR/CSR hydration mismatch 회피. */
function useMjpegSrc(camera: CameraId) {
  const [src, setSrc] = useState<string>("");
  useEffect(() => {
    setSrc(`${getApiBase()}/c2/video/mjpeg?camera=${camera}`);
  }, [camera]);
  return src;
}

function RearCamera() {
  const src = useMjpegSrc("rear");
  return (
    <div className="relative bg-black aspect-video codecorner">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {src && <img src={src} alt="REAR"
                   className="w-full h-full object-contain" />}
      <CamBadge label="REAR" side="left" tone="phos" sub="06 · REAR-WIDE" />
      <Reticle />
    </div>
  );
}

function InspectCamera({ alerts }: {
  alerts: { ts: string; data: AlertPayload }[];
}) {
  const { requestFire, safetyOff } = useWeaponSafety();
  const containerRef = useRef<HTMLDivElement>(null);
  const src = useMjpegSrc("inspect");

  const toViewBox = (x: number, y: number, w: number, h: number) => ({
    left: `${(x / INSPECT_W) * 100}%`,
    top: `${(y / INSPECT_H) * 100}%`,
    width: `${(w / INSPECT_W) * 100}%`,
    height: `${(h / INSPECT_H) * 100}%`,
  });

  const onContainerClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const u = (e.clientX - rect.left) / rect.width;
    const v = (e.clientY - rect.top) / rect.height;
    const px = u * INSPECT_W;
    const py = v * INSPECT_H;
    requestFire({
      look_at_pixel: [px, py],
      target_label: `pixel(${px.toFixed(0)},${py.toFixed(0)})`,
    });
  };

  const onBboxClick = (e: React.MouseEvent, alert: AlertPayload) => {
    e.stopPropagation();
    const bbox = parseBbox(alert.bbox_xyxy);
    if (!bbox) return;
    const cx = (bbox[0] + bbox[2]) / 2;
    const cy = (bbox[1] + bbox[3]) / 2;
    requestFire({
      look_at_pixel: [cx, cy],
      target_label: `${alert.event} (bbox center ${cx.toFixed(0)},${cy.toFixed(0)})`,
    });
  };

  return (
    <div ref={containerRef}
         onClick={onContainerClick}
         className={`relative bg-black aspect-video codecorner
                     ${safetyOff ? "cursor-crosshair" : "cursor-not-allowed"}`}
         title={safetyOff ? "클릭하여 격발 (확인 후)"
                          : "🔒 SAFETY ON — 우측 WEAPON 패널에서 해제 필요"}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {src && <img src={src} alt="INSPECT"
                   className="w-full h-full object-contain pointer-events-none" />}

      {/* bbox overlay */}
      {alerts.map((a, i) => {
        const bbox = parseBbox(a.data.bbox_xyxy);
        if (!bbox) return null;
        const [x1, y1, x2, y2] = bbox;
        const style = toViewBox(x1, y1, x2 - x1, y2 - y1);
        return (
          <div key={i}
               onClick={e => onBboxClick(e, a.data)}
               className={`absolute cursor-pointer pointer-events-auto`}
               style={{
                 ...style,
                 border: `1.5px solid ${safetyOff ? "var(--alert)" : "rgba(255,77,77,0.45)"}`,
                 boxShadow: safetyOff
                   ? "0 0 0 1px rgba(0,0,0,0.5), inset 0 0 12px rgba(255,77,77,0.25)"
                   : undefined,
               }}>
            {/* corner brackets */}
            <span className="absolute -top-px -left-px w-2 h-2 border-t border-l border-alert" />
            <span className="absolute -top-px -right-px w-2 h-2 border-t border-r border-alert" />
            <span className="absolute -bottom-px -left-px w-2 h-2 border-b border-l border-alert" />
            <span className="absolute -bottom-px -right-px w-2 h-2 border-b border-r border-alert" />
            <div className="absolute -top-[18px] left-0 text-[9px] font-display
                            tracking-[0.16em] bg-alert text-base px-1.5">
              {a.data.event} · {a.data.confidence.toFixed(2)}
            </div>
          </div>
        );
      })}

      <CamBadge label="INSPECT" side="left" tone="phos" sub="05 · TURRET-CAM" />
      <CamBadge
        label={safetyOff ? "ARMED" : "SAFE"}
        side="right"
        tone={safetyOff ? "alert" : "phos"}
        sub={safetyOff ? "FCS · OPEN" : "FCS · CLOSED"}
        pulse={safetyOff}
      />

      <Reticle armed={safetyOff} />
    </div>
  );
}

function CamBadge({
  label, side, tone, sub, pulse,
}: {
  label: string; side: "left" | "right";
  tone: "phos" | "alert" | "amber";
  sub?: string; pulse?: boolean;
}) {
  const c = tone === "phos" ? "text-phos border-phos-dim"
    : tone === "alert" ? "text-alert border-alert-dim"
    : "text-amber border-amber-dim";
  return (
    <div className={`absolute top-1.5 ${side === "left" ? "left-1.5" : "right-1.5"}
                     bg-black/75 backdrop-blur-sm border ${c}
                     px-2 py-0.5 ${pulse ? "animate-pulse" : ""}`}>
      <div className="font-display tracking-[0.22em] text-[10px] leading-tight">{label}</div>
      {sub && <div className="font-mono text-[8px] tracking-[0.18em] text-dim leading-tight">{sub}</div>}
    </div>
  );
}

function Reticle({ armed }: { armed?: boolean }) {
  const c = armed ? "var(--alert)" : "rgba(70, 244, 168, 0.55)";
  return (
    <svg className="absolute inset-0 w-full h-full pointer-events-none"
         viewBox="0 0 100 100" preserveAspectRatio="none">
      {/* main crosshair */}
      <line x1="50" y1="44" x2="50" y2="56" stroke={c}
            strokeWidth="0.18" vectorEffect="non-scaling-stroke" />
      <line x1="44" y1="50" x2="56" y2="50" stroke={c}
            strokeWidth="0.18" vectorEffect="non-scaling-stroke" />
      {/* outer ticks */}
      <line x1="50" y1="20" x2="50" y2="24" stroke={c}
            strokeWidth="0.12" vectorEffect="non-scaling-stroke" />
      <line x1="50" y1="76" x2="50" y2="80" stroke={c}
            strokeWidth="0.12" vectorEffect="non-scaling-stroke" />
      <line x1="20" y1="50" x2="24" y2="50" stroke={c}
            strokeWidth="0.12" vectorEffect="non-scaling-stroke" />
      <line x1="76" y1="50" x2="80" y2="50" stroke={c}
            strokeWidth="0.12" vectorEffect="non-scaling-stroke" />
      {/* center dot */}
      <circle cx="50" cy="50" r="0.4" fill={c} />
    </svg>
  );
}

function parseBbox(b: AlertPayload["bbox_xyxy"] | undefined): [number, number, number, number] | null {
  if (!b) return null;
  if (typeof b === "string") {
    try { const a = JSON.parse(b); return a.length >= 4 ? a : null; } catch { return null; }
  }
  return b.length >= 4 ? [b[0], b[1], b[2], b[3]] : null;
}
