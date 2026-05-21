# T13 — DMZ_Zone e2e 수동 시나리오

## 사전조건
- `bake_gp_static_map.py --zone dmz --res 0.4` 실행 (DMZ_Zone 80×80m 베이크)
- Nav2 launch 의 map yaml 을 `main_side/scene/maps/dmz_static.yaml` 로 임시 교체 또는
  병행: `ros2 launch sub1_side/server/nav2_bringup.launch.py map:=$(realpath main_side/scene/maps/dmz_static.yaml)`

## 검증 단계

1. **Isaac 재기동** (DMZ zone 활성)
   ```bash
   isaac-clear
   export GP_GO2_SPAWN_ZONE=dmz
   cobot3-start_all
   ```

2. **Go2 spawn 검증** (DMZ home(0,0) 위)
   ```bash
   ros2 run tf2_ros tf2_echo world Go2
   # Translation: [0.00x, 0.00x, ~0.5]  (DMZ home + clearance)
   ```

3. **landmarks 검증**
   ```bash
   ros2 topic echo --once --field data /scene/landmarks | python3 -m json.tool
   # zone: "dmz", dmz_home: {0,0,0}, dmz_cone: {24,-12,0}, dmz_patrol_w: {-24,-12,0},
   # dmz_fence: [{-40,16,0},{40,16,0}]
   ```

4. **Nav2 stack + patrol 기동**
   ```bash
   ( cd sub1_side/server && bash run_nav2.sh map:=$(realpath ../../main_side/scene/maps/dmz_static.yaml) & ) 
   ( cd sub1_side/server && python3 cmd_vel_safety_filter.py & )
   ( cd sub1_side/server && python3 nav2_patrol.py & )
   ( cd sub1_side/server && bash run.sh & )
   ```

5. **patrol 모드 진입**
   ```bash
   ros2 topic pub --once /mission_command std_msgs/String "{data: 'sortie'}"
   ros2 topic echo --once --field data /patrol_state
   # mode: "PATROL", waypoint: {24,-12} 또는 {-24,-12}
   ```

6. **보행 검증** (옵션 — 시간 소요)
   ```bash
   for i in 1 2 3 4 5 6; do
     ros2 topic echo --once --field pose.pose.position /robot/odom
     sleep 5
   done
   # /robot/odom 누적 변화 확인 (odometry, world 좌표 아님)
   ```

7. **/animal_alerts 트리거**
   ```bash
   ros2 topic pub --once /animal_alerts std_msgs/String "{data: '{\"level\":\"ALERT\",\"event\":\"animal_detected\",\"label\":\"deer\",\"confidence\":0.78,\"bbox_xyxy\":[0,0,50,50],\"count\":1,\"action\":\"monitor\"}'}"
   # 브라우저 AnimalAlertsLog 카드 prepend
   ```

8. **브라우저 검증** (http://localhost:3000)
   - DualCameraView: FRONT + INSPECT 2 panel MJPEG
   - MapTrack: DMZ marker (amber), fence 점선, robot trail
   - PatrolControls: mode=PATROL 표시
   - AnimalAlertsLog: 항목 prepend
   - EventLog: 14줄 스크롤

9. **cube zone 회귀**
   ```bash
   ros2 topic pub --once /mission_command std_msgs/String "{data: 'stop'}"
   isaac-clear
   unset GP_GO2_SPAWN_ZONE   # 또는 export GP_GO2_SPAWN_ZONE=cube
   cobot3-start_all
   ros2 run tf2_ros tf2_echo world Go2
   # Translation: [-714.x, 952.x, ~30.x]  (Cube 위)
   ```

## 성공 기준
- spawn 좌표가 `GP_GO2_SPAWN_ZONE` 에 따라 정확히 분기
- landmarks JSON 의 zone 키 + dmz_* 키 모두 발행
- /patrol_state mode 가 sortie 시 PATROL 로 전환
- Nav2 planner WARN 0건 (`tail /tmp/cobot3_nav2.log | grep -E "fail|valid path"` 빈 결과)
- 브라우저 5개 패널 모두 가시 (DualCameraView·MapTrack·PatrolControls·AnimalAlertsLog·EventLog)
