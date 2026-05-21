"use client";
import { useCallback, useEffect, useState } from "react";
import StatusHeader from "@/components/StatusHeader";
import TelemetryStrip from "@/components/TelemetryStrip";
import DualCameraView from "@/components/DualCameraView";
import MapTrack from "@/components/MapTrack";
import PatrolControls from "@/components/PatrolControls";
import InspectorCameraPanel from "@/components/InspectorCameraPanel";
import AlertsLog from "@/components/AlertsLog";
import AnimalAlertsLog from "@/components/AnimalAlertsLog";
import TeleopPad from "@/components/TeleopPad";
import BaseMovementPanel from "@/components/BaseMovementPanel";
import NpcSpawnButton from "@/components/NpcSpawnButton";
import FallStatusBadge from "@/components/FallStatusBadge";
import {
  C2Event, getJSON, ROBOT_ID, useEvents,
  LandmarksPayload, PatrolStatePayload, IntruderState, AlertPayload,
  FallPayload,
} from "@/lib/api";

type Snap = {
  state?: { mode?: string; gait?: string; battery?: number; waypoint?: number };
  gps?: { lat?: number; lon?: number; alt?: number };
  odom?: { x?: number; y?: number; z?: number; yaw?: number };
  arm_q?: number[];
  leg_q?: number[];
};

