"""ROS 통신 테스트 공용 헬퍼.

각 테스트는 subprocess 로 노드를 띄우고, 본 모듈은 그 노드와 통신하는
pytest 측 rclpy node 를 만든다.

격리: ROS_DOMAIN_ID=199 (Isaac/Nav2 진행 중인 도메인 130 과 분리).
"""
import os
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import rclpy
from rclpy.node import Node

TEST_DOMAIN = "199"
_REPO = Path(__file__).resolve().parents[1]


def setup_test_env():
    """테스트용 ROS env 격리 설정."""
    os.environ["ROS_DOMAIN_ID"] = TEST_DOMAIN
    os.environ.setdefault("RMW_IMPLEMENTATION", "rmw_fastrtps_cpp")
    os.environ["ROS_LOCALHOST_ONLY"] = "1"   # 같은 호스트만, LAN 격리
    # camera_publisher 가 쓰는 FastDDS 프로파일 충돌 회피 — 디폴트 사용
    os.environ.pop("FASTRTPS_DEFAULT_PROFILES_FILE", None)


@contextmanager
def spawn_node(script_relpath, args=None, env_extra=None, ready_topic=None):
    """sub1_side/server 또는 main_side 의 standalone Python 노드를 subprocess
    로 띄움. ROS_DOMAIN_ID=199. 컨텍스트 종료 시 SIGTERM.

    script_relpath: cobot3 repo 루트 기준 상대경로 (예: "main_side/world_odom_tf_pub.py")
    args: subprocess 추가 인자
    env_extra: 추가 env (dict)
    ready_topic: 정해진 경우, 해당 토픽의 publisher 가 등록될 때까지 대기.
    """
    script = _REPO / script_relpath
    assert script.exists(), f"{script} 없음"
    env = os.environ.copy()
    env["ROS_DOMAIN_ID"] = TEST_DOMAIN
    env["RMW_IMPLEMENTATION"] = "rmw_fastrtps_cpp"
    env["ROS_LOCALHOST_ONLY"] = "1"
    env.pop("FASTRTPS_DEFAULT_PROFILES_FILE", None)
    if env_extra:
        env.update(env_extra)
    cmd = [sys.executable, str(script)] + (args or [])
    proc = subprocess.Popen(
        cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        cwd=str(script.parent), preexec_fn=os.setsid)
    try:
        yield proc
    finally:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=5)
        except Exception:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass


def wait_until(predicate, timeout=10.0, interval=0.05):
    """predicate() 가 truthy 가 될 때까지 대기. 타임아웃 시 False."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        try:
            if predicate():
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def spin_for(node: Node, seconds: float, predicate=None):
    """node 를 seconds 동안 spin (또는 predicate 가 True 면 즉시 종료)."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < seconds:
        rclpy.spin_once(node, timeout_sec=0.05)
        if predicate is not None and predicate():
            return True
    return False if predicate else None
