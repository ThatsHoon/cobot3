"use client";
import { useEffect, useState } from "react";
import { getJSON, postJSON, AlertPayload, ROBOT_ID } from "@/lib/api";

type AlertRow = {
  id?: number;
  ts: string;
  level: string;
  event: string;
  confidence: number;
  bbox_xyxy?: number[] | string;
  count: number;
  ack?: boolean;
};

// bbox_xyxy 중심 픽셀 추출 — string 또는 [x1,y1,x2,y2]
function bboxCenter(bbox: number[] | string | undefined): [number, number] | null {
  if (!bbox) return null;
  let arr: number[] | null = null;
  if (typeof bbox === "string") {
    try { arr = JSON.parse(bbox); } catch { return null; }
  } else if (Array.isArray(bbox)) {
    arr = bbox;
  }
  if (!arr || arr.length < 4) return null;
  return [(arr[0] + arr[2]) / 2, (arr[1] + arr[3]) / 2];
}

const MAX_ROWS = 20;

export default function AlertsLog({
  liveEvents,
}: {
  /** WS 로 들어온 신규 alert payload 들 — page.tsx 가 푸시한다. */
  liveEvents: { ts: string; data: AlertPayload }[];
}) {
  const [rows, setRows] = useState<AlertRow[]>([]);
  const [loading, setLoading] = useState(false);

  // 초기 로드 (최근 20건, only_open)
  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const data = await getJSON<AlertRow[]>(
          `/telemetry/alerts?rid=${ROBOT_ID}&limit=${MAX_ROWS}&only_open=true`);
        setRows(data);
      } catch {
        // DB 미가용 시 무시 — WS live 이벤트만 표시
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // WS 실시간 푸시 (앞쪽에 prepend, MAX_ROWS 유지)
  useEffect(() => {
    if (!liveEvents.length) return;
    const last = liveEvents[liveEvents.length - 1];
    setRows((prev) => [{
      ts: last.ts,
      level: last.data.level,
      event: last.data.event,
      confidence: last.data.confidence,
      bbox_xyxy: last.data.bbox_xyxy,
      count: last.data.count,
      ack: false,
    }, ...prev].slice(0, MAX_ROWS));
  }, [liveEvents]);

  const ack = async (id?: number, idx?: number) => {
    if (id == null) {
      // WS 만 온 행 (DB id 없음) — 로컬 상에서만 ack
      setRows((p) => p.map((r, i) => i === idx ? { ...r, ack: true } : r));
      return;
    }
    try {
      await postJSON(`/alerts/${id}/ack`, {});
      setRows((p) => p.map((r) => r.id === id ? { ...r, ack: true } : r));
    } catch {
      // ignore
    }
  };

  // [TRACK] — alert bbox 중심 픽셀로 inspect 카메라 회전 (HITL 사격 보조)
  const track = async (r: AlertRow) => {
    const c = bboxCenter(r.bbox_xyxy);
    if (!c) return;
    try {
      await postJSON(`/robots/${ROBOT_ID}/inspect`,
        { look_at_pixel: c, absolute: false });
    } catch (e) {
      console.error("inspect look_at_pixel", e);
    }
  };

  return (
    <div className="panel">
      <div className="panel-hd">
        <span>ALERTS</span>
        <span className="text-[11px] text-dim">
          {loading ? "loading…" : `${rows.filter(r => !r.ack).length} open`}
        </span>
      </div>
      <div className="px-2 py-1 max-h-48 overflow-auto text-[11px] font-mono">
        {rows.length === 0 && (
          <div className="text-dim px-2 py-1">알람 없음</div>
        )}
        {rows.map((r, i) => (
          <div key={r.id ?? i}
               className={`flex items-center justify-between gap-2 px-2 py-1 border-b border-line ` +
                          (r.ack ? "opacity-50" : "")}>
            <div className="flex-1 min-w-0">
              <div className="text-rose-400">
                {r.event} <span className="text-dim">conf={r.confidence.toFixed(2)}</span>
              </div>
              <div className="text-dim truncate">{new Date(r.ts).toLocaleTimeString()}</div>
            </div>
            <div className="flex gap-1">
              {bboxCenter(r.bbox_xyxy) && (
                <button onClick={() => track(r)}
                        className="text-[10px] px-2 py-0.5 rounded
                                   bg-rose-700 hover:bg-rose-600 text-white"
                        title="inspect 카메라를 bbox 중심으로 회전 (사격 보조)">
                  TRACK
                </button>
              )}
              {!r.ack && (
                <button onClick={() => ack(r.id, i)}
                        className="text-[10px] px-2 py-0.5 rounded bg-zinc-700 hover:bg-zinc-600">
                  ACK
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
