"""T4 단위: cmd_vel_safety_filter._on_cmd_vel 모드 전환 + 클램프."""
import sys
import types
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def filter_node():
    """rclpy 없이 CmdVelSafetyFilter 의 _on_cmd_vel 로직만 단위 검증.

    Node.__init__ 호출 비용을 피하기 위해 __init__ 을 우회한 인스턴스 생성.
    필요한 인스턴스 attr 만 직접 세팅 + _pub.publish 를 MagicMock.
    """
    import rclpy  # noqa
    import cmd_vel_safety_filter as mod

    inst = mod.CmdVelSafetyFilter.__new__(mod.CmdVelSafetyFilter)
    inst._mode = mod.MODE_DRIVE
    inst._max_linear_x = 0.8
    inst._max_angular_z = 0.85
    inst._turn_enter_angular = 0.32
    inst._turn_exit_angular = 0.10
    inst._min_drive_linear = 0.08
    inst._pub = MagicMock()
    return inst, mod


def _make_twist(lin_x=0.0, ang_z=0.0):
    from geometry_msgs.msg import Twist
    t = Twist()
    t.linear.x = float(lin_x)
    t.angular.z = float(ang_z)
    return t


def _last_published(inst):
    assert inst._pub.publish.called
    return inst._pub.publish.call_args.args[0]


def test_drive_mode_passes_linear(filter_node):
    inst, mod = filter_node
    inst._on_cmd_vel(_make_twist(0.5, 0.0))
    out = _last_published(inst)
    assert inst._mode == mod.MODE_DRIVE
    assert abs(out.linear.x - 0.5) < 1e-6
    assert out.angular.z == 0.0


def test_turn_enter_threshold(filter_node):
    inst, mod = filter_node
    inst._on_cmd_vel(_make_twist(0.5, 0.4))   # ≥ turn_enter 0.32
    out = _last_published(inst)
    assert inst._mode == mod.MODE_TURN
    assert abs(out.angular.z - 0.4) < 1e-6
    assert out.linear.x == 0.0    # turn 모드는 linear 0


def test_turn_exit_threshold(filter_node):
    inst, mod = filter_node
    inst._mode = mod.MODE_TURN
    inst._on_cmd_vel(_make_twist(0.4, 0.05))   # ≤ turn_exit 0.10
    assert inst._mode == mod.MODE_DRIVE
    out = _last_published(inst)
    assert abs(out.linear.x - 0.4) < 1e-6


def test_min_drive_linear_clipped(filter_node):
    inst, mod = filter_node
    inst._on_cmd_vel(_make_twist(0.05, 0.0))  # < min_drive 0.08
    out = _last_published(inst)
    assert out.linear.x == 0.0


def test_max_linear_clamped(filter_node):
    inst, mod = filter_node
    inst._on_cmd_vel(_make_twist(10.0, 0.0))
    out = _last_published(inst)
    assert abs(out.linear.x - 0.8) < 1e-6


def test_max_angular_clamped(filter_node):
    inst, mod = filter_node
    inst._on_cmd_vel(_make_twist(0.0, 5.0))
    out = _last_published(inst)
    assert abs(out.angular.z - 0.85) < 1e-6
    assert inst._mode == mod.MODE_TURN


def test_nan_is_zeroed(filter_node):
    inst, mod = filter_node
    msg = _make_twist(0.5, 0.0)
    msg.linear.x = float("nan")
    inst._on_cmd_vel(msg)
    out = _last_published(inst)
    assert out.linear.x == 0.0
