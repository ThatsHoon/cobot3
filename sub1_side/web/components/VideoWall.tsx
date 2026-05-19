"use client";
import { getApiBase } from "@/lib/api";

/** 전방·후방 MJPEG 듀얼 카메라 패널 */
export default function VideoWall({
  detCount,
  contact,
}: {
  detCount: number;
  contact: boolean;
}) {
  const api = getApiBase();

  return (
    <div className="panel h-full flex flex-col">
      <div className="panel-hd">
        <span>FEED · FRONT / REAR</span>
        <span className="flex items-center gap-3">
          <span className="text-phos">MJPEG</span>
          <span className="text-alert">DET {detCount}</span>
        </span>
      </div>
      {/* 상단: 전방 카메라 (HUD 레티클 포함) */}
      <div className="relative flex-1 bg-black overflow-hidden">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={`${api}/c2/video/mjpeg?camera=front`}
          alt="front"
          className="absolute inset-0 w-full h-full object-contain"
        />
        <div className="absolute inset-0 pointer-events-none">
          <div
            className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-24 h-24 border"
            style={{
              borderColor: contact
                ? "rgba(255,77,77,0.85)"
                : "rgba(70,244,168,0.4)",
            }}
          />
          <div className="absolute left-1/2 top-1/2 w-px h-6 -translate-x-1/2 -translate-y-1/2 bg-phos/60" />
          <div className="absolute left-1/2 top-1/2 h-px w-6 -translate-x-1/2 -translate-y-1/2 bg-phos/60" />
          {contact && (
            <div className="absolute top-3 left-1/2 -translate-x-1/2 text-alert font-display tracking-[0.3em] text-sm animate-pulse">
              ▲ TARGET ACQUIRED
            </div>
          )}
          <div className="absolute bottom-2 left-3 text-[10px] text-phos/70 tracking-widest">
            FRONT · 5 FPS · {api.replace(/^https?:\/\//, "")}
          </div>
        </div>
      </div>
      {/* 하단: 후방 카메라 */}
      <div className="relative h-1/3 bg-black overflow-hidden border-t border-dim/30">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={`${api}/c2/video/mjpeg?camera=rear`}
          alt="rear"
          className="absolute inset-0 w-full h-full object-contain"
        />
        <div className="absolute bottom-2 left-3 text-[10px] text-phos/50 tracking-widest pointer-events-none">
          REAR · 5 FPS
        </div>
      </div>
    </div>
  );
}
