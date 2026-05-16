#!/usr/bin/env bash
# standalone 카메라 퍼블리셔 기동 (MCP/GUI 비의존, CycloneDDS).
# GUI Isaac 과 동시에 띄우면 GPU 경합 → GUI Isaac 은 닫고 실행 권장.
set -e
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_DOMAIN_ID=130
export ROS_LOCALHOST_ONLY=0
# 어떤 씬을 쓸지 (기본 cobot3_1.usd; 없으면 스크립트가 최소 구성/빈 스테이지)
export GP_SCENE="${GP_SCENE:-/home/rokey/dev_ws/isaac_sim/src/doosan-robot2/urdf/m0609_isaac_sim/cobot3_1.usd}"
ISAAC=~/dev_ws/isaac_sim/isaacsim/_build/linux-x86_64/release
exec "$ISAAC/python.sh" /home/rokey/dev_ws/isaac_sim/cobot3/main_side/camera_publisher.py
