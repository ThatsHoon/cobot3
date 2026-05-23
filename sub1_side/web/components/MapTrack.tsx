"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { getApiBase, postJSON, ROBOT_ID, LandmarksPayload, IntruderState,
         PatrolStatePayload, TacticalDetectionPoint } from "@/lib/api";

type Pt = { x: number; y: number; z?: number; yaw?: number };

/**
 * GPS/ODOM 궤적 + 경로 표시, 클릭 → goto 명령 (설계 §10.3).
 * sim 좌표 추정: ODOM xy 우선, 없으면 GPS lat/lon.
 * EXTENT(±m) 안에서 캔버스에 매핑. 클릭 좌표를 sim xy 로 역산해 POST.
 *
 * DMZ Sentry M7: landmarks(cube/cone/fence) · intruders · patrol state · alert
 * overlay 통합. cube 좌표 기준 자동 센터링 (gp_scene world ≈ (-714,952)).
 */
const DEFAULT_EXTENT = 60; // ±60 m 표시 범위 (landmarks 없으면)

export default function MapTrack({
  track,
  cur,
  landmarks,
  intruders,
  detections,
  patrolState,
  alertActive,
}: {
  track: Pt[];
  cur: Pt | null;
  landmarks?: LandmarksPayload | null;
  intruders?: IntruderState[];
  detections?: TacticalDetectionPoint[];
  patrolState?: PatrolStatePayload | null;
  alertActive?: boolean;
}) {
  const cv = useRef<HTMLCanvasElement>(null);
  const [pending, setPending] = useState<Pt | null>(null);
  const [msg, setMsg] = useState("");

  const toLocalFromHome = (p: Pt, home?: Pt | null): Pt => {
    if (!home) return p;
    return {
      x: p.x - home.x,
      y: p.y - home.y,
      z: p.z != null && home.z != null ? p.z - home.z : p.z,
      yaw: p.yaw,
    };
  };

  // landmarks 기준 자동 센터링·EXTENT.
  // camera_publisher.py 가 쓰는 /tmp/cobot3_landmarks.json 은 Isaac world
  // 좌표(home/goal/tactical_points)를 저장하지만, 로봇 odom/탐지점은 home
  // 기준 local 좌표로 들어온다. 그래서 view 도 local 좌표계로 잡는다.
  const view = useMemo(() => {
    const zone = landmarks?.zone;
    const useDmz = zone === "dmz" && landmarks?.dmz_home && landmarks?.dmz_cone;
    const home = useDmz ? landmarks!.dmz_home! : landmarks?.cube;
    const goal = useDmz ? landmarks!.dmz_cone! : landmarks?.cone;
    if (home && goal) {
      const cx = 0.5 * (home.x + goal.x);
      const cy = 0.5 * (home.y + goal.y);
      const half = Math.max(
        Math.abs(home.x - goal.x), Math.abs(home.y - goal.y)) * 0.6 + 30;
      return { cx, cy, extent: Math.max(60, half) };
    }
    if (landmarks?.home && landmarks?.goal) {
      const origin = landmarks.home;
      if (landmarks.overhead?.extent && landmarks.overhead.x != null
          && landmarks.overhead.y != null) {
        const center = toLocalFromHome(landmarks.overhead, origin);
        return {
          cx: center.x,
          cy: center.y,
          extent: Math.max(60, Number(landmarks.overhead.extent)),
        };
      }
      const pts: Pt[] = [
        { x: 0, y: 0 },
        toLocalFromHome(landmarks.goal, origin),
        ...Object.values(landmarks.tactical_points ?? {})
          .map((p) => toLocalFromHome(p, origin)),
      ];
      const minX = Math.min(...pts.map((p) => p.x));
      const maxX = Math.max(...pts.map((p) => p.x));
      const minY = Math.min(...pts.map((p) => p.y));
      const maxY = Math.max(...pts.map((p) => p.y));
      const cx = 0.5 * (minX + maxX);
      const cy = 0.5 * (minY + maxY);
      const half = Math.max(maxX - minX, maxY - minY) * 0.65 + 20;
      return { cx, cy, extent: Math.max(60, half) };
    }
    if (home) return { cx: home.x, cy: home.y, extent: DEFAULT_EXTENT };
    if (cur) return { cx: cur.x, cy: cur.y, extent: DEFAULT_EXTENT };
    return { cx: 0, cy: 0, extent: DEFAULT_EXTENT };
  }, [landmarks, cur]);

  useEffect(() => {
    const c = cv.current;
    if (!c) return;
    const ctx = c.getContext("2d")!;
    const W = (c.width = c.clientWidth);
    const H = (c.height = c.clientHeight);
    const toPx = (p: Pt) => ({
      px: W / 2 + ((p.x - view.cx) / view.extent) * (W / 2),
      py: H / 2 - ((p.y - view.cy) / view.extent) * (H / 2),
    });

    ctx.clearRect(0, 0, W, H);
    // 링 그리드
    ctx.strokeStyle = "rgba(70,244,168,0.18)";
    for (let r = 1; r <= 3; r++) {
      ctx.beginPath();
      ctx.arc(W / 2, H / 2, (Math.min(W, H) / 2) * (r / 3), 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.beginPath();
    ctx.moveTo(W / 2, 0); ctx.lineTo(W / 2, H);
    ctx.moveTo(0, H / 2); ctx.lineTo(W, H / 2);
    ctx.stroke();

    // 궤적
    ctx.strokeStyle = "rgba(70,244,168,0.55)";
    ctx.beginPath();
    track.forEach((p, i) => {
      const { px, py } = toPx(p);
      i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
    });
    ctx.stroke();

    // 랜드마크: fence (회색 점 라인)
    if (landmarks?.fence?.length) {
      ctx.fillStyle = "rgba(180,180,180,0.55)";
      landmarks.fence.forEach((f) => {
        const { px, py } = toPx(f);
        ctx.beginPath();
        ctx.arc(px, py, 3, 0, Math.PI * 2);
        ctx.fill();
      });
    }
    // cube (홈, 파랑)
    if (landmarks?.cube) {
      const { px, py } = toPx(landmarks.cube);
      ctx.fillStyle = "#5fa8f0";
      ctx.fillRect(px - 5, py - 5, 10, 10);
      ctx.strokeStyle = "rgba(95,168,240,0.4)";
      ctx.strokeRect(px - 9, py - 9, 18, 18);
      ctx.fillStyle = "rgba(95,168,240,0.9)";
      ctx.font = "10px monospace";
      ctx.fillText("HOME", px + 8, py - 8);
    }
    // cone (목적지, 주황)
    if (landmarks?.cone) {
      const { px, py } = toPx(landmarks.cone);
      ctx.fillStyle = "#f4a040";
      ctx.beginPath();
      ctx.moveTo(px, py - 6);
      ctx.lineTo(px + 6, py + 5);
      ctx.lineTo(px - 6, py + 5);
      ctx.closePath();
      ctx.fill();
      ctx.fillStyle = "rgba(244,160,64,0.9)";
      ctx.fillText("CONE", px + 8, py + 4);
    }
    // DMZ zone markers (별색: amber)
    if (landmarks?.dmz_home) {
      const { px, py } = toPx(landmarks.dmz_home);
      ctx.fillStyle = "#f4b740";
      ctx.fillRect(px - 4, py - 4, 8, 8);
      ctx.fillText("DMZ", px + 6, py - 6);
    }
    if (landmarks?.dmz_cone) {
      const { px, py } = toPx(landmarks.dmz_cone);
      ctx.fillStyle = "#f4b740";
      ctx.beginPath();
      ctx.arc(px, py, 4, 0, Math.PI * 2);
      ctx.fill();
    }
    if (landmarks?.dmz_patrol_w) {
      const { px, py } = toPx(landmarks.dmz_patrol_w);
      ctx.fillStyle = "#f4b740";
      ctx.beginPath();
      ctx.arc(px, py, 4, 0, Math.PI * 2);
      ctx.fill();
    }
    // camera_publisher.py landmarks: home/goal are Isaac world coordinates,
    // so draw them in the same local frame as odom and projected detections.
    if (landmarks?.home) {
      const { px, py } = toPx({ x: 0, y: 0, z: 0 });
      ctx.fillStyle = "#5fa8f0";
      ctx.fillRect(px - 5, py - 5, 10, 10);
      ctx.strokeStyle = "rgba(95,168,240,0.45)";
      ctx.strokeRect(px - 10, py - 10, 20, 20);
      ctx.fillStyle = "rgba(95,168,240,0.95)";
      ctx.font = "10px monospace";
      ctx.fillText("HOME", px + 8, py - 8);
    }
    if (landmarks?.home && landmarks?.goal) {
      const goalLocal = toLocalFromHome(landmarks.goal, landmarks.home);
      const { px, py } = toPx(goalLocal);
      ctx.fillStyle = "#f4a040";
      ctx.beginPath();
      ctx.moveTo(px, py - 6);
      ctx.lineTo(px + 6, py + 5);
      ctx.lineTo(px - 6, py + 5);
      ctx.closePath();
      ctx.fill();
      ctx.fillStyle = "rgba(244,160,64,0.95)";
      ctx.fillText("GOAL", px + 8, py + 4);
    }
    // DMZ fence 점선
    if (landmarks?.dmz_fence?.length === 2) {
      const a = toPx(landmarks.dmz_fence[0]);
      const b = toPx(landmarks.dmz_fence[1]);
      ctx.strokeStyle = "rgba(244,183,64,0.6)";
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(a.px, a.py);
      ctx.lineTo(b.px, b.py);
      ctx.stroke();
      ctx.setLineDash([]);
    }
    // Tactical fixed cameras TP_A/B/C/D. They are stored in Isaac world
    // coordinates, while /robot/odom map is local from home, so draw them
    // after subtracting landmarks.home.
    if (landmarks?.tactical_points) {
      const origin = landmarks.home ?? { x: 0, y: 0, z: 0 };
      Object.entries(landmarks.tactical_points).forEach(([name, p]) => {
        const local = toLocalFromHome(p, origin);
        const { px, py } = toPx(local);
        ctx.fillStyle = "#46f4a8";
        ctx.beginPath();
        ctx.arc(px, py, 5, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = "rgba(70,244,168,0.55)";
        ctx.beginPath();
        ctx.arc(px, py, 11, 0, Math.PI * 2);
        ctx.stroke();
        ctx.fillStyle = "rgba(70,244,168,0.95)";
        ctx.font = "10px monospace";
        ctx.fillText(name, px + 7, py - 7);
      });
    }
    // patrol route (현재 큐)
    if (patrolState?.route?.length) {
      ctx.strokeStyle = "rgba(244,183,64,0.5)";
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      patrolState.route.forEach((p, i) => {
        const { px, py } = toPx(p);
        i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
      });
      ctx.stroke();
      ctx.setLineDash([]);
    }
    // 현재 nav goal
    if (patrolState?.waypoint) {
      const { px, py } = toPx(patrolState.waypoint);
      ctx.strokeStyle = "#f4b740";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(px, py, 10, 0, Math.PI * 2);
      ctx.stroke();
      ctx.lineWidth = 1;
    }
    // 침입자 (빨강 점)
    intruders?.forEach((it) => {
      const { px, py } = toPx(it);
      ctx.fillStyle = "#ff5050";
      ctx.beginPath();
      ctx.arc(px, py, 5, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "rgba(255,80,80,0.45)";
      ctx.beginPath();
      ctx.arc(px, py, 12, 0, Math.PI * 2);
      ctx.stroke();
    });
    // YOLO fixed-camera detections projected to map.
    detections?.forEach((det) => {
      const { px, py } = toPx(det);
      const danger = det.risk === "danger"
        || det.label === "person"
        || det.label === "soldier";
      ctx.fillStyle = danger ? "#ff4040" : "#f4d040";
      ctx.beginPath();
      ctx.arc(px, py, danger ? 6 : 5, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = danger
        ? "rgba(255,64,64,0.55)"
        : "rgba(244,208,64,0.5)";
      ctx.beginPath();
      ctx.arc(px, py, danger ? 15 : 12, 0, Math.PI * 2);
      ctx.stroke();
      ctx.fillStyle = danger
        ? "rgba(255,120,120,0.95)"
        : "rgba(244,220,100,0.95)";
      ctx.font = "10px monospace";
      const conf = det.confidence != null ? ` ${(det.confidence * 100).toFixed(0)}%` : "";
      const depth = det.range_m ? ` d${det.range_m.toFixed(1)}` : "";
      const ground = det.ground_range_m ? ` g${det.ground_range_m.toFixed(1)}m` : "";
      ctx.fillText(`${det.camera.toUpperCase()} ${det.label}${depth}${ground}${conf}`, px + 8, py - 8);
    });
    // 현재 위치 + 시야각 (inspect 전방 + rear 후방)
    if (cur) {
      const { px, py } = toPx(cur);
      // yaw 우선순위: odom (5+Hz, 가장 fresh) > patrolState.pose (mode 따라
      // 안 갱신 가능) > 0. 이전에는 patrolState 만 의존해 IDLE 모드에서
      // cone 이 stale (2026-05-21 fix).
      const yaw = cur.yaw ?? patrolState?.pose?.yaw ?? 0;

      // FOV cone — Isaac 카메라 spec: W=1280, aperture=20.955, focal=18mm
      //   hFOV = 2 * atan(W/2 / fx) = 2 * atan(0.5 / (18/20.955)) ≈ 60°
      // 시각화 거리: 25 m (정상 보행 시야).
      const FOV_RAD = (60 * Math.PI) / 180;
      const HALF = FOV_RAD / 2;
      const RANGE_M = 25;
      const rangePx = (RANGE_M / view.extent) * (W / 2);
      const drawCone = (centerYaw: number, fill: string, stroke: string) => {
        ctx.beginPath();
        ctx.moveTo(px, py);
        // canvas: +y down → screen yaw = -world yaw
        const a0 = -(centerYaw - HALF);
        const a1 = -(centerYaw + HALF);
        ctx.arc(px, py, rangePx, a0, a1, true);
        ctx.closePath();
        ctx.fillStyle = fill;
        ctx.fill();
        ctx.strokeStyle = stroke;
        ctx.lineWidth = 1;
        ctx.stroke();
      };
      // inspect (전방) — cyan 반투명
      drawCone(yaw, "rgba(80,200,255,0.10)", "rgba(80,200,255,0.55)");
      // rear (후방) — orange 반투명
      drawCone(yaw + Math.PI, "rgba(255,170,80,0.07)", "rgba(255,170,80,0.4)");

      // robot 원 + yaw 화살표
      ctx.fillStyle = "#46f4a8";
      ctx.beginPath();
      ctx.arc(px, py, 5, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "#46f4a8";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(px, py);
      ctx.lineTo(px + Math.cos(yaw) * 14, py - Math.sin(yaw) * 14);
      ctx.stroke();
      ctx.lineWidth = 1;
    }
    // 보류 목표
    if (pending) {
      const { px, py } = toPx(pending);
      ctx.strokeStyle = "#f4b740";
      ctx.beginPath();
      ctx.moveTo(px - 7, py); ctx.lineTo(px + 7, py);
      ctx.moveTo(px, py - 7); ctx.lineTo(px, py + 7);
      ctx.stroke();
    }
    // alert overlay (적색 테두리)
    if (alertActive) {
      ctx.strokeStyle = "rgba(255,80,80,0.7)";
      ctx.lineWidth = 4;
      ctx.strokeRect(2, 2, W - 4, H - 4);
      ctx.lineWidth = 1;
      ctx.fillStyle = "#ff5050";
      ctx.font = "bold 11px monospace";
      ctx.fillText("ALERT", 8, 16);
    }
  }, [track, cur, pending, view, landmarks, intruders, detections, patrolState, alertActive]);

  const onClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const c = cv.current!;
    const rect = c.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;
    const x = view.cx + ((px - rect.width / 2) / (rect.width / 2)) * view.extent;
    const y = view.cy + (-(py - rect.height / 2) / (rect.height / 2)) * view.extent;
    setPending({ x, y });
    setMsg(`목표 지정: ${x.toFixed(1)}, ${y.toFixed(1)} — 더블클릭=goto · Shift+클릭=look_at`);
  };

  const onDouble = async () => {
    if (!pending) return;
    try {
      await postJSON(`/robots/${ROBOT_ID}/goto`, pending);
      setMsg(`GOTO 전송됨 → ${pending.x.toFixed(1)}, ${pending.y.toFixed(1)}`);
      setPending(null);
    } catch (e: any) {
      setMsg(`전송 실패: ${e.message}`);
    }
  };

  const onShiftClick = async (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!e.shiftKey) return;
    const c = cv.current!;
    const rect = c.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;
    const x = view.cx + ((px - rect.width / 2) / (rect.width / 2)) * view.extent;
    const y = view.cy + (-(py - rect.height / 2) / (rect.height / 2)) * view.extent;
    try {
      await postJSON(`/robots/${ROBOT_ID}/inspect`,
                     { look_at: [x, y, 1.0], absolute: true });
      setMsg(`검사 카메라 look_at(${x.toFixed(1)}, ${y.toFixed(1)})`);
    } catch (e: any) {
      setMsg(`inspect 실패: ${e.message}`);
    }
  };

  return (
    <div className="panel flex flex-col">
      <div className="panel-hd">
        <span>TACTICAL MAP · {ROBOT_ID.toUpperCase()}</span>
        <span className="text-dim">
          ±{view.extent.toFixed(0)}m · ({view.cx.toFixed(0)},{view.cy.toFixed(0)})
          {patrolState?.mode && ` · ${patrolState.mode}`}
        </span>
      </div>
      <div className="relative aspect-square w-full max-w-sm mx-auto bg-black">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={`${getApiBase()}/c2/video/mjpeg?camera=overhead`}
          alt="overhead"
          className="absolute inset-0 w-full h-full object-cover opacity-55 pointer-events-none"
        />
        <canvas
          ref={cv}
          onClick={(e) => e.shiftKey ? onShiftClick(e) : onClick(e)}
          onDoubleClick={onDouble}
          className="absolute inset-0 w-full h-full cursor-crosshair"
        />
        {/* 시야각 범례 */}
        <div className="absolute bottom-1 left-1 text-[9px] font-mono
                        bg-black/70 px-1.5 py-0.5 flex gap-2 leading-tight">
          <span className="text-cyan-300">▲ INSPECT 60°·25m</span>
          <span className="text-amber-300">▼ REAR 60°·25m</span>
        </div>
      </div>
      <div className="px-3 py-1.5 text-[11px] text-amber border-t border-line min-h-[26px]">
        {msg || "맵 클릭=목표지정 · 더블클릭=GOTO · Shift+클릭=검사 카메라 look_at"}
      </div>
    </div>
  );
}
