"use client";
import dynamic from "next/dynamic";
import { ROBOT_ID } from "@/lib/api";

/**
 * Immersive Camera View — Go2 URDF + rear/inspect sphere wrap, 북향 고정.
 * SSR 불가 (window 의존) → next/dynamic + ssr:false.
 */
const Inner = dynamic(() => import("./ImmersiveCameraViewClient"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full grid place-items-center text-dim text-xs tracking-[0.3em]">
      LOADING 3D · URDF…
    </div>
  ),
});

export default function ImmersiveCameraView({ yaw = 0 }: { yaw?: number }) {
  return (
    <div className="panel h-full flex flex-col overflow-hidden">
      <div className="panel-hd">
        <span>IMMERSIVE · {ROBOT_ID.toUpperCase()}</span>
        <span className="text-[10px] text-dim">URDF · 2-CAM · NORTH-UP</span>
      </div>
      <div className="relative flex-1 min-h-0 bg-black">
        <Inner yaw={yaw} />
      </div>
    </div>
  );
}
