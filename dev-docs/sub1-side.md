# sub1_side — C2 PC (Command & Control)

## 파일 목록

| 파일/디렉토리 | 역할 |
|-------------|------|
| `server/app.py` | FastAPI 앱 (REST + WS /events + WebRTC offer + MJPEG) |
| `server/config.py` | 환경변수 중심 설정 (토픽명, API키, CORS, DB URL) |
| `server/ros_bridge.py` | ROS2 구독/발행 (rclpy, MultiThreadedExecutor) |
| `server/db_writer.py` | asyncpg 배치 적재 (1초 flush, copy_records_to_table) |
| `server/yolo_infer.py` | YOLOv8 추론 (선택, 없으면 graceful skip) |
| `server/webrtc_video.py` | aiortc VideoStreamTrack (5fps, H264) |
| `server/run.sh` | 서버 런처 (ROS2 소싱 + uvicorn :8000) |
| `web/app/page.tsx` | 전술 콘솔 메인 페이지 |
| `web/app/debug/page.tsx` | Lichtblick iframe + SpotSurroundView 3D 패널 |
| `web/components/*.tsx` | VideoWall, TeleopPad, MapTrack, EngagementConsole 등 |
| `web/lib/api.ts` | REST fetch 래퍼 + WS /events useEvents() 훅 |
| `lichtblick/layout.json` | Lichtblick 패널 레이아웃 (3D, 그래프, 카메라) |
| `run_foxglove_bridge.sh` | Foxglove Bridge 런처 (:8765) |

---

## FastAPI REST 엔드포인트

**Base URL:** `http://192.168.10.105:8000`

### 조회 (인증 불필요)
| Method | Path | Response |
|--------|------|----------|
| GET | `/healthz` | `{status, robot, ros, yolo}` |
| GET | `/robots/{rid}/state` | `{robot_id, state{mode,gait,battery,waypoint}, odom{x,y,z,yaw}, leg_q[]}` |
| GET | `/robots/{rid}/gps` | `{robot_id, gps{lat,lon,alt}}` |
| GET | `/telemetry/gps_track?limit=500` | `[{ts,lat,lon,alt}, ...]` |
| GET | `/telemetry/detections?limit=100` | `[{ts,class_name,confidence,bbox_*}, ...]` |
| GET | `/telemetry/fire_events?limit=50` | `[{ts,target_ref,hit,distance_m,operator}, ...]` |

### 명령 (X-API-Key 필요, 빈 키=dev 모드 허용)
| Method | Path | Request Body | Response |
|--------|------|-------------|----------|
| POST | `/robots/{rid}/goto` | `{x: float, y: float}` | `{ok, goal}` |
| POST | `/robots/{rid}/cmd_vel` | `{linear: float, angular: float}` | `{ok}` |
| POST | `/robots/{rid}/fire` | `{target: str, operator: str}` | `{ok, hit, distance_m}` |
| POST | `/robots/{rid}/speaker` | `{preset: str}` or `{pcm_b64, rate}` | `{ok}` |

### 영상
| Method | Path | 설명 |
|--------|------|------|
| POST | `/c2/webrtc/offer` | SDP 교환 (aiortc) |
| GET | `/c2/video/mjpeg` | multipart/x-mixed-replace 5fps JPEG 스트림 |

---

## WebSocket 이벤트 (`/events`)

클라이언트: `ws://host:8000/events` 연결 후 `ping` 텍스트 프레임으로 keepalive.

### 이벤트 타입

```typescript
// 로봇 상태 변경
{ type:"state", ts:ISO8601, data:{mode,gait,battery,waypoint,extra} }

// GPS 위치
{ type:"gps", ts:ISO8601, data:{lat,lon,alt} }

// ROS 로그 (level>=30 WARN)
{ type:"log", ts:ISO8601, level:number, name:string, msg:string }

// YOLO 탐지
{ type:"detection", ts:ISO8601, items:[{class_name,conf,bbox:[x,y,w,h]}] }

// 사격 이벤트
{ type:"fire", ts:ISO8601, target:string, hit:bool, distance_m:number|null, operator:string }

// 진단 (5초 주기)
{ type:"diag", ts:ISO8601, src:"ros_bridge"|"web_server",
  rx:{state,gps,video_front,video_rear,leg,rosout},
  publishers:{video_front,video_rear,state},
  hint:string|null }
```

---

## ros_bridge.py

**패턴:** `RosBridge` (asyncio 파사드) + `_C2Node` (rclpy Node)
- `RosBridge.start(loop, db, event_cb)`: MultiThreadedExecutor를 daemon thread에서 spin
- `RosBridge._emit(event)`: `loop.call_soon_threadsafe(event_cb, event)` — thread safe

### 구독 (downlink)
| 토픽 | 타입 | 콜백 | 동작 |
|------|------|------|------|
| `/robot/state` | String | `_on_state` | JSON 파싱 → latest["state"] + DB + emit |
| `/robot/gps` | NavSatFix | `_on_gps` | lat/lon/alt → latest["gps"] + DB + emit |
| `/robot/odom` | Odometry | `_on_odom` | quaternion→yaw → latest["odom"]{x,y,z,yaw} |
| `/robot/leg_joint_states` | JointState | `_on_leg` | positions → latest["leg_q"] + DB 10Hz |
| `/c2/front/compressed` | CompressedImage | `_on_video(…,"front")` | OpenCV decode + YOLO + frame cache |
| `/c2/rear/compressed` | CompressedImage | `_on_video(…,"rear")` | OpenCV decode + frame cache |
| `/rosout` | Log | `_on_rosout` | level>=30만 → DB + emit |

