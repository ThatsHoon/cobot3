"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import VideoWall from "@/components/VideoWall";
import ContactsPanel from "@/components/ContactsPanel";
import ReadinessStrip from "@/components/ReadinessStrip";
import MapTrack from "@/components/MapTrack";
import OpsLedger, { LedgerItem } from "@/components/OpsLedger";
import DiagnosticsStrip from "@/components/DiagnosticsStrip";
import EngagementConsole from "@/components/EngagementConsole";
import ThreatBar, { Contact } from "@/components/ThreatBar";
import { C2Event, getJSON, ROBOT_ID, useEvents } from "@/lib/api";

const CONTACT_TTL = 8000; // ms — 마지막 탐지 후 위협 유지 시간

export default function Page() {
  const [snap, setSnap] = useState<any>({});
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [ledger, setLedger] = useState<LedgerItem[]>([]);
  const [track, setTrack] = useState<{ x: number; y: number }[]>([]);
  const [lastContactTs, setLastContactTs] = useState<number | null>(null);
  const [, setTick] = useState(0);
  const lastRef = useRef<number | null>(null);
  lastRef.current = lastContactTs;

  // 위협 감쇠용 틱
  useEffect(() => {
    const iv = setInterval(() => setTick((t) => t + 1), 500);
    return () => clearInterval(iv);
  }, []);

  // 초기 스냅샷 폴백
  useEffect(() => {
    const pull = async () => {
      try {
        const [st, gps] = await Promise.all([
          getJSON<any>(`/robots/${ROBOT_ID}/state`),
          getJSON<any>(`/robots/${ROBOT_ID}/gps`),
        ]);
        setSnap((s: any) => ({ ...s, ...st, gps: gps.gps }));
      } catch {}
    };
    pull();
    const iv = setInterval(pull, 4000);
    return () => clearInterval(iv);
  }, []);

  const pushLedger = (it: LedgerItem) =>
    setLedger((l) => [...l.slice(-299), it]);

  const onEvent = useCallback((e: C2Event) => {
    if (e.type === "state") {
      setSnap((s: any) => ({
        ...s,
        state: e.data,
        odom: e.data?.odom ?? s.odom,
      }));
    } else if (e.type === "gps") {
      setSnap((s: any) => ({ ...s, gps: e.data }));
    } else if (e.type === "log") {
      pushLedger({
        ts: e.ts,
        sev: e.level >= 40 ? "alert" : "warn",
        tag: e.level >= 40 ? "SYS·ERR" : "SYS·WARN",
        msg: `${e.name}: ${e.msg}`,
      });
    } else if (e.type === "detection") {
      const items: Contact[] = (e.items || []).map((d: any) => ({
        ts: e.ts,
        class_name: d.class_name,
        conf: d.conf,
        bbox: d.bbox,
      }));
      if (items.length) {
        setContacts((c) => [...items, ...c].slice(0, 14));
        setLastContactTs(Date.now());
        const top = items[0];
        pushLedger({
          ts: e.ts,
          sev: "alert",
          tag: "CONTACT",
          msg: `${top.class_name} ${(top.conf * 100).toFixed(0)}% (x${items.length})`,
        });
      }
    } else if (e.type === "fire") {
      pushLedger({
        ts: e.ts,
        sev: e.hit ? "hit" : "warn",
        tag: "FIRE",
        msg: `${e.hit ? "HIT" : "MISS"} d=${e.distance_m ?? "?"}m by ${e.operator}`,
      });
    }
  }, []);

  const wsOk = useEvents(onEvent);

  useEffect(() => {
    const od = snap.odom;
    if (od?.x != null) setTrack((t) => [...t.slice(-400), { x: od.x, y: od.y }]);
  }, [snap.odom]);

  const active =
    lastContactTs != null && Date.now() - lastContactTs < CONTACT_TTL;
  const contact = active ? contacts[0] : null;
  const cur = snap.odom?.x != null ? { x: snap.odom.x, y: snap.odom.y } : null;

  return (
    <div className={active ? "alert-active" : ""}>
      <main className="relative z-10 min-h-screen p-4 flex flex-col gap-3">
        <header className="flex items-end justify-between">
          <div>
            <h1 className="font-display text-xl tracking-[0.28em] text-phos">
              GP · 지휘통제실
            </h1>
            <p className="text-[10px] text-dim tracking-[0.35em] mt-0.5">
              BORDER GUARD QUADRUPED · C2 OPERATIONS CONSOLE
            </p>
          </div>
          <div className="text-right text-[10px] text-dim leading-relaxed">
            <span className="text-ink">{ROBOT_ID.toUpperCase()}</span> ·{" "}
            <span className={wsOk ? "text-phos" : "text-alert"}>
              {wsOk ? "STREAM ●" : "OFFLINE ○"}
            </span>
          </div>
        </header>

        {/* 1순위: 위협 상태 */}
        <ThreatBar contact={contact} lastTs={lastContactTs} />

        {/* 2순위: 대응 가능 여부 (컴팩트 타일) */}
        <ReadinessStrip s={snap} wsOk={wsOk} />

        {/* 감시 코어: 영상 + 접촉/맵 */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-3 flex-1 min-h-0">
          <div className="xl:col-span-2 flex flex-col gap-3 min-h-0">
            <div className="flex-1 min-h-[340px]">
              <VideoWall detCount={contacts.length} contact={active} />
            </div>
            <EngagementConsole contact={active} wsOk={wsOk} />
          </div>
          <div className="flex flex-col gap-3 min-h-0">
            <div className="flex-1 min-h-[200px]">
              <ContactsPanel items={active ? contacts : contacts.slice(0, 4)} />
            </div>
            <div className="h-[240px]">
              <MapTrack track={track} cur={cur} />
            </div>
          </div>
        </div>

        <DiagnosticsStrip
          armQ={snap.arm_q || []}
          legQ={snap.leg_q || []}
        />

        {/* 통합 작전 로그 */}
        <div className="h-[180px]">
          <OpsLedger items={ledger} />
        </div>
      </main>
    </div>
  );
}
