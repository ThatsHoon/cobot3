"use client";
import { getApiBase } from "@/lib/api";

/**
 * 3-카메라 MJPEG grid (REAR / INSPECT / OVERHEAD) — debug 페이지 전용.
 * inspect 채널에 YOLO bbox overlay (ros_bridge 가 frame 위에 그려서 전송).
 */
const CAMS: { id: "rear" | "inspect" | "overhead"; label: string }[] = [
  { id: "inspect",  label: "INSPECT (YOLO)" },
  { id: "rear",     label: "REAR" },
  { id: "overhead", label: "OVERHEAD (NORTH-UP)" },
];

export default function TripleCameraView() {
  return (
    <div className="panel h-full flex flex-col">
      <div className="panel-hd">
        <span>CAMERAS · 3-VIEW</span>
        <span className="text-[10px] text-dim">MJPEG · 5fps</span>
      </div>
      <div className="grid grid-cols-1 gap-1 p-1 flex-1 min-h-0">
        {CAMS.map(({ id, label }) => (
          <div key={id} className="relative bg-black min-h-0 flex-1">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`${getApiBase()}/c2/video/mjpeg?camera=${id}`}
              alt={label}
              className="w-full h-full object-contain"
            />
            <div className="absolute top-1 left-1 px-1.5 py-0.5 text-[10px]
                            bg-black/70 text-phos font-mono tracking-wider">
              {label}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
