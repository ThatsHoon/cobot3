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
import logging
from datetime import datetime, timezone


def _now_iso():
    return datetime.now(timezone.utc).isoformat()

import asyncpg
import cv2
from aiortc import RTCPeerConnection, RTCSessionDescription
from fastapi import (Depends, FastAPI, Header, HTTPException, Request,
                     WebSocket, WebSocketDisconnect)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import config
from db_writer import DBWriter
from dualsense_worker import DualSenseService
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
dualsense = DualSenseService(
    ros,
    patrol_state_getter=lambda: ros.latest.get("patrol_state", {}))
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
    dualsense.start()
    log.info("C2 web_server up (robot=%s, domain=%s, yolo=%s, dualsense=%s)",
             config.ROBOT_ID, config.ROS_DOMAIN_ID, yolo.enabled,
             dualsense.status()["pygame_available"])
    yield
    dualsense.stop()
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
            "odom": ros.latest["odom"], "leg_q": ros.latest["leg_q"]}


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


@app.get("/telemetry/alerts")
async def alerts(rid: str = config.ROBOT_ID, limit: int = 100,
                 only_open: bool = False):
    sql = ("SELECT id, ts, level, event, confidence, bbox_xyxy, count, ack "
           "FROM alerts WHERE robot_id=$1")
    args = [rid]
    if only_open:
        sql += " AND ack = FALSE"
    sql += " ORDER BY ts DESC LIMIT $2"
    args.append(limit)
    rows = await _query(sql, *args)
    return [dict(r) for r in rows]


@app.get("/telemetry/patrol_state")
async def patrol_state(rid: str = config.ROBOT_ID, limit: int = 100):
    rows = await _query(
        "SELECT ts, mode, current_waypoint, pose_x, pose_y, pose_yaw "
        "FROM patrol_state_log WHERE robot_id=$1 ORDER BY ts DESC LIMIT $2",
        rid, limit)
    return [dict(r) for r in rows]


@app.get("/missions/state")
async def mission_state():
    """현재 patrol/intruder/landmarks 상태 즉시 조회 (WS 미수신 시 폴 백업)."""
    return {
        "patrol_state": ros.latest.get("patrol_state", {}),
        "intruders": ros.latest.get("intruders", []),
        "landmarks": ros.latest.get("landmarks", {}),
    }


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
async def mjpeg(camera: str = "rear"):
    # 2026-05-20: front 제거. rear/inspect/overhead 세 카메라 노출
    cam = camera if camera in ("rear", "inspect", "overhead") else "rear"
    async def gen():
        while True:
            f = ros.get_video_frame(cam)
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


@app.post("/robots/{rid}/cmd_vel", dependencies=[Depends(require_key)])
async def cmd_vel(rid: str, body: dict):
    """body: {"linear":vx, "linear_y":vy, "angular":wz} — /robot/cmd_vel Twist.

    quadruped 사양 (사용자 #4): vx=전후, vy=좌우(strafe), wz=제자리 회전.
    legacy body {"linear", "angular"} 도 호환.
    """
    vx = float(body.get("linear", body.get("linear_x", 0.0)))
    vy = float(body.get("linear_y", 0.0))
    wz = float(body.get("angular", body.get("angular_z", 0.0)))
    ros.pub_cmd_vel(vx, wz, vy=vy)
    return {"ok": True}


@app.post("/robots/{rid}/speaker", dependencies=[Depends(require_key)])
async def speaker(rid: str, body: dict):
    # body: {"preset": "엎드려"} 또는 {"pcm_b64": "...", "rate": 16000}
    ros.send_speaker(body)
    return {"ok": True}


# ---- DMZ Sentry M7 신규 엔드포인트 -------------------------------------
_MISSION_VALID = {"sortie", "home", "stop", "resume", "idle",
                  "start", "halt", "continue", "rtb", "standby"}


@app.post("/missions/command", dependencies=[Depends(require_key)])
async def mission_command(body: dict):
    """body: {"command": "sortie|home|stop|resume|idle"} → /mission_command."""
    cmd = str(body.get("command", "")).strip().lower()
    if cmd not in _MISSION_VALID:
        raise HTTPException(400, f"unknown mission command: {cmd!r}")
    ros.pub_mission(cmd)
    return {"ok": True, "command": cmd}


@app.post("/robots/{rid}/inspect", dependencies=[Depends(require_key)])
async def inspect_command(rid: str, body: dict):
    """검사 카메라 짐벌 명령 → /robot/inspect/command.

    body 키:
      pan, tilt (rad)
      zoom (focal multiplier) 또는 focal_length (mm)
      look_at: [x, y, z]
      absolute: bool (기본 True)
      reset: bool
    """
    payload = {k: body[k] for k in
               ("pan", "tilt", "zoom", "focal_length", "look_at",
                "absolute", "reset", "target_id")
               if k in body}
    if not payload:
        raise HTTPException(400, "empty inspect command")
    ros.pub_inspect_cmd(payload)
    return {"ok": True, "payload": payload}


@app.post("/robots/{rid}/spawn_npc", dependencies=[Depends(require_key)])
async def spawn_npc(rid: str, body: dict | None = None):
    """NPC(사람 형체) 소환 → /robot/npc/spawn (str_msgs/String JSON).
    Main 측 npc_relay 가 /tmp 파일에 dump, camera_publisher 가 폴링.

    body 키 (모두 옵션):
      forward_m (기본 20.0): Go2 전방 거리 m (음수=후방)
      z_offset  (기본 5.0):  base.z + 이만큼 위에서 떨어뜨림
      count     (기본 1):    좌우 0.6m 간격으로 다중 소환
    """
    body = body or {}
    payload = {
        "forward_m": float(body.get("forward_m", 20.0)),
        "z_offset": float(body.get("z_offset", 5.0)),
        "count": int(body.get("count", 1)),
    }
    ros.pub_npc_spawn(payload)
    return {"ok": True, "payload": payload}


@app.get("/c2/dualsense/status")
async def dualsense_status():
    """DualSense 게임패드 연결·키매핑·현재 speed_scale 상태."""
    return dualsense.status()


@app.get("/c2/sample")
async def sample_snapshot():
    """ros_bridge.latest dict snapshot — 다음 세션 foxglove 패널 설계용.

    카메라 frame 은 제외 (대용량 ndarray). state/odom/gps/patrol_state/
    landmarks/intruders/leg_q 등 JSON 직렬화 가능한 데이터만.
    """
    out = {}
    for k, v in ros.latest.items():
        if k.startswith("video_"):
            continue
        out[k] = v
    rx = None
    try:
        rx = dict(ros._node._rx) if (ros._node and hasattr(ros._node, "_rx")) else None
    except Exception:
        pass
    return {"latest": out, "rx": rx}


@app.post("/alerts/{alert_id}/ack", dependencies=[Depends(require_key)])
async def ack_alert(alert_id: int):
    """alert 행 ack=TRUE 마킹."""
    pool = db._pool
    if pool is None:
        raise HTTPException(503, "DB unavailable")
    async with pool.acquire() as c:
        r = await c.execute("UPDATE alerts SET ack=TRUE WHERE id=$1", alert_id)
    return {"ok": True, "result": r}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=config.HTTP_HOST, port=config.HTTP_PORT)
