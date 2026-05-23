"""T9 ROS round-trip: /scene/landmarks latched 전달.

camera_publisher 가 dump 한 /tmp/cobot3_landmarks.json 를 mock 하고
landmarks_pub.py subprocess 를 띄워 TRANSIENT_LOCAL 구독자가 메시지를
받는지 확인. late-subscribe (publish 후 구독 시작) 도 검증.
"""
import json
import os
from pathlib import Path

import pytest
import rclpy
from rclpy.node import Node
from rclpy.qos import (DurabilityPolicy, HistoryPolicy, QoSProfile,
                       ReliabilityPolicy)
from std_msgs.msg import String

from _ros_helpers import setup_test_env, spawn_node, spin_for

_LM_PATH = Path("/tmp/cobot3_landmarks.json")
_BACKUP = Path("/tmp/cobot3_landmarks.json.testbak")
_SAMPLE = {
    "cube": {"x": -714.32, "y": 952.93, "z": 30.57},
    "cone": {"x": -937.07, "y": 938.98, "z": 0.0},
    "fence": [{"x": -800.0, "y": 945.0, "z": 1.0},
              {"x": -850.0, "y": 945.0, "z": 1.0}],
}


@pytest.fixture(scope="module", autouse=True)
def _rclpy_ctx():
    setup_test_env()
    rclpy.init()
    yield
    rclpy.shutdown()


@pytest.fixture
def landmarks_file():
    """기존 파일 백업 → 테스트 샘플 쓰기 → 복구."""
    had = _LM_PATH.exists()
    if had:
        _LM_PATH.rename(_BACKUP)
    _LM_PATH.write_text(json.dumps(_SAMPLE))
    yield _LM_PATH
    _LM_PATH.unlink(missing_ok=True)
    if had and _BACKUP.exists():
        _BACKUP.rename(_LM_PATH)


def _latched_qos():
    return QoSProfile(
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.TRANSIENT_LOCAL,
        history=HistoryPolicy.KEEP_LAST, depth=1)


class LMSub(Node):
    def __init__(self):
        super().__init__("test_lm_sub")
        self.payload = None
        self.create_subscription(String, "/scene/landmarks",
                                 self._cb, _latched_qos())

    def _cb(self, msg):
        try:
            self.payload = json.loads(msg.data)
        except Exception:
            self.payload = {"raw": msg.data}


def test_landmarks_received_after_pub_starts(landmarks_file):
    with spawn_node("main_side/landmarks_pub.py"):
        sub = LMSub()
        ok = spin_for(sub, 8.0, predicate=lambda: sub.payload is not None)
        assert ok and sub.payload is not None, "TIMEOUT — landmarks 미수신"
        assert "cube" in sub.payload and "cone" in sub.payload
        assert abs(sub.payload["cube"]["x"] - (-714.32)) < 1e-3
        sub.destroy_node()


def test_landmarks_late_subscribe(landmarks_file):
    """publisher 가 먼저 latched 발행한 뒤 subscriber 가 늦게 들어와도
    TRANSIENT_LOCAL 덕에 직전 메시지를 1회 즉시 수신해야 한다."""
    with spawn_node("main_side/landmarks_pub.py"):
        # 발행이 진행될 시간을 충분히
        import time
        time.sleep(3.0)
        sub = LMSub()
        ok = spin_for(sub, 5.0, predicate=lambda: sub.payload is not None)
        assert ok, "late subscribe 가 latched 받지 못함"
        sub.destroy_node()
