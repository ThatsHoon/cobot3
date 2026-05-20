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
import EventLog from "@/components/EventLog";
import DiagnosticsStrip from "@/components/DiagnosticsStrip";
import TeleopPad from "@/components/TeleopPad";
import BaseMovementPanel from "@/components/BaseMovementPanel";
import NpcSpawnButton from "@/components/NpcSpawnButton";
import {
  C2Event, getJSON, ROBOT_ID, useEvents,
  LandmarksPayload, PatrolStatePayload, IntruderState, AlertPayload,
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
        <StatusHeader wsOk={wsOk} landmarks={landmarks} />
        <TelemetryStrip
          state={snap.state ?? null}
          gps={snap.gps ?? null}
          odom={snap.odom ?? null}
          patrol={patrolState}
        />

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-3 p-3 flex-1 min-h-0">
          {/* 좌: 영상 + 컨트롤 */}
          <div className="flex flex-col gap-3 min-h-0">
            <div className="flex-1 min-h-[360px]">
              <DualCameraView />
            </div>
            <PatrolControls patrolState={patrolState} />
            <div className="flex gap-2 items-center flex-wrap">
              <button
                onClick={() => setShowBaseMv((v) => !v)}
                className="text-[10px] px-2 py-1 rounded bg-zinc-800
                           hover:bg-zinc-700 text-dim">
                {showBaseMv ? "▼" : "▶"} BASE MOVEMENT
              </button>
              <button
                onClick={() => setShowTeleop((v) => !v)}
                className="text-[10px] px-2 py-1 rounded bg-zinc-800
                           hover:bg-zinc-700 text-dim">
                {showTeleop ? "▼" : "▶"} TELEOP (legacy)
              </button>
              <span className="text-[10px] text-dim">
                Base Movement: 이동/대기 중 추가 보행 명령 (사용자 사양 #4)
              </span>
            </div>
            {showBaseMv && <BaseMovementPanel />}
            {showTeleop && <TeleopPad />}
            <NpcSpawnButton />
          </div>

          {/* 우: 지도 + 검사 + 알람 */}
          <div className="flex flex-col gap-3 min-h-0">
            <div className="flex-1 min-h-[360px]">
              <MapTrack track={track} cur={cur}
                        landmarks={landmarks}
                        intruders={intruders}
                        patrolState={patrolState}
                        alertActive={alertActive} />
            </div>
            <InspectorCameraPanel />
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              <AlertsLog liveEvents={alertEvents} />
              <AnimalAlertsLog liveEvents={animalAlertEvents} />
            </div>
          </div>
        </div>

        <DiagnosticsStrip
          armQ={snap.arm_q || []}
          legQ={snap.leg_q || []}
        />
        <div className="h-[200px] p-3 pt-0">
          <EventLog events={eventStream} />
        </div>
      </main>
    </div>
  );
}
