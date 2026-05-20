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
| GET | `/c2/video/mjpeg?camera=front\|rear` | multipart/x-mixed-replace 5fps JPEG 스트림 (기본: front) |

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
`app/page.tsx` — 실시간 전술 콘솔 (2026-05-20 레이아웃 재정렬: 시각 위계 강화)

**레이아웃 섹션** (위→아래):
1. `StatusHeader` + `TelemetryStrip` — 상단 status bar
2. **HERO** (`grid xl:2`): `DualCameraView` + `MapTrack` — 가장 큰 시각 영역 (min-h 420px)
3. **CONTROLS** (`grid xl:3`): mission(PatrolControls + NpcSpawnButton) · movement(BaseMovementPanel + DualSenseStatus, 선택적 TeleopPad) · inspector(InspectorCameraPanel)
4. **ALERTS** (`grid lg:2`): `AlertsLog` + `AnimalAlertsLog` — 1-row 통합
5. `DiagnosticsStrip` + legacy 토글(BASE MOVEMENT / TELEOP) + `EventLog` (200px) — 푸터

| 컴포넌트 | props | 기능 |
|---------|-------|------|
| `StatusHeader` | wsOk, landmarks | 헤더(robot id · zone · WS 상태 · 시간) |
| `TelemetryStrip` | state, gps, odom, patrol | 1-row 텔레메트리(mode·gait·battery·waypoint·pose·gps) |
| `DualCameraView` | — | 전방+검사 MJPEG 2-panel (`/c2/video/mjpeg?camera=front\|inspect`) |
| `MapTrack` | track, cur, landmarks, intruders, patrolState, alertActive | 전술 지도 (Cube/Cone/DMZ 마커, fence 점선, intruder, alert overlay) |
| `PatrolControls` | patrolState | sortie/home/stop/resume/idle 미션 버튼 + 상태 표시 |
| `BaseMovementPanel` | — | 4족 8-방향 + WASD/QE/Space + 속도 슬라이더 (기본 표시) |
| `TeleopPad` | — | (legacy 토글) D-패드 + 속도, Nav2 비활성 시 보조 |
| `DualSenseStatus` | — | 게임패드 연결 상태 + 키매핑 표시 |
| `NpcSpawnButton` | — | NPC 소환 (fwd/drop/count + 버튼) |
| `InspectorCameraPanel` | — | 검사 카메라 pan/tilt/zoom/look_at REST |
| `AlertsLog` | liveEvents | person alert 누적 (최근 20, ACK 가능) |
| `AnimalAlertsLog` | liveEvents | animal alert 누적 (label·conf·bbox) |
| `EventLog` | events[] | 모든 C2Event 14줄 스크롤 |
| `DiagnosticsStrip` | armQ, legQ | 관절 스파크차트 |

**제거된 컴포넌트 (2026-05-20):** `VideoWall`(↔DualCameraView 중복), `ThreatBar`/`EngagementConsole`(사격 위협 — 실 데이터 무관), `ContactsPanel`(↔AlertsLog 중복), `ReadinessStrip`(↔TelemetryStrip 대체), `OpsLedger`(↔EventLog 중복).

### 디버그 페이지 (`/debug`)
`app/debug/page.tsx` — Lichtblick iframe 풀스크린 (Three.js SpotSurroundView 제거 — Lichtblick 만 사용)

`sub1_side/lichtblick/layout.json` 기본 layout (2026-05-20 강화, 이미지 #5 퀄리티):

| 패널 | 위치 | 토픽/구성 |
|---|---|---|
| `3D!go2` | 좌 50% | URDF Go2 + `/tf` + `/robot/odom` follow + `/cam/front/points` Z-turbo PointCloud |
| `Plot!joint_position` | 우상 33% | `/robot/leg_joint_states.position[0..11]` 12 라인 (FL/FR/RL/RR × hip/thigh/calf) |
| `Plot!foot_position` | 우중 33% | `/robot/leg_joint_states.effort[2,5,8,11]` 4 foot z 추정 |
| `Plot!cmd_vel` | 우하 상반 | `/robot/cmd_vel.linear.x` (red) + `.angular.z` (blue) |
| `Image!cam_front` | 우하 하반 | `/c2/front/compressed` |

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
| 3D!go2 | /tf, /robot/odom, **/cam/front/points** | go2.urdf(http://192.168.10.94:8766/go2_description/urdf/go2.urdf), follow base, 3m distance, PointCloud Z-turbo 컬러맵 "볼록렌즈/보울" |
| RawMessages!state | /robot/state | JSON 원문 표시 |
| Plot!leg | /robot/leg_joint_states.position[:] | Go2 12관절 시계열 |
| Image!cam_front | /c2/front/compressed | 전방 카메라 |
| Image!cam_rear | /c2/rear/compressed | 후방 카메라 |
| Image!depth | /cam/front/depth | 전방 깊이(32FC1 컬러맵) |

**레이아웃 트리:**
```
Row (55% / 45%)
├─ 3D!go2  (PointCloud 보울 + go2.urdf)
└─ Column
   ├─ RawMessages!state (25%)
   └─ Column
      ├─ Plot!leg (35%)
      └─ Column
         ├─ Image!cam_front (50%)
         └─ Column
            ├─ Image!cam_rear (50%)
            └─ Image!depth
```
> 보울 시각화: Isaac OG `CamPCL`(type=depth_pcl)가 `/cam/front/points`
> (PointCloud2) 발행 → foxglove_bridge → 3D!go2 패널이 Z 컬러맵 보울 렌더.
> depth_pcl 미지원 빌드 시 `/cam/front/depth`+`/cam/front/camera_info`
> 기반 Lichtblick 투영 fallback.
