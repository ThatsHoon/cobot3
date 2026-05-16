"""C2 web_server — FastAPI 진입점 (설계 §9.5 / §12 / D7).

레이어:
  ros_bridge   : ROS 2 다운/업링크 (별도 스레드)
  db_writer    : 영상 외 전 데이터 → 로컬 Postgres (asyncpg COPY)
  yolo_infer   : 서버측 YOLO (선택)
  webrtc       : 영상 = WebRTC(aiortc), MJPEG 폴백
  WS /events   : telemetry·log·detection·fire 멀티캐스트
"""
import asyncio
import contextlib
import json
import logging
from datetime import datetime, timezone


def _now_iso():
    return datetime.now(timezone.utc).isoformat()

import asyncpg
import cv2
import numpy as np
from aiortc import RTCPeerConnection, RTCSessionDescription
from fastapi import (Depends, FastAPI, Header, HTTPException, Request,
                     WebSocket, WebSocketDisconnect)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import config
from db_writer import DBWriter
from ros_bridge import RosBridge
from webrtc_video import BridgeVideoTrack
from yolo_infer import YoloInfer

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("c2.app")

# ---- 공유 상태 -----------------------------------------------------------
db = DBWriter()
ros = RosBridge()
yolo = YoloInfer()
_ws_clients: set[WebSocket] = set()
_pcs: set[RTCPeerConnection] = set()
_main_loop: asyncio.AbstractEventLoop | None = None


def _broadcast(event: dict):
    """ros_bridge 스레드 → asyncio. 끊긴 클라이언트는 정리."""
    dead = []
    for ws in list(_ws_clients):
        try:
            asyncio.create_task(ws.send_json(event))
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.discard(ws)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    global _main_loop
    _main_loop = asyncio.get_running_loop()
    await db.start()
    ros.start(_main_loop, db, _broadcast, yolo if yolo.enabled else None)
    log.info("C2 web_server up (robot=%s, domain=%s, yolo=%s)",
             config.ROBOT_ID, config.ROS_DOMAIN_ID, yolo.enabled)
    yield
    ros.stop()
    await db.stop()
    for pc in list(_pcs):
        await pc.close()


app = FastAPI(title="GP C2 web_server", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=config.WEB_ORIGINS,
    allow_methods=["*"], allow_headers=["*"])


# ---- 인증 (변경계열, 설계 §4.3) ------------------------------------------
def require_key(x_api_key: str = Header(default="")):
    if not config.API_KEY:          # 키 미설정 = 개발모드(LAN 한정)
        return
    if x_api_key != config.API_KEY:
        raise HTTPException(401, "invalid X-API-Key")


# ---- 조회 (인증 불요) ----------------------------------------------------
@app.get("/healthz")
async def healthz():
    return {"status": "ok", "robot": config.ROBOT_ID,
            "ros": ros.__class__.__name__, "yolo": yolo.enabled}


@app.get("/robots/{rid}/state")
async def get_state(rid: str):
    return {"robot_id": rid, "state": ros.latest["state"],
            "odom": ros.latest["odom"],
            "arm_q": ros.latest["arm_q"], "leg_q": ros.latest["leg_q"]}


@app.get("/robots/{rid}/gps")
async def get_gps(rid: str):
    return {"robot_id": rid, "gps": ros.latest["gps"]}


@app.get("/telemetry/gps_track")
async def gps_track(rid: str = config.ROBOT_ID, limit: int = 500):
    rows = await _query(
        "SELECT ts, lat, lon, alt FROM gps_track WHERE robot_id=$1 "
        "ORDER BY ts DESC LIMIT $2", rid, limit)
    return [dict(r) for r in rows]


@app.get("/telemetry/detections")
async def detections(rid: str = config.ROBOT_ID, limit: int = 100):
    rows = await _query(
        "SELECT ts, class_name, confidence, bbox_x, bbox_y, bbox_w, bbox_h "
        "FROM intruder_detections WHERE robot_id=$1 ORDER BY ts DESC LIMIT $2",
        rid, limit)
    return [dict(r) for r in rows]


@app.get("/telemetry/fire_events")
async def fire_events(rid: str = config.ROBOT_ID, limit: int = 50):
    rows = await _query(
        "SELECT ts, target_ref, hit, distance_m, operator FROM fire_events "
        "WHERE robot_id=$1 ORDER BY ts DESC LIMIT $2", rid, limit)
    return [dict(r) for r in rows]


async def _query(sql: str, *args):
    pool = db._pool
    if pool is None:
        return []
    async with pool.acquire() as c:
        return await c.fetch(sql, *args)


# ---- WebSocket /events ---------------------------------------------------
@app.websocket("/events")
async def events(ws: WebSocket):
    await ws.accept()
    _ws_clients.add(ws)
    try:
        while True:
            await ws.receive_text()      # keep-alive (클라가 ping)
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(ws)


# ---- 영상: WebRTC (설계 D7) ---------------------------------------------
@app.post("/c2/webrtc/offer")
async def webrtc_offer(req: Request):
    body = await req.json()
    offer = RTCSessionDescription(sdp=body["sdp"], type=body["type"])
    pc = RTCPeerConnection()
    _pcs.add(pc)

    @pc.on("connectionstatechange")
    async def _on_state():
        if pc.connectionState in ("failed", "closed"):
            await pc.close()
            _pcs.discard(pc)

    pc.addTrack(BridgeVideoTrack(ros))
    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}


