# ROS2 인터페이스 참조

ROS_DOMAIN_ID=130, RMW=rmw_fastrtps_cpp, FastDDS UDP-only

---

## 토픽 목록

### 다운링크 (Main PC → C2 PC)

| 토픽 | 타입 | QoS | Hz | 발행자 | 구독자 |
|------|------|-----|----|-------|-------|
| `/cam/front/rgb` | sensor_msgs/Image | BEST_EFFORT depth=5 | ~50 | OG CamFront | video_degrade_node (front) |
| `/cam/rear/rgb` | sensor_msgs/Image | BEST_EFFORT depth=5 | ~50 | OG CamRear | video_degrade_node (rear) |
| `/c2/front/compressed` | sensor_msgs/CompressedImage | BEST_EFFORT depth=5 | 5 | video_degrade_node | ros_bridge._on_video("front") |
| `/c2/rear/compressed` | sensor_msgs/CompressedImage | BEST_EFFORT depth=5 | 5 | video_degrade_node | ros_bridge._on_video("rear") |
| `/robot/odom` | nav_msgs/Odometry | RELIABLE depth=10 | ~63 | OG OdoPub | telemetry_bridge_node, ros_bridge._on_odom |
| `/robot/gps` | sensor_msgs/NavSatFix | RELIABLE depth=10 | 5 | telemetry_bridge_node | ros_bridge._on_gps |
| `/robot/state` | std_msgs/String (JSON) | RELIABLE depth=10 | 5 | telemetry_bridge_node | ros_bridge._on_state |
| `/robot/leg_joint_states` | sensor_msgs/JointState | RELIABLE depth=10 | ~500 | OG LegJS | ros_bridge._on_leg |
| `/tf` | tf2_msgs/TFMessage | BEST_EFFORT depth=5 | ~50 | OG TF | Foxglove Bridge |
| `/rosout` | rcl_interfaces/Log | RELIABLE depth=10 | on-event | 각 ROS2 노드 | ros_bridge._on_rosout (level>=30만) |

### 업링크 (C2 PC → Main PC)

| 토픽/서비스 | 타입 | QoS | 발행자 | 구독자 |
|-----------|------|-----|-------|-------|
| `/robot/cmd_vel` | geometry_msgs/Twist | RELIABLE depth=10 | ros_bridge.pub_cmd_vel | OG SubCmd → SpotController |
| `/robot/nav/goal` | geometry_msgs/PoseStamped | RELIABLE depth=10 | ros_bridge.publish_goal | SpotController.set_nav_goal |
| `/robot/speaker/audio` | std_msgs/String (JSON) | RELIABLE depth=10 | ros_bridge.send_speaker | (미구현 소비자 — C2측 발행만) |
| `/robot/weapon/fire` | std_srvs/Trigger (service) | RELIABLE | ros_bridge.fire() (client) | (서버: C2 명령 노드 예정) |

---

## 메시지 스키마

### `/robot/state` JSON
```json
{
  "mode": "patrol",
  "gait": "stand" | "walk",
  "battery": 95.3,
  "waypoint": 0,
  "extra": {}
}
```

### `/robot/odom` (핵심 필드)
```
pose.pose.position.{x, y, z}           — base 위치 (m, world 좌표)
pose.pose.orientation.{x, y, z, w}     — 쿼터니언 (yaw 추출에 사용)
twist.twist.linear.{x, y, z}           — 선속도 (m/s)
twist.twist.angular.{x, y, z}          — 각속도 (rad/s)
```

**yaw 추출 공식 (ros_bridge._on_odom):**
```python
siny = 2.0 * (q.w * q.z + q.x * q.y)
cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
yaw = math.atan2(siny, cosy)
```

### `/robot/cmd_vel` (Twist)
```
linear.x  — 전진 속도 (m/s), SpotController: [-0.6, 0.6]
angular.z — 회전 속도 (rad/s), SpotController: [-1.2, 1.2]
```

### `/robot/weapon/fire` (Trigger)
```
Request:  (빈 요청)
Response: success: bool
          message: "hit;distance_m" (예: "true;12.5")
```

---

## QoS 프로파일 상세

### RELIABLE (명령·텔레메트리)
```json
{
  "history": "keepLast", "depth": 10,
  "reliability": "reliable", "durability": "volatile",
  "deadline": 0.0, "lifespan": 0.0,
  "liveliness": "systemDefault", "leaseDuration": 0.0
}
```

### BEST_EFFORT (영상·TF)
```json
{
  "history": "keepLast", "depth": 5,
  "reliability": "bestEffort", "durability": "volatile",
  "deadline": 0.0, "lifespan": 0.0,
  "liveliness": "systemDefault", "leaseDuration": 0.0
}
```

> **주의:** Isaac OG ROS2 노드는 8개 키 전체 필수. 일부 생략 시 `WARNING: QoSProfile` 후 엔드포인트 미생성.

---

## FastDDS 설정

```
fastdds_no_shm.xml    — UDPv4-only, SharedMemory 비활성
fastdds_main.xml      — 2-PC LAN 프로파일 (unicast initialPeers 포함, IP 치환 필요)
```

**환경변수:**
```bash
RMW_IMPLEMENTATION=rmw_fastrtps_cpp
FASTRTPS_DEFAULT_PROFILES_FILE=/path/to/fastdds_no_shm.xml
ROS_DOMAIN_ID=130
ROS_LOCALHOST_ONLY=0    # 크로스호스트 허용
```

**SHM 비활성 이유:** Isaac 번들 FastDDS 2.6.x와 시스템 FastDDS 2.6.11이 SharedMemory 포맷 비호환
→ UDP-only로 강제하면 wire 포맷 호환 달성.
