"use client";
import dynamic from "next/dynamic";
import { ROBOT_ID } from "@/lib/api";

/**
 * Immersive Camera View — Go2 (Spot SDK fisheye sphere wrapping 패턴 차용).
 * Three.js 컴포넌트는 SSR 불가 (window 의존) → next/dynamic + ssr:false.
 */
const Inner = dynamic(() => import("./ImmersiveCameraViewClient"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full grid place-items-center text-dim text-xs tracking-[0.3em]">
      LOADING 3D…
    </div>
  ),
});

export default function ImmersiveCameraView() {
  return (
    <div className="panel h-full flex flex-col overflow-hidden">
      <div className="panel-hd">
        <span>IMMERSIVE · {ROBOT_ID.toUpperCase()}</span>
        <span className="text-[10px] text-dim">SPHERE WRAP · 3-CAM</span>
      </div>
      <div className="relative flex-1 min-h-0 bg-black">
        <Inner />
        <div className="absolute top-2 left-2 text-[10px] text-phos font-mono tracking-wider
                        bg-black/60 px-2 py-0.5">
          GO2 · IMMERSIVE
        </div>
      </div>
    </div>
  );
}
