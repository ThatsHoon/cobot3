# sub1_side — C2 PC (Command & Control)

## 파일 목록

| 파일/디렉토리 | 역할 |
|-------------|------|
| `server/app.py` | FastAPI 앱 (REST + WS /events + WebRTC offer + MJPEG + /c2/sample) |
| `server/config.py` | 환경변수 중심 설정 (토픽명, API키, CORS, DB URL, YOLO 정책) |
| `server/ros_bridge.py` | ROS2 구독/발행 (rclpy, MultiThreadedExecutor) — PAUSED 가드 |
| `server/db_writer.py` | asyncpg 배치 적재 (1초 flush, copy_records_to_table) |
| `server/yolo_infer.py` | YOLO 추론 (4-class: person/soldier/drone/animal). 안정 감지 트래커: soldier/person **5초/3프레임** → 정밀사격, drone 3초/2프레임 → 정밀사격. 30s 쿨다운. |
| `server/webrtc_video.py` | aiortc VideoStreamTrack (5fps, H264) |
| `server/nav2_patrol.py` | Nav2 patrol FSM (IDLE/PATROL/HOME/PAUSED), HOME=(212.8,890.53) GOAL=(287.59,1129.728), ±10m 사각 도착 |
| `server/cmd_vel_safety_filter.py` | Nav2 `/cmd_vel_nav2_raw` → `/robot/cmd_vel`, `MUTE_MODES={"PAUSED"}` |
| `server/nav2_bringup.launch.py` | Nav2 stack launch |
| `server/dualsense_worker.py` | **(신규)** PS5 DualSense 폴링(50Hz) → cmd_vel/inspect/mission |
| `server/foxglove_sdk_publisher.py` | **(신규)** rclpy + foxglove SDK :8767, ROS JSON → native SceneUpdate/ImageAnnotations/PoseInFrame/Log |
| `server/run.sh` | 서버 런처 (ROS2 소싱 + uvicorn :8000) |
| `web/app/page.tsx` | 전술 콘솔 메인 페이지 |
| `web/app/debug/page.tsx` | Lichtblick(8765+8767) iframe + Immersive + TopicHealth + RawJsonInspector |
| `web/components/*.tsx` | DualCameraView, ImmersiveCameraView, BaseMovementPanel, PatrolControls, DualSenseStatus, NpcSpawnButton, TripleCameraView, TopicHealthMonitor, RawJsonInspector 등 |
| `web/lib/api.ts` | `getApiBase()` 런타임 함수 (SSR 안전) + WS /events useEvents() 훅 |
| `lichtblick/layout.json` | 12 패널 + 4 userNodes (3D!go2 URDF, Plot×3, Image, SceneUpdate 변환) |
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
| POST | `/robots/{rid}/goto_tp` (2026-05-23) | `{tp_id: "TP_A".."TP_D"}` | `{ok, tp_id}` |
| POST | `/robots/{rid}/inspect` | `{pan?, tilt?, look_at?, look_at_pixel?, absolute?, reset?}` | `{ok}` |
| POST | `/robots/{rid}/spawn_animal` **(2026-05-27 신규)** | `{kind: "wolf"\|"deer"\|"boar"\|"drone", count?: int}` | `{ok, payload}` |
| GET | `/robots/{rid}/preview_route?tp_id=TP_*` (2026-05-23) | — | `{tp_id, route:[{x,y}…]}`. **2026-05-24: 로봇 현재 world 위치(StartingPoint+odom) 기반 경로 계산** |

### 영상
| Method | Path | 설명 |
|--------|------|------|
| POST | `/c2/webrtc/offer` | SDP 교환 (aiortc) |
| GET | `/c2/video/mjpeg?camera=<id>` | multipart/x-mixed-replace 5fps JPEG. camera ∈ `{rear, inspect, overhead, tp_a~d, tp_grid}`. **2026-05-24: `tp_grid` 가상 카메라 추가** — tp_a/b/c/d 1×4 가로 mosaic (1280×180), 단일 MJPEG 연결로 4 채널 표시 (HTTP/1.1 origin 6-connection 제한 회피). |

### 진단
| Method | Path | 설명 |
|--------|------|------|
| GET | `/c2/sample` | 1Hz 폴링용: `latest` 토픽 스냅샷 + rx 카운터 + publishers + env (디버그 페이지 TopicHealthMonitor·RawJsonInspector) |

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

