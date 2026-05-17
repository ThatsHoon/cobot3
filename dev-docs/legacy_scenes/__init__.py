"""cobot3 scene 빌드 모듈.

각 setup_*.py 는 두 가지 방식으로 호출 가능:

1. **MCP execute_script 안에서**:
   ```python
   import sys; sys.path.insert(0, "/home/rokey/dev_ws/isaac_sim/cobot3")
   from scenes import setup_ground_and_physics
   setup_ground_and_physics.run()
   ```

2. **standalone Python (python.sh)**:
   ```bash
   ~/dev_ws/isaac_sim/isaacsim/_build/linux-x86_64/release/python.sh \
       -m scenes.setup_ground_and_physics
   ```

모든 스크립트는 idempotent — 여러 번 호출해도 안전.
"""
