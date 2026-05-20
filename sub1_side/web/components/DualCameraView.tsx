"use client";
import { getApiBase } from "@/lib/api";

/**
 * 검사(짐벌) + 후방(real) 카메라 MJPEG 2-panel.
 * 2026-05-20: front 제거 → inspect+rear. YOLO bbox 는 inspect 채널에서.
 */
const CAMS: { id: "rear" | "inspect"; label: string }[] = [
  { id: "inspect", label: "INSPECT" },
  { id: "rear",    label: "REAR" },
];

export default function DualCameraView() {
  return (
    <div className="panel">
      <div className="panel-hd">
        <span>DUAL CAMERA</span>
        <span className="text-[11px] text-dim">MJPEG · 5fps</span>
      </div>
      <div className="grid grid-cols-2 gap-1.5 p-1.5">
        {CAMS.map(({ id, label }) => (
          <div key={id} className="relative bg-black aspect-video">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`${getApiBase()}/c2/video/mjpeg?camera=${id}`}
              alt={label}
              className="w-full h-full object-contain"
            />
            <div className="absolute top-1 left-1 px-1.5 py-0.5 text-[10px]
                            bg-black/70 text-phos font-mono">
              {label}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
