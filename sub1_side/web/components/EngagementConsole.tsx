"use client";
import { useEffect, useState } from "react";
import { postJSON, ROBOT_ID } from "@/lib/api";

/** 교전 절차 순서대로 배치: 경고방송 → 무장 → 사격. 접촉 시 강조. */
const PRESETS = ["정지하라", "엎드려", "손들어", "경고: 접근금지"];

export default function EngagementConsole({
  contact,
  wsOk,
}: {
  contact: boolean;
  wsOk: boolean;
}) {
  const [key, setKey] = useState("");
  const [armed, setArmed] = useState(false);
  const [toast, setToast] = useState("");
  const [confirm, setConfirm] = useState(false);

  useEffect(() => setKey(localStorage.getItem("c2_api_key") || ""), []);
  const saveKey = (v: string) => {
    setKey(v);
    localStorage.setItem("c2_api_key", v);
  };
  const flash = (m: string) => {
    setToast(m);
    setTimeout(() => setToast(""), 3500);
  };

  const speak = async (preset: string) => {
    try {
      await postJSON(`/robots/${ROBOT_ID}/speaker`, { preset });
      flash(`확성기 송출: "${preset}"`);
    } catch (e: any) {
      flash(`실패: ${e.message}`);
    }
  };
  const fire = async () => {
    setConfirm(false);
    try {
      const r: any = await postJSON(`/robots/${ROBOT_ID}/fire`, {
        target: "manual",
        operator: "c2",
      });
      flash(r.hit ? `사격 — 명중 (${r.distance_m ?? "?"} m)` : "사격 — 빗나감");
    } catch (e: any) {
      flash(`사격 실패: ${e.message}`);
    }
  };

  return (
    <div
      className="panel"
      style={contact ? { borderColor: "var(--alert)" } : undefined}
    >
      <div className="panel-hd">
        <span>ENGAGEMENT · 교전 통제</span>
        <span className="flex items-center gap-2 text-[10px]">
          <span
            className="led"
            style={{ color: wsOk ? "var(--phos)" : "var(--alert)" }}
          />
          {wsOk ? "LINK UP" : "LINK DOWN"}
        </span>
      </div>

      <div className="p-3 grid grid-cols-1 lg:grid-cols-[1fr_auto] gap-3">
        <div>
          <div className="text-[11px] text-dim tracking-[0.2em] mb-1.5">
            1 · 확성기 경고
          </div>
          <div className="flex flex-wrap gap-2">
            {PRESETS.map((p) => (
              <button
                key={p}
                className="btn"
                onClick={() => speak(p)}
                style={
                  contact ? { borderColor: "var(--amber)" } : undefined
                }
              >
                {p}
              </button>
            ))}
          </div>
          <div className="mt-3 flex items-center gap-2">
            <input
              type="password"
              placeholder="X-API-KEY (변경계열 인증)"
              value={key}
              onChange={(e) => saveKey(e.target.value)}
              className="bg-[#0a1410] border border-line px-2 py-1.5 text-[12px] w-60 outline-none focus:border-phos"
            />
            <span className="text-[10px] text-dim">
              미설정 시 LAN 개발모드
            </span>
          </div>
        </div>

        <div className="flex flex-col gap-2 lg:border-l lg:border-line lg:pl-3 min-w-[180px]">
          <div className="text-[11px] text-dim tracking-[0.2em]">
            2 · 무장 &nbsp;3 · 사격
          </div>
          <label className="flex items-center gap-2 text-[11px] text-dim cursor-pointer select-none">
            <input
              type="checkbox"
              checked={armed}
              onChange={(e) => setArmed(e.target.checked)}
            />
            ARM 무장
          </label>
          <button
            disabled={!armed}
            onClick={() => setConfirm(true)}
            className="btn btn-fire disabled:opacity-25 disabled:cursor-not-allowed"
            style={
              contact && armed
                ? { boxShadow: "var(--alertglow)" }
                : undefined
            }
          >
            ▲ 사격 (FIRE)
          </button>
        </div>
      </div>

      {toast && (
        <div className="px-3 pb-2 text-[12px] text-phos tracking-wide">
          ▸ {toast}
        </div>
      )}

      {confirm && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/75">
          <div
            className="panel max-w-sm w-full p-5"
            style={{ borderColor: "var(--alert)" }}
          >
            <div className="font-display tracking-[0.2em] text-alert text-sm mb-2">
              사격 확인 / FIRE CONFIRM
            </div>
            <p className="text-[13px] text-ink mb-4">
              시뮬레이션 사격 실행 (raycast 히트판정 · FireEvent 기록).
              {contact
                ? " 활성 접촉 존재."
                : " 현재 탐지된 접촉 없음 — 재확인 요망."}
            </p>
            <div className="flex gap-2 justify-end">
              <button className="btn" onClick={() => setConfirm(false)}>
                취소
              </button>
              <button className="btn btn-fire" onClick={fire}>
                실행
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
