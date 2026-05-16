"use client";
import { useEffect, useRef, useState } from "react";

export const API_BASE =
  process.env.NEXT_PUBLIC_C2_API || "http://localhost:8000";
export const ROBOT_ID = process.env.NEXT_PUBLIC_GP_ROBOT || "gp0";

export function apiKey(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("c2_api_key") || "";
}

export async function getJSON<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}

export async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": apiKey() },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}

export type C2Event =
  | { type: "state"; ts: string; data: any }
  | { type: "gps"; ts: string; data: { lat: number; lon: number; alt: number } }
  | { type: "log"; ts: string; level: number; name: string; msg: string }
  | { type: "detection"; ts: string; items: any[] }
  | { type: "fire"; ts: string; target: string; hit: boolean; distance_m: number | null; operator: string };

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
      const url = API_BASE.replace(/^http/, "ws") + "/events";
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
