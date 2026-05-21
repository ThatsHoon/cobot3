"use client";
import { useRef } from "react";
import { getApiBase, AlertPayload } from "@/lib/api";
import { useWeaponSafety } from "./WeaponSafetyContext";

/** 검사(짐벌) + 후방(real) 카메라 MJPEG 2-panel + HITL 사격 클릭.
 *
 *  inspect 패널:
 *    - 최근 YOLO alert 의 bbox 를 빨강 outline 으로 표시
 *    - bbox 클릭 → bbox 중심 좌표로 격발 요청 (안전장치 검사)
 *    - 빈 영역 클릭 → 클릭 좌표로 격발 요청
 *
 *  안전장치 OFF 면 useWeaponSafety.requestFire() → 확인 모달 → 격발.
 *  안전장치 ON 이면 toast "안전장치 해제 요망".
 *
 *  bbox 좌표계: AlertPayload.bbox_xyxy = inspect 카메라 이미지 픽셀 (1280×720
 *  기본 가정 — config 의 CamInspect 해상도). 클릭 좌표 변환 동일.
 */
const INSPECT_W = 1280;
const INSPECT_H = 720;

export default function DualCameraView({
  liveAlerts,
}: {
  liveAlerts?: { ts: string; data: AlertPayload }[];
}) {
  // 최근 5초 이내 alert 들 (overlay 표시)
  const now = Date.now();
  const recent = (liveAlerts || []).filter(e =>
    now - new Date(e.ts).getTime() < 5000);

  return (
    <div className="panel">
      <div className="panel-hd">
        <span>DUAL CAMERA</span>
        <span className="text-[11px] text-dim">
          MJPEG · 5fps · INSPECT 클릭=격발 ({recent.length} bbox)
        </span>
      </div>
      <div className="grid grid-cols-2 gap-1.5 p-1.5">
        <InspectCamera alerts={recent} />
        <RearCamera />
      </div>
    </div>
  );
}

function RearCamera() {
  return (
    <div className="relative bg-black aspect-video">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={`${getApiBase()}/c2/video/mjpeg?camera=rear`}
           alt="REAR" className="w-full h-full object-contain" />
      <div className="absolute top-1 left-1 px-1.5 py-0.5 text-[10px]
                      bg-black/70 text-phos font-mono">REAR</div>
    </div>
  );
}

function InspectCamera({ alerts }: {
  alerts: { ts: string; data: AlertPayload }[];
}) {
  const { requestFire, safetyOff } = useWeaponSafety();
  const containerRef = useRef<HTMLDivElement>(null);

  // 픽셀 좌표 (1280×720 기준) → 화면 좌표(%) 로 표시
  const toViewBox = (x: number, y: number, w: number, h: number) => ({
    left: `${(x / INSPECT_W) * 100}%`,
    top: `${(y / INSPECT_H) * 100}%`,
    width: `${(w / INSPECT_W) * 100}%`,
    height: `${(h / INSPECT_H) * 100}%`,
  });

  const onContainerClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!containerRef.current) return;
    // 이미 bbox 클릭 핸들러가 stopPropagation 하면 여기 안 옴.
    const rect = containerRef.current.getBoundingClientRect();
    const u = (e.clientX - rect.left) / rect.width;   // 0..1
    const v = (e.clientY - rect.top) / rect.height;   // 0..1
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
         className={`relative bg-black aspect-video
                     ${safetyOff ? "cursor-crosshair" : "cursor-not-allowed"}`}
         title={safetyOff ? "클릭하여 격발 (확인 후)"
                          : "🔒 SAFETY ON — 우측 WEAPON 패널에서 해제 필요"}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={`${getApiBase()}/c2/video/mjpeg?camera=inspect`}
           alt="INSPECT" className="w-full h-full object-contain
                                    pointer-events-none" />
      {/* bbox overlay */}
      {alerts.map((a, i) => {
        const bbox = parseBbox(a.data.bbox_xyxy);
        if (!bbox) return null;
        const [x1, y1, x2, y2] = bbox;
        const style = toViewBox(x1, y1, x2 - x1, y2 - y1);
        return (
          <div key={i}
               onClick={e => onBboxClick(e, a.data)}
               className={`absolute border-2 ${safetyOff
                 ? "border-rose-500 hover:border-yellow-300 hover:bg-rose-500/20"
                 : "border-rose-500/40"} cursor-pointer pointer-events-auto`}
               style={style}>
            <div className="absolute -top-4 left-0 text-[9px] font-mono
                            bg-rose-600 text-white px-1">
              {a.data.event} {a.data.confidence.toFixed(2)}
            </div>
          </div>
        );
      })}
      {/* 라벨 + 안전장치 인디케이터 */}
      <div className="absolute top-1 left-1 px-1.5 py-0.5 text-[10px]
                      bg-black/70 text-phos font-mono">INSPECT</div>
      <div className={`absolute top-1 right-1 px-1.5 py-0.5 text-[10px]
                       font-mono ${safetyOff
                         ? "bg-rose-600 text-white animate-pulse"
                         : "bg-emerald-700/80 text-white"}`}>
        {safetyOff ? "🔓 ARMED" : "🔒 SAFE"}
      </div>
      {/* 십자선 (참고용, 사격 시 inspect 가 클릭 위치로 회전) */}
      <svg className="absolute inset-0 w-full h-full pointer-events-none"
           viewBox="0 0 100 100" preserveAspectRatio="none">
        <line x1="50" y1="46" x2="50" y2="54" stroke="rgba(255,80,80,0.5)"
              strokeWidth="0.2" vectorEffect="non-scaling-stroke" />
        <line x1="46" y1="50" x2="54" y2="50" stroke="rgba(255,80,80,0.5)"
              strokeWidth="0.2" vectorEffect="non-scaling-stroke" />
      </svg>
    </div>
  );
}

function parseBbox(b: AlertPayload["bbox_xyxy"] | undefined): [number, number, number, number] | null {
  if (!b) return null;
  if (typeof b === "string") {
    try { const a = JSON.parse(b); return a.length >= 4 ? a : null; } catch { return null; }
  }
  return b.length >= 4 ? [b[0], b[1], b[2], b[3]] : null;
}
