"use client";
import { ReactNode, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Settings, X } from "lucide-react";

/** 패널 헤더 ⚙ 트리거 + 중앙 오버레이 팝업.
 *  - position:fixed 이며 React Portal 로 body 에 직접 렌더링되어 화면 중앙 정렬 보장.
 *  - 백드롭 70% 투명도 적용.
 *  - dismiss: 외부 mousedown / Esc / X 버튼. */
export default function SettingsPopover({
  children,
  title,
  buttonTitle = "세부 설정",
  width = 360,
}: {
  children: ReactNode;
  title?: string;
  buttonTitle?: string;
  width?: number;
}) {
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    const onDown = (e: MouseEvent) => {
      if (!panelRef.current) return;
      if (e.target instanceof Node && panelRef.current.contains(e.target)) return;
      setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onDown, true);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onDown, true);
    };
  }, [open]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        title={buttonTitle}
        aria-label={buttonTitle}
        aria-expanded={open}
        data-active={open ? "true" : "false"}
        className="btn-icon !p-0 !w-6 !h-6 leading-none !border-amber-dim hover:!border-amber"
        style={{ color: "var(--amber)" }}>
        <Settings size={12} strokeWidth={1.6} />
      </button>
      {open && mounted && createPortal(
        <>
          {/* Backdrop overlay with 70% transparency */}
          <div
            style={{
              position: "fixed",
              inset: 0,
              zIndex: 9999,
              backgroundColor: "rgba(4, 8, 10, 0.7)",
              backdropFilter: "blur(1px)",
              transition: "opacity 0.2s",
            }}
            onClick={() => setOpen(false)}
          />
          <div
            ref={panelRef}
            className="panel"
            style={{
              position: "fixed",
              top: "50%",
              left: "50%",
              transform: "translate(-50%, -50%)",
              zIndex: 10000,
              width: `min(${width}px, 92vw)`,
              background:
                "linear-gradient(180deg, var(--panel), #060b09 92%)",
              boxShadow:
                "0 24px 60px -10px rgba(0,0,0,0.85), 0 0 0 1px var(--phos-faint), 0 0 30px -6px var(--phos-glow)",
            }}
            role="dialog"
            aria-modal="true">
            <div className="panel-hd">
              <span>{title ?? "SETTINGS"}</span>
              <span className="flex items-center gap-2">
                <span className="panel-idx">CFG</span>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="btn-icon !p-0 !w-6 !h-6 leading-none"
                  aria-label="close">
                  <X size={12} strokeWidth={1.8} />
                </button>
              </span>
            </div>
            <div className="p-4 text-[11px] font-mono">{children}</div>
          </div>
        </>,
        document.body
      )}
    </>
  );
}
