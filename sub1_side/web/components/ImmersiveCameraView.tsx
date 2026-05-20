"use client";
import { getApiBase, ROBOT_ID } from "@/lib/api";

/**
 * Immersive Camera View — front/rear MJPEG 를 robot 주변 어안렌즈 곡면처럼
 * 렌더링. CSS 3D transform + radial mask + perspective.
 *
 * 디자인 영감: Spot SDK Foxglove panel (image #1) — 검은 배경 위 robot 중심,
 * 카메라 뷰가 fisheye 처럼 wrapping.
 *
 * 좌: rear 카메라 (왼쪽으로 휘어짐, perspective)
 * 중앙: Go2 SVG silhouette (top-down view, yellow glow)
 * 우: inspect 카메라 (오른쪽으로 휘어짐)
 *
 * 각 카메라 frame 은 큰 border-radius + 3D rotateY + radial-gradient mask
 * 로 fisheye 의 곡률 시뮬레이션.
 */
export default function ImmersiveCameraView() {
  const apiBase = typeof window !== "undefined" ? getApiBase() : "";
  return (
    <div className="panel h-full flex flex-col overflow-hidden">
      <div className="panel-hd">
        <span>IMMERSIVE VIEW · {ROBOT_ID.toUpperCase()}</span>
        <span className="text-[10px] text-dim">REAR ◀ GO2 ▶ INSPECT</span>
      </div>
      <div className="relative flex-1 min-h-0 bg-black overflow-hidden"
           style={{ perspective: "1200px" }}>
        {/* 좌측 — REAR 카메라 (오른쪽으로 회전) */}
        <div
          className="absolute left-0 top-1/2 -translate-y-1/2
                     w-[42%] aspect-video"
          style={{
            transform: "rotateY(35deg) translateZ(-40px) translateX(-10%)",
            transformOrigin: "right center",
            filter: "drop-shadow(0 8px 24px rgba(0,255,0,0.18))",
          }}>
          <div
            className="w-full h-full rounded-[40%/30%] overflow-hidden
                       border border-phos/40"
            style={{
              maskImage: "radial-gradient(ellipse at center, black 60%, transparent 100%)",
              WebkitMaskImage: "radial-gradient(ellipse at center, black 60%, transparent 100%)",
            }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`${apiBase}/c2/video/mjpeg?camera=rear`}
              alt="rear"
              className="w-full h-full object-cover"
            />
          </div>
          <div className="absolute top-1 left-1 px-1.5 py-0.5 text-[10px]
                          bg-black/70 text-phos font-mono tracking-wider">
            REAR
          </div>
        </div>

        {/* 우측 — INSPECT 카메라 (왼쪽으로 회전) */}
        <div
          className="absolute right-0 top-1/2 -translate-y-1/2
                     w-[42%] aspect-video"
          style={{
            transform: "rotateY(-35deg) translateZ(-40px) translateX(10%)",
            transformOrigin: "left center",
            filter: "drop-shadow(0 8px 24px rgba(0,255,0,0.18))",
          }}>
          <div
            className="w-full h-full rounded-[40%/30%] overflow-hidden
                       border border-phos/40"
            style={{
              maskImage: "radial-gradient(ellipse at center, black 60%, transparent 100%)",
              WebkitMaskImage: "radial-gradient(ellipse at center, black 60%, transparent 100%)",
            }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`${apiBase}/c2/video/mjpeg?camera=inspect`}
              alt="inspect"
              className="w-full h-full object-cover"
            />
          </div>
          <div className="absolute top-1 right-1 px-1.5 py-0.5 text-[10px]
                          bg-black/70 text-phos font-mono tracking-wider">
            INSPECT
          </div>
        </div>

        {/* 중앙 — Go2 silhouette + 회전 ring */}
        <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2
                        w-[24%] aspect-square flex items-center justify-center">
          {/* outer ring (천천히 회전) */}
          <div className="absolute inset-0 rounded-full border border-phos/30"
               style={{
                 animation: "spin 18s linear infinite",
                 boxShadow: "0 0 40px rgba(0,255,128,0.18) inset",
               }} />
          {/* inner ring (반대 회전) */}
          <div className="absolute inset-[12%] rounded-full border border-phos/50
                          border-dashed"
               style={{ animation: "spin 9s linear infinite reverse" }} />
          {/* Go2 top-down SVG */}
          <svg viewBox="0 0 100 100" className="relative w-[55%] h-[55%]"
               style={{ filter: "drop-shadow(0 0 12px rgba(255,221,0,0.6))" }}>
            {/* 본체 */}
            <rect x="30" y="22" width="40" height="56" rx="8"
                  fill="#ffcc00" stroke="#806600" strokeWidth="1.2"/>
            {/* 머리 */}
            <rect x="38" y="12" width="24" height="14" rx="4"
                  fill="#ffdd33" stroke="#806600" strokeWidth="1"/>
            {/* 다리 4개 */}
            <circle cx="28" cy="32" r="4" fill="#ffaa00" />
            <circle cx="72" cy="32" r="4" fill="#ffaa00" />
            <circle cx="28" cy="68" r="4" fill="#ffaa00" />
            <circle cx="72" cy="68" r="4" fill="#ffaa00" />
            {/* 전방 표시 화살표 */}
            <polygon points="50,4 46,12 54,12" fill="#00ff88" />
          </svg>
          <div className="absolute bottom-[-22px] text-[10px] text-phos
                          tracking-[0.25em] font-mono">
            GO2 · ACTIVE
          </div>
        </div>

        {/* scanline 효과 */}
        <div className="absolute inset-0 pointer-events-none opacity-25"
             style={{
               background: "repeating-linear-gradient(0deg, rgba(0,255,128,0) 0px, rgba(0,255,128,0) 2px, rgba(0,255,128,0.04) 3px, rgba(0,255,128,0) 4px)",
             }} />
      </div>
    </div>
  );
}