# ---- 영상: MJPEG 폴백 (저대역) ------------------------------------------
@app.get("/c2/video/mjpeg")
async def mjpeg():
    async def gen():
        while True:
            f = ros.get_video_frame()
            if f is not None:
                ok, jpg = cv2.imencode(".jpg", f,
                                       [cv2.IMWRITE_JPEG_QUALITY, 50])
                if ok:
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                           + jpg.tobytes() + b"\r\n")
            await asyncio.sleep(0.2)     # 5fps
    return StreamingResponse(
        gen(), media_type="multipart/x-mixed-replace; boundary=frame")


# ---- 업링크 (변경계열, X-API-Key) ---------------------------------------
@app.post("/robots/{rid}/goto", dependencies=[Depends(require_key)])
async def goto(rid: str, body: dict):
    ros.publish_goal(float(body["x"]), float(body["y"]))
    return {"ok": True, "goal": {"x": body["x"], "y": body["y"]}}


@app.post("/robots/{rid}/fire", dependencies=[Depends(require_key)])
async def fire(rid: str, body: dict):
    res = ros.fire(target_ref=str(body.get("target", "manual")),
                   operator=str(body.get("operator", "c2")))
    return {"ok": True, **res}


@app.post("/robots/{rid}/speaker", dependencies=[Depends(require_key)])
async def speaker(rid: str, body: dict):
    # body: {"preset": "엎드려"} 또는 {"pcm_b64": "...", "rate": 16000}
    ros.send_speaker(body)
    return {"ok": True}


# ── D-확장 직결 ingest (임시 같은-PC: ROS2 우회, Isaac in-process → 여기로) ──
# 기존 UI 무변경: ros.latest / 비디오 프레임 / WS 이벤트 / DB 를 ROS 콜백과
# 동일하게 채운다. rclpy 불필요(이 경로는 ros_bridge 와 독립).
import time as _t
_ingest = {"frame": 0, "tele": 0, "last": _t.time()}


@app.post("/ingest/frame")
async def ingest_frame(req: Request, w: int = 640, h: int = 360,
                       enc: str = "rgb"):
    """Isaac in-process 캡처 프레임(raw HxWx3 uint8). WebRTC/MJPEG 가 그대로 소비."""
    raw = await req.body()
    arr = np.frombuffer(raw, dtype=np.uint8)
    if arr.size < w * h * 3:
        raise HTTPException(400, f"frame size {arr.size} < {w*h*3}")
    img = arr[: w * h * 3].reshape(h, w, 3)
    bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR) if enc == "rgb" else img.copy()
    # 서버측 YOLO(선택) → bbox 오버레이 + 탐지 emit/기록
    if yolo.enabled:
        for d in yolo.infer(bgr):
            x, y, ww, hh = d["bbox"]
            cv2.rectangle(bgr, (int(x), int(y)),
                          (int(x + ww), int(y + hh)), (0, 0, 255), 2)
            cv2.putText(bgr, f'{d["class_name"]} {d["conf"]:.2f}',
                        (int(x), int(y) - 5), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (0, 0, 255), 1)
            db.put("intruder_detections",
                   (config.ROBOT_ID, _now_iso(), d["class_name"], d["conf"],
                    x, y, ww, hh, None, None, None, None, "realsense"))
            _broadcast({"type": "detection", "ts": _now_iso(), "items": [d]})
    ros._set_video_frame(bgr)
    ros.ingest_ts = _t.time()
    _ingest["frame"] += 1
    return {"ok": True, "n": _ingest["frame"]}


@app.post("/ingest/telemetry")
async def ingest_telemetry(body: dict):
    """Isaac in-process 텔레메트리(joint/gps/odom/state/logs) — ROS 콜백과 동일 처리."""
    ts = body.get("ts") or _now_iso()
    rid = config.ROBOT_ID
    arm_q = body.get("arm_q") or []
    leg_q = body.get("leg_q") or []
    gps = body.get("gps") or {}
    odom = body.get("odom") or {}
    st = body.get("state") or {}

    if arm_q:
        ros.latest["arm_q"] = arm_q
    if leg_q:
        ros.latest["leg_q"] = leg_q
    if odom:
        ros.latest["odom"] = odom
    if gps:
        ros.latest["gps"] = gps
        db.put("gps_track", (rid, ts, gps.get("lat"), gps.get("lon"),
                             float(gps.get("alt") or 0.0),
                             odom.get("x"), odom.get("y")))
        _broadcast({"type": "gps", "ts": ts, "data": gps})
    if st:
        ros.latest["state"] = st
        db.put("robot_state_log", (rid, ts, st.get("mode"), st.get("gait"),
                                   st.get("battery"), st.get("waypoint"),
                                   json.dumps(st.get("extra", {}))))
        _broadcast({"type": "state", "ts": ts, "data": {**st, "odom": odom}})
    if arm_q or leg_q:
        db.put("joint_snapshots", (rid, ts, arm_q, leg_q))
    for lg in body.get("logs", []):
        lvl = int(lg.get("level", 30))
        if lvl >= config.ROSOUT_WARN_LEVEL:
            db.put("rosout_warn", (ts, lvl, lg.get("name", "isaac"),
                                   lg.get("msg", "")))
            _broadcast({"type": "log", "ts": ts, "level": lvl,
                        "name": lg.get("name", "isaac"),
                        "msg": lg.get("msg", "")})
    ros.ingest_ts = _t.time()
    _ingest["tele"] += 1
    return {"ok": True, "n": _ingest["tele"]}


@app.get("/ingest/stats")
async def ingest_stats():
    return {"frame": _ingest["frame"], "tele": _ingest["tele"]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=config.HTTP_HOST, port=config.HTTP_PORT)
