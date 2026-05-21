"use client";
import { useEffect, useRef, useState } from "react";

// 빌드타임 env가 있으면 그걸 쓰고, 없으면 런타임에 window.location.hostname 기반으로 계산.
// 모듈 상수로 두면 SSR 시점(window 없음)에 "localhost"로 굳어버리므로 함수로 노출.
const _STATIC_BASE = process.env.NEXT_PUBLIC_C2_API ?? "";
export function getApiBase(): string {
  if (_STATIC_BASE) return _STATIC_BASE;
  // SSR (prerender) 안전 guard — window 미정의 시 빈 string. 클라이언트 hydrate
  // 후 첫 render 부터 정상 hostname 사용.
  if (typeof window === "undefined") return "";
  return `http://${window.location.hostname}:8000`;
}
export const API_BASE = _STATIC_BASE || "http://localhost:8000"; // SSR 호환용 (fetch 직접 호출 시 fallback)
export const ROBOT_ID = process.env.NEXT_PUBLIC_GP_ROBOT || "gp0";
// 디버그(/debug) 페이지가 iframe 으로 임베드하는 Lichtblick(Foxglove) URL.
// 같은-PC 임시: http://localhost:8080. NEXT_PUBLIC_* 는 빌드타임 주입.
export const LICHTBLICK_URL =
  process.env.NEXT_PUBLIC_LICHTBLICK_URL || "http://localhost:8080";

export function apiKey(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("c2_api_key") || "";
}

export async function getJSON<T>(path: string): Promise<T> {
  const r = await fetch(`${getApiBase()}${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}

export async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${getApiBase()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": apiKey() },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}

export type Landmark = { x: number; y: number; z?: number };
export type Pose2D = { x: number; y: number; yaw: number };
export type IntruderState = { id?: string; x: number; y: number; z?: number; label?: string };
export type LandmarksPayload = {
  cube?: Landmark;
  cone?: Landmark;
  fence?: Landmark[];
  // P2 (DMZ_Zone): 별도 평지 patrol home/cone/fence
  zone?: "cube" | "dmz";
  dmz_home?: Landmark;
  dmz_cone?: Landmark;
  dmz_patrol_w?: Landmark;
  dmz_fence?: Landmark[];
};
export type PatrolStatePayload = {
  mode: string;
  waypoint: { x: number; y: number } | null;
  home: { x: number; y: number };
  route: { x: number; y: number }[];
  pose: Pose2D | null;
  landmarks_received?: boolean;
};
export type AlertPayload = {
  level: string;
  event: string;
  confidence: number;
  bbox_xyxy: [number, number, number, number];
  count: number;
  action?: string;
};

// FALL 감지 (2026-05-21) — fall_relay 사이드카 → /robot/fall_alert/state
export type FallPayload = {
  level: "ALERT" | "WARN" | "INFO";
  event: string;     // robot_fall_detected / robot_recovery_in_progress / robot_recovery_done / robot_upright
  state: "FALLEN" | "RECOVERING" | "RECOVERED" | "UPRIGHT";
  up_z: number;      // 직립=1.0, 누움≈0
  stage: number | null;  // RECOVERING 시 0..3
  pose?: { x: number; y: number; z: number };
  ts: number;
};

// Weather + Wind (2026-05-21)
export type WeatherCommand = {
  time_of_day?: "morning" | "noon" | "evening" | "night";
  weather?: "clear" | "cloudy" | "fog" | "rain" | "snow";
  wind_mode?: "calm" | "breeze" | "windy" | "gale" | "storm";
  wind_random_dir?: boolean;
  wind_dir_deg?: number | null;
  wind_speed_m_s?: number | null;
};
export type WindState = {
  vx: number; vy: number; vz: number;
  speed: number; dir_deg: number;     // derived in ros_bridge
};
// Weapon (HITL 2026-05-21)
export type WeaponState = {
  state: "IDLE" | "RAMP_DOWN" | "FIRE" | "HOLD" | "RAMP_UP" | "COOLDOWN";
  fire_id: string | null;
  cooldown_remaining_s: number;
  ts: number;
};
export type FireEvent = {
  ts: string; target: string;
  hit: boolean | null;          // null=인간 판정 대기
  distance_m: number | null;
  operator: string;
  fire_id: string | null;
  state: string;
  success: boolean;
};

export type C2Event =
  | { type: "state"; ts: string; data: any }
  | { type: "gps"; ts: string; data: { lat: number; lon: number; alt: number } }
  | { type: "log"; ts: string; level: number; name: string; msg: string }
  | { type: "detection"; ts: string; items: any[] }
  | { type: "fire"; ts: string; target: string; hit: boolean | null; distance_m: number | null; operator: string; fire_id: string | null; state: string; success: boolean }
  | { type: "fire_result"; ts: string; fire_id: string; hit: boolean; miss_reason: string | null }
  | { type: "weapon_state"; ts: string; data: WeaponState }
  | { type: "wind_state"; ts: string; data: WindState }
  | { type: "alert"; ts: string; data: AlertPayload }
  | { type: "animal_alert"; ts: string; data: AlertPayload & { label: string } }
  | { type: "fall_alert"; ts: string; data: FallPayload }
  | { type: "patrol_state"; ts: string; data: PatrolStatePayload }
  | { type: "intruder_state"; ts: string; data: IntruderState[] | { items: IntruderState[] } }
  | { type: "landmarks"; ts: string; data: LandmarksPayload };

/** WS /events 구독. 자동 재연결. */
export function useEvents(onEvent: (e: C2Event) => void) {
  const [connected, setConnected] = useState(false);
  const cb = useRef(onEvent);
  cb.current = onEvent;

  useEffect(() => {
    let ws: WebSocket | null = null;
    let ping: ReturnType<typeof setInterval> | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let closed = false;

    const connect = () => {
      const url = getApiBase().replace(/^http/, "ws") + "/events";
      console.info("[C2/ws] connecting →", url);
      ws = new WebSocket(url);
      ws.onopen = () => {
        setConnected(true);
        console.info("[C2/ws] ✓ connected");
        ping = setInterval(() => ws?.readyState === 1 && ws.send("ping"), 15000);
      };
      ws.onmessage = (m) => {
        try {
          const ev = JSON.parse(m.data);
          // 진단 이벤트는 콘솔에 깔끔하게 표시
          if (ev.type === "diag") {
            const bad = ev.warn?.length || ev.hint || ev.fatal;
            console[bad ? "warn" : "debug"](
              `[C2/diag:${ev.src}]`,
              JSON.stringify({
                env: ev.env, rx: ev.rx, publishers: ev.publishers,
                hint: ev.hint, warn: ev.warn, fatal: ev.fatal,
              })
            );
          }
          cb.current(ev);
        } catch (e) {
          console.error("[C2/ws] parse fail", e);
        }
      };
      ws.onclose = () => {
        setConnected(false);
        console.warn("[C2/ws] closed — 2s 후 재연결");
        if (ping) clearInterval(ping);
        if (!closed) retry = setTimeout(connect, 2000);
      };
      ws.onerror = (e) => {
        console.error("[C2/ws] error", e);
        ws?.close();
      };
    };
    connect();
    return () => {
      closed = true;
      if (ping) clearInterval(ping);
      if (retry) clearTimeout(retry);
      ws?.close();
    };
  }, []);

  return connected;
}
