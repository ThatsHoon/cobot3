"""T4 단위: cmd_vel_safety_filter._on_cmd_vel 클램프 + 동시 통과 검증."""
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
    inst._max_linear_x = 0.8
    inst._max_angular_z = 0.85
    inst._min_drive_linear = 0.08
    inst._muted = False
    inst._patrol_mode = "IDLE"
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


def test_linear_passes_through(filter_node):
    inst, mod = filter_node
    inst._on_cmd_vel(_make_twist(0.5, 0.0))
    out = _last_published(inst)
    assert abs(out.linear.x - 0.5) < 1e-6
    assert out.angular.z == 0.0


def test_angular_passes_through(filter_node):
    inst, mod = filter_node
    inst._on_cmd_vel(_make_twist(0.0, 0.4))
    out = _last_published(inst)
    assert out.linear.x == 0.0
    assert abs(out.angular.z - 0.4) < 1e-6


def test_simultaneous_linear_and_angular(filter_node):
    """linear 과 angular 가 동시에 모두 통과해야 한다 (곡선 주행 지원)."""
    inst, mod = filter_node
    inst._on_cmd_vel(_make_twist(0.5, 0.4))
    out = _last_published(inst)
    assert abs(out.linear.x - 0.5) < 1e-6
    assert abs(out.angular.z - 0.4) < 1e-6


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


def test_nan_is_zeroed(filter_node):
    inst, mod = filter_node
    msg = _make_twist(0.5, 0.0)
    msg.linear.x = float("nan")
    inst._on_cmd_vel(msg)
    out = _last_published(inst)
    assert out.linear.x == 0.0


def test_muted_publishes_zero(filter_node):
    inst, mod = filter_node
    inst._muted = True
    inst._on_cmd_vel(_make_twist(0.5, 0.4))
    out = _last_published(inst)
    assert out.linear.x == 0.0
    assert out.angular.z == 0.0