### 구독 (downlink, 2026-05-21)
| 토픽 | 타입 | 콜백 | 동작 |
|------|------|------|------|
| `/robot/state` | String | `_on_state` | JSON 파싱 → latest["state"] + DB + emit |
| `/robot/gps` | NavSatFix | `_on_gps` | lat/lon/alt → latest["gps"] + DB + emit |
| `/robot/odom` | Odometry | `_on_odom` | quaternion→yaw → latest["odom"]{x,y,z,yaw} |
| `/robot/leg_joint_states` | JointState | `_on_leg` | positions → latest["leg_q"] + DB 10Hz |
| `/c2/rear/compressed` | CompressedImage | `_on_video(…,"rear")` | OpenCV decode + frame cache |
| `/c2/inspect/compressed` | CompressedImage | `_on_video(…,"inspect")` | OpenCV decode + **비동기 YOLO 추론** (ThreadPoolExecutor, 이전 추론 중이면 드롭) + frame cache |
| `/c2/overhead/compressed` | CompressedImage | `_on_video(…,"overhead")` | OpenCV decode + frame cache |
| `/c2/tp_{a,b,c,d}/compressed` | CompressedImage | `_on_video(…,"tp_*")` | YOLO + 3D map projection (config.YOLO_CAMERAS 가드) |
| `/c2/tp_{a,b,c,d}/depth_compressed` (2026-05-24) | CompressedImage (PNG 16UC1 320×180) | `_on_depth(…,"tp_*")` | PNG decode → meter float32 → bbox 중앙 거리 샘플 |
| `/patrol_state` | String JSON | `_on_patrol_state` | mode/waypoint/route/pose latest 갱신 — PAUSED 가드 트리거 |
| `/scene/landmarks` | String JSON | `_on_landmarks` | home/goal/fence latched 수신 |
| `/intruder_states` | String JSON | `_on_intruders` | NPC 좌표 |
| `/alerts`, `/animal_alerts` | String JSON | `_on_alert`/`_on_animal_alert` | WS emit + DB |
| `/rosout` | Log | `_on_rosout` | level>=30만 → DB + emit |

### 발행 (uplink)
| 메서드 | 토픽 | 타입 | 비고 |
|--------|------|------|------|
| `pub_cmd_vel(lin, ang, vy=0.0)` | `/robot/cmd_vel` | Twist | **PAUSED 가드** — patrol_state mode==PAUSED 시 무발행 |
| `publish_goal(x, y)` | `/robot/nav/goal` | PoseStamped | (Nav2 stack 단독 시 미사용) |
| `pub_inspect_cmd(payload)` | `/robot/inspect/command` | String JSON | pan/tilt/zoom/look_at |
| `pub_mission(cmd)` | `/mission_command` | String | sortie/home/stop/resume/idle/ab_patrol |
| `pub_soldier_spawn(payload)` | `/robot/npc/spawn` | String JSON | `{count}` → npc_relay → `/tmp/cobot3_npc_cmd.json` |
| `pub_animal_spawn(payload)` **(2026-05-27 신규)** | `/robot/npc/spawn` | String JSON | `{kind, count}` → npc_relay → `/tmp/cobot3_animal_cmd.json` |
| `send_speaker(payload)` | `/robot/speaker/audio` | String (JSON) | (미구현 소비자) |
| `fire()` | `/robot/weapon/fire` | Trigger (service) | (미구현 서버) |
| `_on_auto_fire_detected(label, cx, cy)` | — | — | YOLO 콜백 → `_auto_fire_async` asyncio 예약 |
| `_auto_fire_async(label, cx, cy)` | — | — | patrol stop → **bbox 중심 정밀조준(look_at_pixel)** → 사격 (soldier/person/drone 동일) |

**PAUSED race fix (2026-05-21):** `pub_cmd_vel` 진입 시 `latest["patrol_state"]
.mode == "PAUSED"` 확인 → 즉시 return. velocity_smoother·dualsense·web teleop
잔여 발행을 모두 ros_bridge 출구에서 차단.

**헬스 타이머:** 5초마다 rx 카운터 + publisher 수 확인 → `diag` 이벤트 emit.

**YOLO 자동사격 (2026-05-27/28 수정):** `start()` 에서 `yolo.set_auto_fire_cb(self._on_auto_fire_detected)` 주입. soldier/person/drone 모두 **bbox 중심 look_at_pixel 정밀조준 후 실사격** (구: soldier/person 공포탄 tilt 80° 제거). stable tracker 기준: soldier/person **5초/3프레임**, drone 3초/2프레임. `/events` WS 에 `{type:"auto_fire", label, bbox_cx, bbox_cy, success, fire_id, state}` 방송.

