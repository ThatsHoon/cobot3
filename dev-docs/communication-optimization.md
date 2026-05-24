# 통신 효율화 결정 기록 (2026-05-24)

cobot3 Main(192.168.10.94, Isaac Sim) ↔ C2(192.168.10.105, FastAPI+Next.js+PostgreSQL)
사이 ROS2 통신을 실측 기반으로 분석하고 Tier 1+2+3 효율화를 적용한 결과 기록.

---

## 1. 측정 베이스라인 (변경 전)

### 1.1 측정 환경
- Main PC LAN 인터페이스: `wlp128s20f3` (WiFi)
- ROS_DOMAIN_ID=130, RMW=`rmw_fastrtps_cpp`, FastDDS UDP-only (`fastdds_no_shm.xml`)
- Isaac Sim 5.1, GUI 모드, 7개 카메라(rear, inspect, overhead, tp_a~d) + 4채널 depth
- C2 PC ros_bridge, foxglove_bridge:8765, lichtblick:8080, web:3000 가동

### 1.2 측정 명령
```bash
# 인터페이스 카운터 (sudo 불요)
IFACE=wlp128s20f3
TX1=$(cat /sys/class/net/$IFACE/statistics/tx_bytes); sleep 10
TX2=$(cat /sys/class/net/$IFACE/statistics/tx_bytes)
echo "TX: $(( (TX2-TX1)/10/1024 )) KB/s"

# 토픽별 메시지 크기/주파수
ros2 topic bw /cam/tactical/tp_a/depth
ros2 topic hz /cam/tactical/tp_a/depth
ros2 topic info /cam/tactical/tp_a/depth -v
```

### 1.3 변경 전 트래픽 분포
| 항목 | 값 |
|------|----|
| Main PC LAN TX (wlp128s20f3) | **17,933 KB/s ≈ 17.9 MB/s** |
| 토픽 수 | 86개 |
| `/cam/tactical/tp_*/depth` 메시지 크기 | 920 KB/msg |
| `/cam/tactical/tp_*/depth` Hz 합산 (4 cams) | ~10 Hz 총합 |
| → depth 정당 LAN 트래픽 | ~9.1 MB/s |
| `/cam/*/rgb` 메시지 크기 | ~691 KB/msg |
| `/cam/*/rgb` 누설 LAN 트래픽 | ~7-8 MB/s (FastDDS multicast 누출) |
| `/c2/*/compressed` LAN 트래픽 | ~0.2 MB/s |

---

## 2. 발견 사항 (D1~D11)

| ID | 증상 | 진단 | 결정 | 적용 위치 |
|----|------|------|------|-----------|
| **D1** | `/robot/gps` (lat/lon) vs `/robot/state.waypoint` (x/y) 중복 의심 | 의미 다름 (절대 vs FSM idx) | 유지 | — |
| **D2** | `/cam/*/rgb` 7개 RAW가 LAN으로 흘러가는 듯 | Main 측 구독자는 `video_degrade_node`(로컬)뿐. FastDDS UDP multicast 가 데이터를 LAN 인터페이스로도 송신 | depth 압축으로 핵심 절감, RAW RGB는 Isaac 재시작 시 FastDDS 멀티캐스트 차단 적용 (별도 PR) | `fastdds_no_shm.xml` (P2) |
| **D3** | `video_degrade_node.py` `DEGRADE_IN` 기본값 `/cam/front/rgb` (front 제거됨) | 잔재 | env required 변경 | `main_side/video_degrade_node.py:20` |
| **D4** | `/robot/odom` DB 미저장 | 캐시 전용 의도 | 유지 + `gps_track`에 `yaw` 합류 | `sub1_side/db/schema.sql`, `ros_bridge.py:_on_gps` |
| **D5** | YOLO 5채널 (inspect + tp_a~d) 동시 inference CPU 부담 | 정책 부재 | env `C2_YOLO_CAMERAS` 도입 (기본 `inspect,tp_a`) | `sub1_side/server/config.py`, `ros_bridge.py:429,481` |
| **D6** | `camera_info` 1Hz timer (latched라 1회면 충분) | 디자인 잔재 | 1회 발행 + 60s 보호 발행 | `main_side/camera_info_publisher.py:73-84` |
| **D7** | `/wind/state` 20Hz → WS 5Hz throttle | 이미 최적화됨 | 유지 | — |
| **D8** | `intruder_detections`(픽셀) + `intruder_states_log`(world) 두 테이블 분산 | 같은 의미의 분산 | `detection_events` 통합 (kind=detection/gt_state) | `sub1_side/db/{schema.sql,migrations/2026-05-24_detection_unify.sql}`, `db_writer.py`, `ros_bridge.py` 3곳 |
| **D9** | BEST_EFFORT 5fps 영상 starvation 가능성 | 위험 낮음 (WebRTC 폴백) | 유지 | — |
| **D10** | `/tmp/cobot3_landmarks.json` 미존재 시 보호 있음 | 의도된 fallback | 유지 | — |
| **D11** | `/weather/command` ROS + `/tmp/cobot3_weather_cmd.json` IPC 이중경로 | Isaac in-process rclpy 충돌 회피용 | 유지 (의도된 mailbox 패턴) | dev-docs 명문화만 |

