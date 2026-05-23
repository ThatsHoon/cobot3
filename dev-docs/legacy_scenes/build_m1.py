"""M1 전체 빌드 — 한 번에 호출하는 orchestrator.

순서:
  1. ground + physics
  2. conveyor (kinematic + surface velocity)
  3. bins (3 개)
  4. robot r0 (m0609)
  5. test box 1 개 spawn

호출:
  MCP execute_script 안:
    import sys; sys.path.insert(0, "/home/rokey/dev_ws/isaac_sim/cobot3")
    from scenes import build_m1
    build_m1.run()
"""


def run() -> str:
    results = []

    from scenes import setup_ground_and_physics
    results.append(setup_ground_and_physics.run())

    from scenes import setup_conveyor
    results.append(setup_conveyor.run())

    from scenes import setup_bins
    results.append(setup_bins.run())

    from scenes import setup_robot_r0
    results.append(setup_robot_r0.run())

    from scenes import setup_spawn_box
    results.append(setup_spawn_box.run("red", 1))

    summary = "\n".join(f"  {i+1}. {r}" for i, r in enumerate(results))
    return f"M1 build complete:\n{summary}"


if __name__ == "__main__":
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": False})

    import sys
    sys.path.insert(0, "/home/rokey/dev_ws/isaac_sim/cobot3")

    print(run())
    # 사람이 보고 검증할 수 있도록 잠시 대기
    import time
    print("\n10 초 대기 (Isaac Sim viewport 에서 확인) ...")
    time.sleep(10)
    app.close()
