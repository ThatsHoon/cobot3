"use client";
import { getApiBase } from "@/lib/api";

/**
 * 전방 + 검사 카메라 MJPEG 2-panel (P4 jsy 포팅).
 * server 의 `/c2/video/mjpeg?camera={front|rear|inspect}` 활용.
 */
const CAMS: { id: "front" | "rear" | "inspect"; label: string }[] = [
  { id: "front",   label: "FRONT" },
  { id: "inspect", label: "INSPECT" },
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
