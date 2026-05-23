"use client";
import { createContext, useContext, useState, useCallback, ReactNode } from "react";
import { postJSON, ROBOT_ID } from "@/lib/api";

/** 무기 안전장치 + 사격 흐름 전역 상태.
 *  - safety_off: 슬라이더가 완전히 오른쪽으로 당겨진 상태에서만 true
 *  - fireAt(payload): bbox 중심 또는 좌표 클릭으로 사격 시퀀스 호출.
 *    안전장치 ON 이면 toast 트리거, OFF 이면 confirm 모달.
 *  - 결과 모달 (Hit/Miss) 은 WeaponFireControl 이 weapon_state edge 로 띄움.
 */
export type FireRequest = {
  // inspect 카메라 픽셀 (look_at_pixel 변환), 또는 미지정 시 raycast 만
  look_at_pixel?: [number, number];
  // 화면에 표시할 라벨 (모달용)
  target_label: string;
  target_alert_id?: number;
};

type Ctx = {
  safetyOff: boolean;
  setSafetyOff: (v: boolean) => void;
  // 사격 요청 (안전장치 검사 + 확인 모달 trigger)
  requestFire: (req: FireRequest) => void;
  // pending confirm (UI 모달이 구독)
  pending: FireRequest | null;
  confirmFire: () => Promise<void>;
  cancelFire: () => void;
  // safety lock 시도 (toast 표시)
  toastMsg: string | null;
  clearToast: () => void;
};

const C = createContext<Ctx | null>(null);

export function WeaponSafetyProvider({ children }: { children: ReactNode }) {
  const [safetyOff, setSafetyOff] = useState(false);
  const [pending, setPending] = useState<FireRequest | null>(null);
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const [firing, setFiring] = useState(false);

  const requestFire = useCallback((req: FireRequest) => {
    if (!safetyOff) {
      setToastMsg("⚠ 안전장치 해제 요망 — 우측 SAFETY 바를 끝까지 드래그");
      setTimeout(() => setToastMsg(null), 3000);
      return;
    }
    setPending(req);
  }, [safetyOff]);

  const confirmFire = useCallback(async () => {
    if (!pending || firing) return;
    setFiring(true);
    try {
      // inspect 카메라 회전 (bbox/좌표 → look_at_pixel)
      if (pending.look_at_pixel) {
        await postJSON(`/robots/${ROBOT_ID}/inspect`,
          { look_at_pixel: pending.look_at_pixel, absolute: false });
        // 짐벌 회전 시간 (~250ms 대기)
        await new Promise(r => setTimeout(r, 280));
      }
      // 격발
      await postJSON(`/robots/${ROBOT_ID}/fire`, {
        target: pending.target_label,
        operator: "c2",
        target_alert_id: pending.target_alert_id,
      });
      // 2026-05-21: 자동 재잠금 제거 — 운용자가 슬라이더 좌측 드래그로
      // 직접 잠가야 함. 연속 사격 가능성·운용자 의도 우선.
    } catch (e: any) {
      setToastMsg(`발사 실패: ${e?.message || e}`);
      setTimeout(() => setToastMsg(null), 3000);
    } finally {
      setFiring(false);
      setPending(null);
    }
  }, [pending, firing]);

  const cancelFire = useCallback(() => setPending(null), []);
  const clearToast = useCallback(() => setToastMsg(null), []);

  return (
    <C.Provider value={{ safetyOff, setSafetyOff, requestFire,
                         pending, confirmFire, cancelFire,
                         toastMsg, clearToast }}>
      {children}
    </C.Provider>
  );
}

export function useWeaponSafety(): Ctx {
  const ctx = useContext(C);
  if (!ctx) throw new Error("useWeaponSafety must be inside WeaponSafetyProvider");
  return ctx;
}