export default function Page() {
  const [snap, setSnap] = useState<Snap>({});
  const [track, setTrack] = useState<{ x: number; y: number }[]>([]);
  const [landmarks, setLandmarks] = useState<LandmarksPayload | null>(null);
  const [patrolState, setPatrolState] = useState<PatrolStatePayload | null>(null);
  const [intruders, setIntruders] = useState<IntruderState[]>([]);
  const [alertEvents, setAlertEvents] =
    useState<{ ts: string; data: AlertPayload }[]>([]);
  const [animalAlertEvents, setAnimalAlertEvents] =
    useState<{ ts: string; data: AlertPayload & { label: string } }[]>([]);
  const [fallEvents, setFallEvents] =
    useState<{ ts: string; data: FallPayload }[]>([]);
  const [eventStream, setEventStream] = useState<C2Event[]>([]);
  const [lastAlertTs, setLastAlertTs] = useState<number | null>(null);
  const [showTeleop, setShowTeleop] = useState(false);
  const [showBaseMv, setShowBaseMv] = useState(true);

  // 초기 스냅샷 폴백 (4초 폴링)
  useEffect(() => {
    const pull = async () => {
      try {
        const [st, gps] = await Promise.all([
          getJSON<any>(`/robots/${ROBOT_ID}/state`),
          getJSON<any>(`/robots/${ROBOT_ID}/gps`),
        ]);
        setSnap((s) => ({ ...s, ...st, gps: gps.gps }));
      } catch {}
    };
    pull();
    const iv = setInterval(pull, 4000);
    return () => clearInterval(iv);
  }, []);

  const onEvent = useCallback((e: C2Event) => {
    if (e.type === "state") {
      setSnap((s) => ({ ...s, state: e.data,
                       odom: e.data?.odom ?? s.odom }));
    } else if (e.type === "gps") {
      setSnap((s) => ({ ...s, gps: e.data }));
    } else if (e.type === "landmarks") {
      setLandmarks(e.data);
    } else if (e.type === "patrol_state") {
      setPatrolState(e.data);
    } else if (e.type === "intruder_state") {
      const items = Array.isArray(e.data) ? e.data : (e.data?.items ?? []);
      setIntruders(items);
    } else if (e.type === "alert") {
      setAlertEvents((p) => [...p.slice(-49), { ts: e.ts, data: e.data }]);
      setLastAlertTs(Date.now());
    } else if (e.type === "animal_alert") {
      setAnimalAlertEvents((p) =>
        [...p.slice(-49), { ts: e.ts, data: e.data }]);
    } else if (e.type === "fall_alert") {
      setFallEvents((p) => [...p.slice(-29), { ts: e.ts, data: e.data }]);
      // FALLEN edge → 화면 빨강 깜빡 트리거(기존 alertActive 재사용)
      if (e.data.state === "FALLEN") setLastAlertTs(Date.now());
    }
    setEventStream((p) => [...p.slice(-99), e]);
  }, []);

  const wsOk = useEvents(onEvent);

  useEffect(() => {
    const od = snap.odom;
    if (od?.x != null && od.y != null)
      setTrack((t) => [...t.slice(-400), { x: od.x!, y: od.y! }]);
  }, [snap.odom]);

  const cur = snap.odom?.x != null
    ? { x: snap.odom.x, y: snap.odom.y! }
    : null;
  const alertActive = lastAlertTs != null
    && Date.now() - lastAlertTs < 8000;

  return (
    <div className={alertActive ? "alert-active" : ""}>
      <main className="relative z-10 min-h-screen flex flex-col">
        <div className="flex items-stretch">
          <div className="flex-1"><StatusHeader wsOk={wsOk} landmarks={landmarks} /></div>
          <div className="flex items-center pr-3 border-b border-line bg-black/40">
            <FallStatusBadge liveFallEvents={fallEvents} />
          </div>
        </div>
        <TelemetryStrip
          state={snap.state ?? null}
          gps={snap.gps ?? null}
          odom={snap.odom ?? null}
          patrol={patrolState}
        />

        {/* HERO: ImmersiveCamera + MapTrack + Controls — 1 viewport row */}
        <section
          className="grid grid-cols-1 xl:grid-cols-12 gap-3 p-3"
          aria-label="hero">
          {/* 좌측 5col — DualCameraView (기존 INSPECT + REAR) */}
          <div className="xl:col-span-5 min-w-0 min-h-[420px]">
            <DualCameraView />
          </div>
          {/* 중앙 4col — MapTrack (정사각형) */}
          <div className="xl:col-span-4 min-w-0">
            <MapTrack track={track} cur={cur}
                      landmarks={landmarks}
                      intruders={intruders}
                      patrolState={patrolState}
                      alertActive={alertActive} />
          </div>
          {/* 우측 3col — Patrol + Inspect+BaseMv (통합) */}
          <div className="xl:col-span-3 flex flex-col gap-2 min-w-0">
            <PatrolControls patrolState={patrolState} />
            {/* InspectCam + BaseMovement 통합 컨테이너 (사용자 요청) */}
            <div className="panel flex flex-col">
              <div className="panel-hd">
                <span>ROBOT CONTROL</span>
                <span className="text-[10px] text-dim">INSPECT · MOVE</span>
              </div>
              <div className="p-2 flex flex-col gap-2">
                {/* INSPECT CAM + BASE MOVEMENT 가로 2-column 배치 */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  <div className="min-w-0">
                    <InspectorCameraPanel />
                  </div>
                  <div className="min-w-0">
                    {showBaseMv && <BaseMovementPanel />}
                    {showTeleop && <TeleopPad />}
                  </div>
                </div>
                <div className="flex gap-1.5">
                  <button
                    type="button"
                    onClick={() => setShowBaseMv((v) => !v)}
                    className="flex-1 text-[10px] px-2 py-0.5 rounded
                               bg-zinc-800 hover:bg-zinc-700 text-dim">
                    {showBaseMv ? "▼" : "▶"} BASE MV
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowTeleop((v) => !v)}
                    className="flex-1 text-[10px] px-2 py-0.5 rounded
                               bg-zinc-800 hover:bg-zinc-700 text-dim">
                    {showTeleop ? "▼" : "▶"} TELEOP
                  </button>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ALERTS + NPC row */}
        <section
          className="grid grid-cols-1 lg:grid-cols-3 gap-3 px-3 pb-3"
          aria-label="alerts">
          <AlertsLog liveEvents={alertEvents} />
          <AnimalAlertsLog liveEvents={animalAlertEvents} />
          <NpcSpawnButton />
        </section>
      </main>
    </div>
  );
}
