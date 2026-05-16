"use client";
import { useEffect, useRef, useState } from "react";
import { API_BASE } from "@/lib/api";

/** WebRTC(aiortc) 우선, 실패 시 MJPEG 폴백 — 설계 D7/§9.1 */
export default function VideoWall({
  detCount,
  contact,
}: {
  detCount: number;
  contact: boolean;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [mode, setMode] = useState<"connecting" | "webrtc" | "mjpeg">(
    "connecting"
  );

  useEffect(() => {
    let pc: RTCPeerConnection | null = null;
    let cancelled = false;

    (async () => {
      try {
        console.info("[C2/webrtc] negotiating →", `${API_BASE}/c2/webrtc/offer`);
        pc = new RTCPeerConnection();
        pc.addTransceiver("video", { direction: "recvonly" });
        pc.oniceconnectionstatechange = () =>
          console.debug("[C2/webrtc] ICE:", pc?.iceConnectionState);
        pc.onconnectionstatechange = () =>
          console.info("[C2/webrtc] state:", pc?.connectionState);
        pc.ontrack = (e) => {
          console.info("[C2/webrtc] ✓ track 수신 — 영상 스트림 연결됨");
          if (videoRef.current) videoRef.current.srcObject = e.streams[0];
        };
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);
        const r = await fetch(`${API_BASE}/c2/webrtc/offer`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            sdp: pc.localDescription!.sdp,
            type: pc.localDescription!.type,
          }),
        });
        if (!r.ok) throw new Error(`offer ${r.status}`);
        const ans = await r.json();
        await pc.setRemoteDescription(ans);
        if (!cancelled) {
          setMode("webrtc");
          console.info("[C2/webrtc] ✓ SDP 교환 완료 (영상 트랙 대기)");
        }
      } catch (err) {
        console.warn("[C2/webrtc] 실패 → MJPEG 폴백:", err);
        if (!cancelled) setMode("mjpeg");
      }
    })();

    return () => {
      cancelled = true;
      pc?.close();
    };
  }, []);

  return (
    <div className="panel h-full flex flex-col">
      <div className="panel-hd">
        <span>FEED · REALSENSE RGB-D</span>
        <span className="flex items-center gap-3">
          <span className="text-phos">{mode.toUpperCase()}</span>
          <span className="text-alert">DET {detCount}</span>
        </span>
      </div>
      <div className="relative flex-1 bg-black overflow-hidden">
        {mode === "mjpeg" ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={`${API_BASE}/c2/video/mjpeg`}
            alt="feed"
            className="absolute inset-0 w-full h-full object-contain"
          />
        ) : (
          <video
            ref={videoRef}
            autoPlay
            muted
            playsInline
            className="absolute inset-0 w-full h-full object-contain"
          />
        )}
        {/* HUD 조준 레티클 — 접촉 시 적색 + 경고 */}
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
            5 FPS · DEGRADED · {API_BASE.replace(/^https?:\/\//, "")}
          </div>
        </div>
        {mode === "connecting" && (
          <div className="absolute inset-0 grid place-items-center text-dim text-xs tracking-[0.3em]">
            ESTABLISHING LINK…
          </div>
        )}
      </div>
    </div>
  );
}
