"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { postJSON, ROBOT_ID } from "@/lib/api";

// quadruped_example.py 의 base_command 누적 패턴 (사용자 사양 #4, 2026-05-20).
// _base_command = [vx, vy, wz]. press → +=, release → -=. 동시 입력 가능.
type Vec = [number, number, number];

const KEY_MAP: Record<string, Vec> = {
  // forward / back
  KeyW: [1, 0, 0], ArrowUp:   [1, 0, 0],
  KeyS: [-1, 0, 0], ArrowDown: [-1, 0, 0],
  // strafe left / right (robot body frame)
  KeyA: [0, 1, 0], ArrowLeft:  [0, 1, 0],
  KeyD: [0, -1, 0], ArrowRight: [0, -1, 0],
  // yaw + / -
  KeyQ: [0, 0, 1],
  KeyE: [0, 0, -1],
};

const SEND_MS = 100;

export default function BaseMovementPanel() {
  const [maxSpeed, setMaxSpeed] = useState(0.6);
  const [pressed, setPressed] = useState<Set<string>>(new Set());
  const baseRef = useRef<Vec>([0, 0, 0]);
  const sendTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const maxSpeedRef = useRef(maxSpeed);
  useEffect(() => { maxSpeedRef.current = maxSpeed; }, [maxSpeed]);

  const send = useCallback(async (vx: number, vy: number, wz: number) => {
    try {
      await postJSON(`/robots/${ROBOT_ID}/cmd_vel`, {
        linear: vx, linear_y: vy, angular: wz,
      });
    } catch {}
  }, []);

  const recomputeBase = useCallback((keys: Set<string>) => {
    const acc: Vec = [0, 0, 0];
    keys.forEach((k) => {
      const v = KEY_MAP[k];
      if (!v) return;
      acc[0] += v[0]; acc[1] += v[1]; acc[2] += v[2];
    });
    baseRef.current = acc;
  }, []);

  const tick = useCallback(() => {
    const s = maxSpeedRef.current;
    const [bx, by, bz] = baseRef.current;
    send(bx * s, by * s, bz * s);
  }, [send]);

  // 송신 타이머 — 항상 100ms 주기 (0 도 발행해 stop 보장).
  useEffect(() => {
    sendTimerRef.current = setInterval(tick, SEND_MS);
    return () => { if (sendTimerRef.current) clearInterval(sendTimerRef.current); };
  }, [tick]);

  // 키보드 listener
  useEffect(() => {
    const onDown = (e: KeyboardEvent) => {
      if (e.code === "Space") {
        e.preventDefault();
        setPressed(new Set());
        baseRef.current = [0, 0, 0];
        send(0, 0, 0);
        return;
      }
      if (!KEY_MAP[e.code] || e.repeat) return;
      e.preventDefault();
      setPressed((prev) => {
        if (prev.has(e.code)) return prev;
        const next = new Set(prev); next.add(e.code);
        recomputeBase(next);
        return next;
      });
    };
    const onUp = (e: KeyboardEvent) => {
      if (!KEY_MAP[e.code]) return;
      setPressed((prev) => {
        if (!prev.has(e.code)) return prev;
        const next = new Set(prev); next.delete(e.code);
        recomputeBase(next);
        return next;
      });
    };
    window.addEventListener("keydown", onDown);
    window.addEventListener("keyup", onUp);
    return () => {
      window.removeEventListener("keydown", onDown);
      window.removeEventListener("keyup", onUp);
    };
  }, [recomputeBase, send]);

  const pressKey = useCallback((code: string) => {
    setPressed((prev) => {
      if (prev.has(code)) return prev;
      const next = new Set(prev); next.add(code);
      recomputeBase(next);
      return next;
    });
  }, [recomputeBase]);

  const releaseKey = useCallback((code: string) => {
    setPressed((prev) => {
      if (!prev.has(code)) return prev;
      const next = new Set(prev); next.delete(code);
      recomputeBase(next);
      return next;
    });
  }, [recomputeBase]);

  const stopAll = useCallback(() => {
    setPressed(new Set());
    baseRef.current = [0, 0, 0];
    send(0, 0, 0);
  }, [send]);

  const btn = (code: string, label: string, hint: string) => (
    <button
      className="btn select-none touch-none"
      style={pressed.has(code) ? { borderColor: "var(--phos)", color: "var(--phos)" } : undefined}
      onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); pressKey(code); }}
      onPointerUp={() => releaseKey(code)}
      onPointerCancel={() => releaseKey(code)}
      title={hint}
    >
      {label}
    </button>
  );

  const [bx, by, bz] = baseRef.current;

  return (
    <div className="panel">
      <div className="panel-hd">BASE MOVEMENT · 직접 보행 제어</div>
      <div className="p-3 flex flex-col gap-3">
        <div className="grid grid-cols-3 gap-1 w-fit mx-auto">
          {btn("KeyQ", "↺", "Q · yaw+")}
          {btn("KeyW", "▲", "W · 전진")}
          {btn("KeyE", "↻", "E · yaw-")}
          {btn("KeyA", "◀", "A · 좌평행")}
          <button className="btn text-alert" onClick={stopAll} title="Space · 정지">■</button>
          {btn("KeyD", "▶", "D · 우평행")}
          <div />
          {btn("KeyS", "▼", "S · 후진")}
          <div />
        </div>

        <div className="flex items-center gap-2 text-[11px] text-dim">
          <span className="tracking-[0.15em] w-12">SPEED</span>
          <input
            type="range" min={0.1} max={1.6} step={0.05}
            value={maxSpeed}
            onChange={(e) => setMaxSpeed(parseFloat(e.target.value))}
            className="flex-1 accent-[var(--phos)]"
          />
          <span className="w-10 text-right text-ink">{maxSpeed.toFixed(2)}</span>
        </div>

        <div className="text-[10px] text-dim leading-snug">
          키보드: W/S 전후, A/D 좌우평행, Q/E 좌우회전, Space 정지.
          버튼 누름 동안 누적 cmd_vel (100ms 주기). 현재 [vx={(bx * maxSpeed).toFixed(2)},
          vy={(by * maxSpeed).toFixed(2)}, wz={(bz * maxSpeed).toFixed(2)}].
        </div>
      </div>
    </div>
  );
}