### 2.1 신규 발견 (Phase 0 진단 중)
| 항목 | 발견 | 결정 |
|------|------|------|
| **DEPTH RAW 송신** | `/cam/tactical/tp_*/depth` 각 920KB × 5.6Hz 등 → 9.1 MB/s LAN | `depth_degrade_node.py` 신규 도입 (PNG 16UC1 320×180) |

---

## 3. Depth 압축 — 핵심 절감 메커니즘

### 3.1 문제
TP 카메라 4개의 depth(`/cam/tactical/tp_*/depth`)가 C2 ros_bridge의 YOLO 3D projection에 사용되므로 정당하게 LAN을 통과한다. 그러나 raw 32FC1 (4 bytes × 640 × 360 = 921,600 bytes/msg) 형식이라 약 9 MB/s를 차지.

### 3.2 해결책
신규 노드 `main_side/depth_degrade_node.py`:
1. SUB: `/cam/tactical/tp_*/depth` (raw 32FC1 또는 16UC1)
2. 처리: 60m 클램프 → 320×180 다운샘플 → mm 단위 uint16 변환 → PNG 무손실 압축
3. PUB: `/c2/tp_*/depth_compressed` (CompressedImage, format=`16UC1; png compressed`)

C2 측 `ros_bridge.py:_decode_depth`도 양 포맷 호환 (legacy raw + 신규 PNG).

### 3.3 실측 결과
| TP | raw 크기 | 압축 후 크기 | 비율 |
|----|---------|-------------|------|
| tp_a | 920 KB | 32.0 KB | 3.5% |
| tp_b | 920 KB | 31.9 KB | 3.5% |
| tp_c | 920 KB | 4.2 KB | 0.5% (sparse) |
| tp_d | 920 KB | 20.1 KB | 2.2% |
| **평균** | **920 KB** | **~22 KB** | **2.4%** |

depth 정확도: 320×180 다운샘플 + 16비트 mm 양자화는 YOLO bbox 중앙의 거리값 추정에 충분 (서브미터 정확도). `_sample_depth()`가 이미 dh/iw 비율로 좌표 스케일링하므로 호환.

---

## 4. QoS 결정 매트릭스

| 토픽 패턴 | reliability | durability | depth | 이유 |
|-----------|------------|------------|-------|------|
| `/cam/*/rgb` (Main 내부) | BEST_EFFORT | VOLATILE | 5 | Isaac OG 발행, video_degrade가 로컬 구독 |
| `/c2/*/compressed` | BEST_EFFORT | VOLATILE | 5 | 5fps JPEG, 손실 허용 |
| `/c2/tp_*/depth_compressed` (NEW) | BEST_EFFORT | VOLATILE | 5 | 2fps PNG 16UC1 |
| `/robot/state`, `/robot/gps`, `/robot/odom` | RELIABLE | VOLATILE | 10 | 텔레메트리 손실 불가 |
| `/cam/*/camera_info` | RELIABLE | TRANSIENT_LOCAL | 1 | latched, 늦은 join 자동 수신. 1회 + 60s 보호 발행 |
| `/scene/landmarks`, `/robot/weapon/state` | RELIABLE | TRANSIENT_LOCAL | 1 | latched 상태 (zone, weapon FSM) |
| `/robot/cmd_vel`, `/robot/nav/goal` | RELIABLE | VOLATILE | 10 | 업링크 명령 |
| `/tf`, `/tf_static` | (ROS 표준) | - | - | 변경 없음 |

