#!/usr/bin/env python3
"""
최소 양방향 ROS2 브리지 검증 (씬 無·rclpy 無 · OmniGraph C++ 브리지만).

목적: "메인 PC 시스템 ROS2 ↔ Isaac 내부" 통신 가부를 가장 작은 단위로 판정.
  · 업링크: OG ROS2PublishClock → 시스템에서 `ros2 topic echo /clock` 수신?
  · 다운링크: 시스템 `ros2 topic pub /cobot3_cmd_vel` → OG ROS2SubscribeTwist
              이 수신해 이 스크립트가 RX 값을 출력?
OmniGraph 의 ROS2* 노드는 isaacsim.ros2.bridge 의 C++ rmw/rcl 을 직접 쓰므로
시스템 rclpy(py3.10) 와의 ABI 충돌(업링크 rclpy 경로의 과거 실패원인)과 무관.
런처 run_test_ros2_bridge.sh 가 internal humble libfastrtps(2.6.x, 시스템
2.6.11 과 와이어호환) 로 LD 를 잡아준다.
"""
import os
import time

from isaacsim import SimulationApp

simulation_app = SimulationApp({"headless": True})

import omni.timeline
import omni.graph.core as og
from isaacsim.core.api import World
from isaacsim.core.utils.extensions import enable_extension

enable_extension("isaacsim.ros2.bridge")
for _ in range(60):
    simulation_app.update()

DOMAIN = int(os.environ.get("ROS_DOMAIN_ID", "129"))
CMD_TOPIC = os.environ.get("TEST_CMD_TOPIC", "/cobot3_cmd_vel")
GRAPH = "/World/Graphs/test_bridge"


def log(m):
    print(f"[test_bridge] {m}", flush=True)


world = World(stage_units_in_meters=1.0)
world.scene.add_default_ground_plane()

K = og.Controller.Keys
og.Controller.edit(
    {"graph_path": GRAPH, "evaluator_name": "execution"},
    {
        K.CREATE_NODES: [
            ("OnTick", "omni.graph.action.OnPlaybackTick"),
            ("Ctx", "isaacsim.ros2.bridge.ROS2Context"),
            ("SimTime", "isaacsim.core.nodes.IsaacReadSimulationTime"),
            ("PubClock", "isaacsim.ros2.bridge.ROS2PublishClock"),
            ("SubTwist", "isaacsim.ros2.bridge.ROS2SubscribeTwist"),
        ],
        K.SET_VALUES: [
            ("Ctx.inputs:domain_id", DOMAIN),
            ("PubClock.inputs:topicName", "/clock"),
            ("SubTwist.inputs:topicName", CMD_TOPIC),
        ],
        K.CONNECT: [
            ("OnTick.outputs:tick", "PubClock.inputs:execIn"),
            ("OnTick.outputs:tick", "SubTwist.inputs:execIn"),
            ("Ctx.outputs:context", "PubClock.inputs:context"),
            ("Ctx.outputs:context", "SubTwist.inputs:context"),
            ("SimTime.outputs:simulationTime", "PubClock.inputs:timeStamp"),
        ],
    },
)
log(f"OG 생성 완료 — domain={DOMAIN} pub=/clock sub={CMD_TOPIC}")

world.reset()
omni.timeline.get_timeline_interface().play()

lin_attr = og.Controller.attribute(f"{GRAPH}/SubTwist.outputs:linearVelocity")
ang_attr = og.Controller.attribute(f"{GRAPH}/SubTwist.outputs:angularVelocity")

log("=== READY: 시스템 측에서 아래 2개 실행 ===")
log(f"  1) ros2 topic echo /clock              (업링크 확인)")
log(f"  2) ros2 topic pub {CMD_TOPIC} geometry_msgs/msg/Twist "
    f"'{{linear: {{x: 0.7}}, angular: {{z: 0.3}}}}' -r 5   (다운링크 확인)")

_tl = omni.timeline.get_timeline_interface()
try:
    _graph = og.get_graph_by_path(GRAPH)
except Exception as e:
    _graph = None
    log(f"get_graph err {e!r}")
simtime_attr = og.Controller.attribute(f"{GRAPH}/SimTime.outputs:simulationTime")

last = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
i = 0
while simulation_app.is_running():
    world.step(render=True)          # render=True 라야 타임라인 프레임 전진
                                     # → OnPlaybackTick 펄스 → ROS2 노드 실행
    if _graph is not None:
        try:
            _graph.evaluate()           # OG 강제 평가 보장
        except Exception as e:
            log(f"graph.evaluate err {e!r}")
    i += 1
    if i % 30 == 0:
        try:
            _st = simtime_attr.get()
        except Exception:
            _st = "n/a"
        log(f"  [diag] playing={_tl.is_playing()} t={_tl.get_current_time():.2f} "
            f"OG.simTime={_st}")
    if i % 30 == 0:
        try:
            import numpy as _np
            lin = _np.asarray(lin_attr.get()).astype(float).ravel().tolist()
            ang = _np.asarray(ang_attr.get()).astype(float).ravel().tolist()
        except Exception as e:
            lin, ang = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
            log(f"attr read err {e!r}")
        cur = tuple(lin) + tuple(ang)
        rx = any(abs(float(v)) > 1e-6 for v in cur)
        log(f"[{i:5d}] DOWNLINK RX lin={lin} ang={ang}  "
            f"{'<<< 수신중' if rx else '(아직 0 — pub 대기/미수신)'}")
        last = cur

simulation_app.close()
