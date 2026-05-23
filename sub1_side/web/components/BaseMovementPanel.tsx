"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { postJSON, ROBOT_ID } from "@/lib/api";
import SettingsPopover from "./SettingsPopover";

type Vec = [number, number, number];

const KEY_MAP: Record<string, Vec> = {
  KeyW: [1, 0, 0],  ArrowUp:    [1, 0, 0],
  KeyS: [-1, 0, 0], ArrowDown:  [-1, 0, 0],
  KeyA: [0, 1, 0],  ArrowLeft:  [0, 1, 0],
  KeyD: [0, -1, 0], ArrowRight: [0, -1, 0],
  KeyQ: [0, 0, 1],
  KeyE: [0, 0, -1],
};

const SEND_MS = 100;

export default function BaseMovementPanel({ bare = false }: { bare?: boolean }) {
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

  useEffect(() => {
    sendTimerRef.current = setInterval(tick, SEND_MS);
    return () => { if (sendTimerRef.current) clearInterval(sendTimerRef.current); };
  }, [tick]);

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
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
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

  /** WASD/QE 키 버튼 — 컴팩트, 키 라벨 좌상 + 화살표 가운데. */
  const KeyCell = ({ code, arrow, hint, danger }: {
    code: string; arrow: string; hint: string; danger?: boolean;
  }) => {
    const active = pressed.has(code);
    const label = code.replace("Key", "");
    return (
      <button
        className="h-8 select-none touch-none relative border
                   font-display tracking-[0.04em] text-[11.5px]
                   transition-colors duration-75 flex items-center justify-center"
        style={{
          background: active
            ? "linear-gradient(180deg, var(--phos-faint), transparent)"
            : "linear-gradient(180deg, #0c1611, #050a08)",
          borderColor: active ? "var(--phos)" : (danger ? "var(--alert-dim)" : "var(--line-2)"),
          color: active ? "var(--phos)" : (danger ? "var(--alert)" : "var(--ink)"),
          boxShadow: active ? "inset 0 0 0 1px var(--phos-faint), 0 0 10px -2px var(--phos-glow)" : undefined,
        }}
        onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); pressKey(code); }}
        onPointerUp={() => releaseKey(code)}
        onPointerCancel={() => releaseKey(code)}
        title={hint}>
        <span className="absolute top-[1px] left-1 text-[7.5px] tracking-[0.08em] text-dim">{label}</span>
        <span className="leading-none">{arrow}</span>
      </button>
    );
  };

  const StopCell = () => (
    <button
      className="h-8 border font-display text-[12px] tracking-[0.06em]
                 transition-colors hover:opacity-90 flex items-center justify-center"
      style={{
        background: "linear-gradient(180deg, rgba(244,183,64,0.18), rgba(244,183,64,0.06))",
        borderColor: "var(--amber)",
        color: "var(--amber)",
        boxShadow: "inset 0 0 0 1px rgba(244,183,64,0.18)",
      }}
      onClick={stopAll}
      title="Space · 정지">
      ■
    </button>
  );

  const [bx, by, bz] = baseRef.current;
  const active = pressed.size > 0;

  const settingsPopover = (
    <SettingsPopover title="DRIVE · DETAIL">
      <div className="space-y-2 text-[10.5px]">
        <div className="text-dim tracking-[0.04em] leading-snug">
          KEYMAP — W/S 전후 · A/D 좌우 · Q/E 회전 · Space 정지<br/>
          버튼 누름 동안 누적 cmd_vel (100ms 주기)
        </div>
        <div className="border-t border-line pt-2">
          <div className="text-[9.5px] tracking-[0.22em] text-dim mb-1">SAFETY STOP</div>
          <button onClick={stopAll} data-tone="alert" className="btn w-full !py-2 !text-[11px]">
            ▣ EMERGENCY STOP
          </button>
        </div>
      </div>
    </SettingsPopover>
  );

  const body = (
    <div className="space-y-1.5">
      <div className="grid grid-cols-3 gap-1">
        <KeyCell code="KeyQ" arrow="↺" hint="Q · yaw+" />
        <KeyCell code="KeyW" arrow="▲" hint="W · 전진" />
        <KeyCell code="KeyE" arrow="↻" hint="E · yaw-" />
        <KeyCell code="KeyA" arrow="◀" hint="A · 좌평행" />
        <StopCell />
        <KeyCell code="KeyD" arrow="▶" hint="D · 우평행" />
        <div />
        <KeyCell code="KeyS" arrow="▼" hint="S · 후진" />
        <div />
      </div>

      <div className="flex items-center gap-1.5 text-[9px] tracking-[0.18em] pt-0.5">
        <span className="text-dim mr-1">SPEED</span>
        <button
          type="button"
          onClick={() => setMaxSpeed(0.1)}
          className="px-1 py-0.5 bg-panel-2 border border-line-2 hover:border-phos hover:text-phos text-dim text-[8.5px] font-display transition-colors"
          title="최소 속도로 변경">
          MIN
        </button>
        <input
          type="range" min={0.1} max={1.6} step={0.05}
          value={maxSpeed}
          onChange={(e) => setMaxSpeed(parseFloat(e.target.value))}
          className="flex-1 speed-slider-custom cursor-pointer" />
        <button
          type="button"
          onClick={() => setMaxSpeed(1.6)}
          className="px-1 py-0.5 bg-panel-2 border border-line-2 hover:border-phos hover:text-phos text-dim text-[8.5px] font-display transition-colors"
          title="최대 속도로 변경">
          MAX
        </button>
        <span className="text-ink tabular w-12 text-right">
          {maxSpeed.toFixed(2)}<span className="text-dim ml-0.5">m/s</span>
        </span>
      </div>

      <div className="grid grid-cols-3 gap-1 text-[9px] font-mono">
        <Mini k="VX" v={(bx * maxSpeed).toFixed(2)} />
        <Mini k="VY" v={(by * maxSpeed).toFixed(2)} />
        <Mini k="WZ" v={(bz * maxSpeed).toFixed(2)} />
      </div>
    </div>
  );

  if (bare) {
    return (
      <div className="p-2 relative h-full">
        <div className="flex items-center justify-between mb-1.5">
          <span className="font-display tracking-[0.24em] text-[10px] text-ink-2">MOVE</span>
          <span className="flex items-center gap-1.5">
            {settingsPopover}
            <span className={`font-display tracking-[0.18em] text-[9px] ${active ? "text-phos" : "text-dim"}`}>
              {active ? "ACTIVE" : "HOLD"}
            </span>
            <span className="text-[8.5px] tracking-[0.18em] text-dim">DRV/02</span>
          </span>
        </div>
        {body}
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-hd">
        <span>BASE MOVEMENT</span>
        <span className="flex items-center gap-2">
          {settingsPopover}
          <span className={`font-display tracking-[0.22em] text-[11px] ${active ? "text-phos" : "text-dim"}`}>
            {active ? "ACTIVE" : "HOLD"}
          </span>
          <span className="panel-idx">DRV/02</span>
        </span>
      </div>
      <div className="p-3">{body}</div>
    </div>
  );
}

function Mini({ k, v }: { k: string; v: string }) {
  return (
    <div className="border border-line bg-panel-2 px-1.5 py-0.5 flex items-baseline justify-between">
      <span className="text-[7.5px] tracking-[0.22em] text-dim">{k}</span>
      <span className="font-display text-[10px] tabular text-ink">{v}</span>
    </div>
  );
}