**비동기 YOLO (2026-05-27):** `_yolo_executor = ThreadPoolExecutor(max_workers=1)` + `_yolo_futures` dict. `_on_video("inspect")` 에서 이전 Future 미완료 시 현재 프레임 드롭(drop) → YOLO가 video delivery thread 를 블로킹하지 않음. 결과는 `_last_dets["inspect"]` 에 캐시, 다음 프레임 overlay에 사용.

**FRAME_TIMING (2026-05-27):** `FRAME_TIMING=1` 환경변수 시 `_on_video("inspect")` 에서 `[FT] RECV #N recv_gap=...ms net=...ms yolo_busy=...` 로그. `net_ms` = C2 수신시각 - Main header.stamp(wall-clock). 블랙아웃 원인 진단용.

---

## db_writer.py

**패턴:** asyncio Queue → 1초 batch flush (`asyncpg.copy_records_to_table`)

```python
db.put("robot_state_log", (robot_id, ts, mode, gait, battery, waypoint, json.dumps(extra)))
# 2026-05-24: gps_track 에 yaw 합류 (D4)
db.put("gps_track", (robot_id, ts, lat, lon, alt, x, y, yaw))
db.put("joint_snapshots", (robot_id, ts, [], leg_q))
db.put("rosout_warn", (ts, level, name, msg))
# 2026-05-24: intruder_detections + intruder_states_log → detection_events 통합
db.put("detection_events", (ts, robot_id, source, kind, class_name, conf,
                            json.dumps({"x":x,"y":y,"w":w,"h":h}),
                            world_x, world_y, world_z, beyond_fence, intruder_id))
db.put("fire_events", (robot_id, ts, target_ref, hit, dist, operator))
```

**오버플로:** `C2_DB_QUEUE_MAX=20000` 초과 시 가장 오래된 항목 삭제 (backpressure).

---

## PostgreSQL 스키마 (`db/schema.sql`)

| 테이블 | 키 컬럼 | 용도 |
|--------|---------|------|
| `robot_state_log` | robot_id, ts, mode, gait, battery, waypoint, extra | 상태 이력 |
| `gps_track` | robot_id, ts, lat, lon, alt, x, y, **yaw** (2026-05-24) | GPS 궤적 + odom yaw |
| `fire_events` | robot_id, ts, target_ref, hit, distance_m, operator | 사격 로그 |
| `rosout_warn` | ts, level, node_name, msg | ROS 경고/오류 |
| `detection_events` (2026-05-24) | ts, robot_id, source, **kind**='detection'\|'gt_state', class_name, confidence, bbox_pixel JSONB, world_xyz, beyond_fence, intruder_id, ack | YOLO + NPC ground-truth 통합 |
| `joint_snapshots` | robot_id, ts, arm_q[], leg_q[] | 관절 스냅샷 (10Hz) |
| `_deprecated_intruder_detections` / `_deprecated_intruder_states_log` | (구) | 1주 후 DROP 예정 — `detection_events` 로 이관됨 |

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
| `DualCameraView` | liveAlerts, tpDetections | inspect + rear + TP_A~D 표시. **2026-05-24: TP_A~D 가 단일 mosaic (`tp_grid` MJPEG, 1×4 가로 strip + quadrant overlay)** — HTTP/1.1 connection limit 회피. inspect 더블클릭=look_at_pixel (사격 조준). |
| `MapTrack` | track, cur, landmarks, intruders, patrolState, alertActive, routingState, previewRoute | 전술 지도. **2026-05-24**: overhead 카메라 배경 (SSR-safe useEffect), TP 거리 기반 자동 extent, `OVERHEAD_GROUND_HALF=262m` 기준 동적 CSS scale, w2o() world→odom 변환, 라우팅 amber 점선 + 미리보기 회색 점선. |
| `PatrolControls` | patrolState | sortie/home/stop/resume/idle 미션 버튼 + 상태 표시 |
| `BaseMovementPanel` | — | 4족 8-방향 + WASD/QE/Space + 속도 슬라이더 (기본 표시) |
| `TeleopPad` | — | (legacy 토글) D-패드 + 속도, Nav2 비활성 시 보조 |
| `DualSenseStatus` | — | 게임패드 연결 상태 + 키매핑 표시 |
| `NpcSpawnButton` | — | NPC 소환 패널 **(2026-05-27 확장)**: SOLDIER 버튼(count 1~5 슬라이더) + WOLF/DEER/BOAR/DRONE 버튼(2열 그리드, amber 톤). 각 버튼 → 해당 `/spawn_soldier` 또는 `/spawn_animal` REST 호출. |
| `InspectorCameraPanel` | — | 검사 카메라 pan/tilt/zoom/look_at REST. **2026-05-24: PAN_STEP=TILT_STEP=2°/click (이전 8°/5°)** — 정밀 조준. ▶ 클릭=카메라 오른쪽 (백엔드 `_qz(-pan)` 부호 컨벤션과 정합). |
| `TacticalPointsPanel` (2026-05-23) | routingState, onPreviewChange | TP_A~D 선택→`previewRoute`(미리보기) / "이동" → `goto_tp` 발행. 라우팅 진행률 표시 |
| `AlertsLog` | liveEvents | person alert 누적 (최근 20, ACK 가능) |
| `AnimalAlertsLog` | liveEvents | animal alert 누적 (label·conf·bbox) |
| `EventLog` | events[] | 모든 C2Event 14줄 스크롤 |
| `DiagnosticsStrip` | legQ | **2026-05-24 재작성**: Go2 12-DOF 4-leg × 3-joint 그리드 (FL/FR/RL/RR × hip/thigh/calf), 관절명+bar(±π/2 비율)+rad값. 구 M0609 arm + ANYmal leg 표시 제거. armQ prop 제거. |