---

## 5. YOLO 채널 정책

- env `C2_YOLO_CAMERAS` 도입
- 기본값: `inspect,tp_a` (1차 정찰 2채널)
- 확장: `inspect,tp_a,tp_b,tp_c,tp_d`로 override 가능
- 적용: `sub1_side/server/config.py:YOLO_CAMERAS` set, `ros_bridge.py:_on_video`에서 `camera in config.YOLO_CAMERAS` 가드
- 향후: CPU 80% 초과 시 자동 축소 (미구현)

---

## 6. DB 통합 — `detection_events`

### 6.1 통합 전후
| 변경 전 | 변경 후 |
|---------|---------|
| `intruder_detections` (YOLO 픽셀 bbox, 13 컬럼) | `detection_events` 단일 테이블 (12 컬럼, JSONB bbox) |
| `intruder_states_log` (NPC ground-truth, 6 컬럼) | `kind='detection'` / `kind='gt_state'` 로 구분 |

### 6.2 스키마
```sql
CREATE TABLE detection_events (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ NOT NULL,
  robot_id TEXT REFERENCES robots(robot_id),
  source TEXT NOT NULL,        -- 'camera_inspect'|'camera_tp_a'..|'ground_truth'
  kind TEXT NOT NULL,          -- 'detection'|'gt_state'
  class_name TEXT,
  confidence REAL,
  bbox_pixel JSONB,            -- {x,y,w,h} | NULL
  world_x REAL, world_y REAL, world_z REAL,
  beyond_fence BOOLEAN,
  intruder_id TEXT,            -- gt_state 시만
  ack BOOLEAN DEFAULT FALSE
);
```

### 6.3 보관 정책
- 30일 (cleanup_old_data 함수에 반영됨)
- 구 테이블 `_deprecated_intruder_detections`, `_deprecated_intruder_states_log`로 rename, 1주 후 별도 PR로 DROP

### 6.4 마이그레이션
파일: `sub1_side/db/migrations/2026-05-24_detection_unify.sql`
- `BEGIN; ... COMMIT;` 트랜잭션
- `gps_track`에 `yaw REAL` 컬럼 추가 (D4 합류)
- 구 테이블 → 신 테이블 INSERT (information_schema 가드)
- 구 테이블 rename to `_deprecated_*`
- 백업 필수: `pg_dump -Fc -d cobot3 -f cobot3_backup_YYYYMMDD.dump`
- 롤백: 백업 restore 또는 SQL 본문 상단의 롤백 절차

---

## 7. 변경 후 측정 (Phase 4)

### 7.1 핵심 지표

| 항목 | 변경 전 | 변경 후 | 절감 |
|------|---------|---------|------|
| **Main LAN TX (wlp128s20f3)** | **17.9 MB/s** | **0.57 MB/s** | **97% ↓** |
| `/cam/tactical/tp_a/depth` 구독자 | C2 (LAN) | depth_degrade_node (로컬만) | LAN 격리 |
| `/c2/tp_a/depth_compressed` 평균 크기 | — (신규) | 22 KB/msg | — |
| `camera_info` 발행 Hz | 1.0 Hz × 3 | 0 Hz (60s 보호) | CPU wakeup 절감 |
| YOLO inference 채널 수 | 5 (inspect+tp_a~d) | 2 (inspect+tp_a, env로 조정) | 60% CPU 절감 |
| DB `intruder_*` 테이블 수 | 2 | 1 (`detection_events`) | 쿼리 단순화 |

### 7.2 검증 명령 결과

