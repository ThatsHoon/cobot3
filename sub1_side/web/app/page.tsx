"use client";
import { useCallback, useEffect, useState } from "react";
import StatusHeader from "@/components/StatusHeader";
import TelemetryStrip from "@/components/TelemetryStrip";
import DualCameraView from "@/components/DualCameraView";
import MapTrack from "@/components/MapTrack";
import RobotControlPanel from "@/components/RobotControlPanel";
import AlertsLog from "@/components/AlertsLog";
import AnimalAlertsLog from "@/components/AnimalAlertsLog";
import NpcSpawnButton from "@/components/NpcSpawnButton";
import FallStatusBadge from "@/components/FallStatusBadge";
import WeatherControl from "@/components/WeatherControl";
import WindGauge from "@/components/WindGauge";
import TacticalOpsPanel from "@/components/TacticalOpsPanel";
import { WeaponSafetyProvider } from "@/components/WeaponSafetyContext";
import {
  C2Event, getJSON, ROBOT_ID, useEvents,
  LandmarksPayload, PatrolStatePayload, IntruderState, AlertPayload,
  FallPayload, WindState, WeaponState, RoutingStatePayload,
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
  const [wind, setWind] = useState<WindState | null>(null);
  const [weapon, setWeapon] = useState<WeaponState | null>(null);
  const [fireEvents, setFireEvents] =
    useState<{ fire_id: string | null; target: string }[]>([]);
  const [routingState, setRoutingState] = useState<RoutingStatePayload | null>(null);
  const [previewRoute, setPreviewRoute] = useState<{ x: number; y: number }[] | null>(null);
  const [tpDetections, setTpDetections] =
    useState<{ ts: string; camera: string }[]>([]);
  const [eventStream, setEventStream] = useState<C2Event[]>([]);
  const [lastAlertTs, setLastAlertTs] = useState<number | null>(null);

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
    } else if (e.type === "wind_state") {
      setWind(e.data);
    } else if (e.type === "weapon_state") {
      setWeapon(e.data);
    } else if (e.type === "fire") {
      if (e.fire_id) {
        setFireEvents((p) => [...p.slice(-19),
                              { fire_id: e.fire_id, target: e.target }]);
      }
    } else if (e.type === "routing_state") {
      setRoutingState(e.data);
    } else if (e.type === "detection") {
      const items: { camera?: string }[] = e.items || [];
      const ts = e.ts;
      const entries = items
        .filter((d) => d.camera && d.camera.startsWith("tp_"))
        .map((d) => ({ ts, camera: d.camera as string }));
      if (entries.length > 0)
        setTpDetections((p) => [...p.slice(-199), ...entries]);
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
    ? { x: snap.odom.x, y: snap.odom.y!, yaw: snap.odom.yaw }
    : null;
  const alertActive = lastAlertTs != null
    && Date.now() - lastAlertTs < 8000;

  return (
    <WeaponSafetyProvider>
    <div className={alertActive ? "alert-active" : ""}>
      <main className="relative z-10 min-h-screen flex flex-col">
        <div className="flex items-stretch h-14 border-b border-line">
          <div className="flex-1 min-w-0"><StatusHeader wsOk={wsOk} landmarks={landmarks} /></div>
          <div className="flex items-stretch flex-shrink-0">
            <WindGauge wind={wind} />
            <FallStatusBadge liveFallEvents={fallEvents} />
          </div>
        </div>
        <TelemetryStrip
          state={snap.state ?? null}
          gps={snap.gps ?? null}
          odom={snap.odom ?? null}
          patrol={patrolState}
        />

        {/* ROW 1: CAMERA & MAP (Full Width 75% / 25%) */}
        <section className="grid grid-cols-1 xl:grid-cols-12 gap-3 p-3 pb-0" aria-label="cameras-map">
          <div className="xl:col-span-9 min-w-0 min-h-[320px]">
            <DualCameraView liveAlerts={alertEvents} tpDetections={tpDetections} />
          </div>
          <div className="xl:col-span-3 min-w-0">
            <MapTrack track={track} cur={cur}
                      landmarks={landmarks}
                      intruders={intruders}
                      patrolState={patrolState}
                      alertActive={alertActive}
                      routingState={routingState}
                      previewRoute={previewRoute} />
          </div>
        </section>

        {/* ROW 2: UNIFIED TACTICAL MISSION CONTROL & ROBOT DRIVING */}
        <section className="grid grid-cols-1 xl:grid-cols-12 gap-3 p-3 pb-0" aria-label="tactical-operations-driving">
          <div className="xl:col-span-8 min-w-0 h-full">
            <TacticalOpsPanel
              weapon={weapon}
              liveFireEvents={fireEvents}
              patrolState={patrolState}
              routingState={routingState}
              onPreviewChange={setPreviewRoute}
            />
          </div>
          <div className="xl:col-span-4 min-w-0 h-full">
            <RobotControlPanel />
          </div>
        </section>

        {/* ROW 3: ALERTS LOGS */}
        <section className="grid grid-cols-1 xl:grid-cols-12 gap-3 p-3 pb-0" aria-label="alerts-logs">
          <div className="xl:col-span-8 min-w-0 h-full">
            <AlertsLog liveEvents={alertEvents} />
          </div>
          <div className="xl:col-span-4 min-w-0 h-full">
            <AnimalAlertsLog liveEvents={animalAlertEvents} />
          </div>
        </section>

        {/* ROW 4: SIMULATION & ENV CONFIG */}
        <section className="grid grid-cols-1 xl:grid-cols-12 gap-3 p-3" aria-label="simulation-env">
          <div className="xl:col-span-8 min-w-0">
            <WeatherControl />
          </div>
          <div className="xl:col-span-4 min-w-0">
            <NpcSpawnButton />
          </div>
        </section>
      </main>
    </div>
    </WeaponSafetyProvider>
  );
}