**제거된 컴포넌트 (2026-05-20):** `VideoWall`(↔DualCameraView 중복), `ThreatBar`/`EngagementConsole`(사격 위협 — 실 데이터 무관), `ContactsPanel`(↔AlertsLog 중복), `ReadinessStrip`(↔TelemetryStrip 대체), `OpsLedger`(↔EventLog 중복).

### 디버그 페이지 (`/debug`, 2026-05-21 12-col grid)

`app/debug/page.tsx` — 12-column grid, 12-panel:

| 그리드 | 컴포넌트 | 토픽/구성 |
|---|---|---|
| row1 좌 (8col) | Lichtblick iframe | `http://host:8080/?ds=foxglove-websocket&ds.url=ws://host:8765` |
| row1 우 (4col) | `ImmersiveCameraView` | Three.js SphereGeometry inside-out 에 rear/inspect VideoTexture 섹터 매핑 + Go2 URDF 메시. **2026-05-24**: legQ prop 추가 (Go2Urdf 에서 12-DOF `setJointValue` 매 프레임 lerp 동기), sphere phi 정렬 `+π/2`→`+π` (+X=robot forward). 데이터: REST `/robots/{rid}/state` 5Hz 폴링으로 odom.yaw + leg_q[12] 동기. URDF URL: `http://192.168.10.94:8780/scene/go2_description/urdf/go2.urdf` (run_urdf_server.sh :8780). **2026-05-28**: URDF 포트 8766→8780 수정(렌더링 불가 버그), `PCFSoftShadowMap`→`PCFShadowMap` (Three.js r175+). |
| row2 좌 (5col) | `TopicHealthMonitor` | `/c2/sample` 1Hz 폴링 — rx 카운터·publishers·env·hint |
| row2 중 (4col) | `RawJsonInspector` | latest 토픽 JSON 원문 |
| row2 우 (3col) | `DualSenseStatus` | 게임패드 연결·키맵 |
| row3 (12col) | `DiagnosticsStrip` | 12-DOF leg joint 스파크차트 |
| row4 (12col) | `EventLog` | 모든 C2Event 14줄 스크롤 |

> Lichtblick 은 두 데이터 소스 동시 연결 가능 (`ws://host:8765` foxglove_bridge,
> `ws://host:8767` foxglove SDK native). 표준 단일 소스 미지원 시 별도 탭/창.

### Lichtblick `layout.json` 기본 layout (2026-05-21)

12 패널 + 4 userNodes — String JSON → SceneUpdate 변환:

| 패널 | 토픽 / userNode | 설명 |
|---|---|---|
| `3D!go2` | go2-urdf(http://192.168.10.94:8780/go2_description/urdf/go2.urdf), `/tf`, `/robot/odom`, `/cam/rear/points`, `/sdk/intruder_markers`, `/sdk/landmark_markers`, `/sdk/patrol_goal_pose` | follow `base` link |
| `Image!inspect` + camera_info frustum | `/c2/inspect/compressed` + `/cam/inspect/camera_info` | YOLO 입력 카메라 |
| `Image!rear`  + camera_info frustum | `/c2/rear/compressed` + `/cam/rear/camera_info` | |
| `Image!overhead` | `/c2/overhead/compressed` + `/cam/overhead/camera_info` | |
| `Plot!leg_position` | `/robot/leg_joint_states.position[0..11]` | 12 라인 |
| `Plot!leg_velocity` | `.velocity[0..11]` | 12 라인 |
| `Plot!cmd_vel` | `/robot/cmd_vel.linear.{x,y}` + `.angular.z` | 3 라인 |
| `Plot!patrol_mode` | userNode `patrol_mode_extractor` → mode enum 시계열 | |
| `Plot!battery` | userNode `battery_extractor` → /robot/state battery | |
| `Log!alerts` | `/sdk/alert_log` (foxglove SDK Log) | |
| `RawMessages!patrol` | `/patrol_state` | mode/waypoint/route JSON 원문 |
| `RawMessages!landmarks` | `/scene/landmarks` | home/goal/fence |

**userNodes (4개)**:
- `patrol_mode_extractor` — `/patrol_state.mode` → numeric enum
- `battery_extractor` — `/robot/state` JSON 파싱 → battery float
- `intruders_to_scene` — `/intruder_states` JSON → SceneUpdate (fallback;
  SDK 미가동 시)
- `landmarks_to_scene` — `/scene/landmarks` JSON → SceneUpdate (fallback)

> SDK 사이드카(8767)가 가동되어 있으면 `/sdk/*` native 채널이 우선 노출 —
> userNodes 는 SDK 미설치 fallback 으로 유지.

### API 클라이언트 (`lib/api.ts`, 2026-05-19 SSR fix)
```typescript
// 모듈 레벨 상수로 두면 Next.js SSR 시점에 "localhost" 로 굳어버림 → 런타임 함수.
export function getApiBase(): string {
  if (process.env.NEXT_PUBLIC_C2_API) return process.env.NEXT_PUBLIC_C2_API;
  if (typeof window === "undefined") return "";   // SSR guard
  return `http://${window.location.hostname}:8000`;
}
export const LICHTBLICK_URL = process.env.NEXT_PUBLIC_LICHTBLICK_URL
  || "http://localhost:8080";
export const ROBOT_ID = process.env.NEXT_PUBLIC_GP_ROBOT || "gp0";

getJSON<T>(path)         // GET with no-store cache
postJSON<T>(path, body)  // POST with X-API-Key header
useEvents(handlers)      // WS /events 자동 재연결 + ping keepalive
```

---

## Foxglove SDK Python 사이드카 (`server/foxglove_sdk_publisher.py`, 2026-05-21 신규)

rclpy 노드와 foxglove SDK 가 같은 프로세스에서 동거. `foxglove.start_server
(host="0.0.0.0", port=8767)` 자체 WS 서버 가동. ROS String JSON 토픽 5종을
native schema 채널로 변환 발행 → Lichtblick 가 ws://host:8767 별도 source
로 추가 연결.

| SDK 채널 | well-known schema | 입력 ROS 토픽 |
|---|---|---|
| `/sdk/intruder_markers` | `foxglove.SceneUpdate` (SpherePrimitive × intruder, level=ALERT 빨강) | `/intruder_states` |
| `/sdk/landmark_markers` | `foxglove.SceneUpdate` (home/goal CubePrimitive + arrive_box CylinderPrimitive + TextPrimitive) | `/scene/landmarks` |
| `/sdk/patrol_goal_pose` | `foxglove.PoseInFrame` | `/patrol_state.waypoint` |
| `/sdk/inspect_annotations` | `foxglove.ImageAnnotations` (LINE_STRIP × bbox) | `/detections_text` |
| `/sdk/alert_log` | `foxglove.Log` (level=WARNING) | `/alerts` |

이전 in-app userNodes 변환 방식은 fallback 으로 layout.json 안에 보존.

## DualSense worker (`server/dualsense_worker.py`, 2026-05-21 신규)

PS5 컨트롤러 폴링(pygame.joystick, 30Hz). 매핑:

| 입력 | 기능 |
|---|---|
| L-stick X/Y | inspect 카메라 pan/tilt (±70° clamp). **2026-05-24: 속도 `INSPECT_RATE_RAD_PER_S=2°/s` (이전 45°/s, 정밀 조준)** |
| L2 / R2 | inspect 카메라 zoom in / out |
| D-pad ↑/↓/←/→ | base movement 전/후/좌/우 strafe |
| R-stick X | yaw (좌우 회전) |
| × (cross) | stop_toggle (정지/재개) |
| △ (triangle) | sortie (PATROL 시작) |
| ○ (circle) | home (HOME 복귀) |

내부적으로 ros_bridge.pub_cmd_vel / pub_inspect_cmd / pub_mission 호출.
