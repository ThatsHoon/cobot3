"""robot_state_publisher launch — Go2 URDF FK + /robot/leg_joint_states → /tf.

Lichtblick 3D 패널이 URDF mesh 렌더링하려면 각 link 의 TF 가 발행돼야 함.
Isaac OG TF helper 는 world→Go2 만 발행하고 12 leg joint TF 미발행 →
mesh 가 transform lookup 실패. robot_state_publisher 가 URDF FK 로 모든
link transform 발행.

URDF path: /tmp/go2.urdf (main_side/scene/go2_description/urdf/go2.urdf 복사본).
remap: /joint_states → /robot/leg_joint_states.

실행: ros2 launch main_side/robot_state_publisher.launch.py
"""
import os

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    urdf_path = os.environ.get("GO2_URDF", "/tmp/go2.urdf")
    with open(urdf_path) as f:
        urdf = f.read()
    return LaunchDescription([
        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            name="robot_state_publisher",
            output="screen",
            parameters=[{
                "robot_description": urdf,
                "publish_frequency": 30.0,
            }],
            remappings=[
                ("joint_states", "/robot/leg_joint_states"),
            ],
        ),
    ])