### 발행 (uplink)
| 메서드 | 토픽 | 타입 |
|--------|------|------|
| `pub_cmd_vel(lin, ang)` | `/robot/cmd_vel` | Twist |
| `publish_goal(x, y)` | `/robot/nav/goal` | PoseStamped |
| `send_speaker(payload)` | `/robot/speaker/audio` | String (JSON) |
| `fire()` | `/robot/weapon/fire` | Trigger (service) |

**헬스 타이머:** 5초마다 rx 카운터 + publisher 수 확인 → `diag` 이벤트 emit.

---

## db_writer.py

**패턴:** asyncio Queue → 1초 batch flush (`asyncpg.copy_records_to_table`)

```python
db.put("robot_state_log", (robot_id, ts, mode, gait, battery, waypoint, json.dumps(extra)))
db.put("gps_track", (robot_id, ts, lat, lon, alt, None, None))
db.put("joint_snapshots", (robot_id, ts, [], leg_q))
db.put("rosout_warn", (ts, level, name, msg))
db.put("intruder_detections", (robot_id, ts, class_name, conf, x, y, w, h, ...))
db.put("fire_events", (robot_id, ts, target_ref, hit, dist, operator))
```

**오버플로:** `C2_DB_QUEUE_MAX=20000` 초과 시 가장 오래된 항목 삭제 (backpressure).

---

## PostgreSQL 스키마 (`db/schema.sql`)

| 테이블 | 키 컬럼 | 용도 |
|--------|---------|------|
| `robot_state_log` | robot_id, ts, mode, gait, battery, waypoint, extra | 상태 이력 |
| `gps_track` | robot_id, ts, lat, lon, alt, x, y | GPS 궤적 |
| `fire_events` | robot_id, ts, target_ref, hit, distance_m, operator | 사격 로그 |
| `rosout_warn` | ts, level, node_name, msg | ROS 경고/오류 |
| `intruder_detections` | robot_id, ts, class_name, confidence, bbox_*, camera_frame | YOLO 탐지 |
| `joint_snapshots` | robot_id, ts, arm_q[], leg_q[] | 관절 스냅샷 (10Hz) |

---

## Next.js 컴포넌트

### 메인 페이지 (`/`)
`app/page.tsx` — 실시간 전술 콘솔

| 컴포넌트 | props | 기능 |
|---------|-------|------|
| `VideoWall` | detCount, contact | WebRTC(aiortc) + MJPEG 폴백, HUD 레티클 |
| `ThreatBar` | contact, lastTs | 위협 상태 표시 (8s TTL) |
| `ReadinessStrip` | state, wsOk | MODE/BATTERY/LINK/WAYPOINT/GPS 타일 |
| `MapTrack` | track[], cur | ±60m 캔버스 전술 지도, 더블클릭→goto |
| `ContactsPanel` | items[] | 탐지 목록 + 신뢰도 바 |
| `EngagementConsole` | contact, wsOk | 확성기→ARM→FIRE 워크플로 |
| `TeleopPad` | — | D-패드 + 속도 슬라이더, 100ms 주기 cmd_vel |
| `DiagnosticsStrip` | armQ, legQ | 관절 스파크차트 (접기/펼치기) |
| `OpsLedger` | items[] | 통합 이벤트 로그 (최대 300개) |

### 디버그 페이지 (`/debug`)
`app/debug/page.tsx` — 진단 도구

| 패널 | 구성 |
|------|------|
| `SpotSurroundView` | Three.js 3D: 로봇 바디, 전/후방 카메라 75° frustum, 2.5m 커버리지 링. odom yaw 200ms 폴링 |
| `iframe` (Lichtblick) | `http://host:8080/?ds=foxglove-websocket&ds.url=ws://host:8765` |

**SpotSurroundView 구현 세부:**
- `import type * as THREE from "three"` (타입 전용, SSR safe)
- `await import("three")` in useEffect (동적 로드, 번들 분리)
- 마우스 드래그 궤도 회전 (spherical coords), 스크롤 줌
- `yawRef.current` — 200ms 폴링으로 `/robots/gp0/state` odom.yaw 반영
- `robotGroup.rotation.y = yawRef.current` — 매 프레임 적용

### API 클라이언트 (`lib/api.ts`)
```typescript
API_BASE = process.env.NEXT_PUBLIC_C2_API  // default: http://localhost:8000
ROBOT_ID = process.env.NEXT_PUBLIC_GP_ROBOT // default: gp0

getJSON<T>(path)         // GET with no-store cache
postJSON<T>(path, body)  // POST with X-API-Key header
useEvents(handlers)      // WS /events 자동 재연결 + ping keepalive
```

---

## Lichtblick 레이아웃 (`lichtblick/layout.json`)

| 패널 | 토픽 | 설정 |
|------|------|------|
| 3D!spot | /tf, /robot/odom | URDF: http://192.168.10.94:8766/spot_isaac.urdf, follow base, 2m distance |
| RawMessages!state | /robot/state | JSON 원문 표시 |
| Plot!leg | /robot/leg_joint_states.position[:] | 12관절 시계열 |
| Image!cam_front | /c2/front/compressed | 전방 카메라 |
| Image!cam_rear | /c2/rear/compressed | 후방 카메라 |

**레이아웃 트리:**
```
Row (55% / 45%)
├─ 3D!spot
└─ Column
   ├─ RawMessages!state (28%)
   └─ Column
      ├─ Plot!leg (40%)
      └─ Column (60%)
         ├─ Image!cam_front (50%)
         └─ Image!cam_rear  (50%)
```