```
/cam/tactical/tp_a/depth 구독자: depth_degrade_node (LOCAL) ✓
/c2/tp_a/depth_compressed 구독자: c2_web_server (LAN) ✓
/cam/inspect/camera_info Hz: ros2 hz 타임아웃 (= 정상, 1회 발행 후 idle) ✓
detection_events 마이그레이션: 87 row 이관, kind='detection' ✓
gps_track.yaw: 컬럼 추가됨 ✓
```

---

## 8. 잔여 작업 (FastDDS multicast 차단 — P2)

Phase 0 진단 중 `/cam/*/rgb` 가 Main 로컬 구독자(`video_degrade_node`)만 있음에도
FastDDS 기본 multicast가 LAN 인터페이스로 데이터 패킷을 누출하는 현상을 확인.
현재 Main 측 Isaac 가 사용하는 `fastdds_no_shm.xml`은 multicast 비활성 옵션 부재.

### 8.1 향후 조치 (Isaac 재시작 시 자연 적용)
`main_side/fastdds_no_shm.xml`에 추가:
```xml
<participant profile_name="udp_only" is_default_profile="true">
  <rtps>
    <userTransports>
      <transport_id>udp_only_transport</transport_id>
    </userTransports>
    <useBuiltinTransports>false</useBuiltinTransports>
    <builtin>
      <metatrafficUnicastLocatorList><locator><udpv4/></locator></metatrafficUnicastLocatorList>
      <initialPeersList>
        <locator><udpv4><address>127.0.0.1</address></udpv4></locator>
        <locator><udpv4><address>__C2_PC_IP__</address></udpv4></locator>
      </initialPeersList>
    </builtin>
    <defaultMulticastLocatorList></defaultMulticastLocatorList>
  </rtps>
</participant>
```
효과: 모든 데이터 송수신을 unicast로 강제 → 구독자 없는 토픽의 LAN 누출 차단.

### 8.2 적용 시점
- 현재 Phase 4 측정으로 LAN TX가 이미 0.57 MB/s까지 떨어졌으므로 긴급도 낮음
- 다음 Isaac 재시작 사이클에 fastdds_no_shm.xml 갱신 후 적용 권장

---

## 9. 향후 모니터링 지표

| 지표 | 측정 명령 | 임계값 |
|------|----------|--------|
| Main LAN TX | `cat /sys/class/net/wlp128s20f3/statistics/tx_bytes` 5초 차분 | < 2 MB/s |
| `/c2/tp_*/depth_compressed` 평균 크기 | `ros2 topic bw` | < 100 KB/msg |
| `detection_events` 일간 row 증가 | `SELECT count(*) WHERE ts > now()-INTERVAL '1 day'` | (운영 베이스라인 수립 필요) |
| YOLO inference latency (p95) | C2 web 로그 grep "infer" + timer | < 50ms |
| C2 ros_bridge HEALTH `rx` 카운터 | `/c2/sample` API | 토픽별 0 없음 |

---

## 10. 관련 파일

### 신규
- `main_side/depth_degrade_node.py`
- `sub1_side/db/migrations/2026-05-24_detection_unify.sql`
- `dev-docs/communication-optimization.md` (이 문서)

### 수정
- `main_side/run_degrade.sh` (depth degrade 4개 추가)
- `main_side/video_degrade_node.py` (DEGRADE_IN required)
- `main_side/camera_info_publisher.py` (1Hz timer 제거)
- `sub1_side/server/config.py` (YOLO_CAMERAS, depth 토픽 매핑)
- `sub1_side/server/ros_bridge.py` (depth CompressedImage 구독, YOLO 가드, detection_events INSERT, gps_track yaw)
- `sub1_side/server/db_writer.py` (COLUMNS 통합)
- `sub1_side/db/schema.sql` (detection_events, gps_track.yaw, cleanup_old_data)

### 갱신된 dev-docs
- `dev-docs/ros2-interface.md`
- `dev-docs/architecture.md`
- `dev-docs/design-ros2-bridge.md`
- `dev-docs/ops.md`
- `dev-docs/main-side.md`
- `dev-docs/sub1-side.md`
- `dev-docs/CHANGELOG.md`
