"""Nav2 bringup — cobot3 Go2 적용. Main PC 에서 실행 (2026-05-21 이동).
로봇 측 onboard nav2 패턴 — Isaac OG sensor → costmap → planner → controller
→ /cmd_vel_nav → smoother → /cmd_vel_nav2_raw → safety_filter → /robot/cmd_vel.

기본 params: main_side/nav2_params.yaml
기본 map:    main_side/scene/maps/gp_static.yaml

실행:
    ros2 launch main_side/nav2_bringup.launch.py
    ros2 launch main_side/nav2_bringup.launch.py map:=/path/to/other.yaml
"""
from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, SetEnvironmentVariable
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

_HERE = Path(__file__).resolve().parent

DEFAULT_PARAMS = _HERE / "nav2_params.yaml"
DEFAULT_MAP = _HERE / "scene" / "maps" / "gp_static.yaml"


def generate_launch_description():
    params_file = LaunchConfiguration("params_file")
    map_file = LaunchConfiguration("map")
    use_sim_time = LaunchConfiguration("use_sim_time")
    autostart = LaunchConfiguration("autostart")

    lifecycle_nodes = [
        "map_server",
        "controller_server",
        "smoother_server",
        "planner_server",
        "behavior_server",
        "bt_navigator",
        "waypoint_follower",
        "velocity_smoother",
    ]

    remappings = [("/tf", "tf"), ("/tf_static", "tf_static")]

    return LaunchDescription([
        SetEnvironmentVariable("RCUTILS_LOGGING_BUFFERED_STREAM", "1"),
        DeclareLaunchArgument("params_file", default_value=str(DEFAULT_PARAMS)),
        DeclareLaunchArgument("map", default_value=str(DEFAULT_MAP)),
        DeclareLaunchArgument("use_sim_time", default_value="true"),
        DeclareLaunchArgument("autostart", default_value="true"),
        Node(
            package="nav2_map_server",
            executable="map_server",
            name="map_server",
            output="screen",
            parameters=[params_file,
                        {"yaml_filename": map_file,
                         "use_sim_time": use_sim_time}],
            remappings=remappings,
        ),
        Node(
            package="nav2_controller",
            executable="controller_server",
            name="controller_server",
            output="screen",
            parameters=[params_file],
            remappings=remappings + [("cmd_vel", "cmd_vel_nav")],
        ),
        Node(
            package="nav2_smoother",
            executable="smoother_server",
            name="smoother_server",
            output="screen",
            parameters=[params_file],
            remappings=remappings,
        ),
        Node(
            package="nav2_planner",
            executable="planner_server",
            name="planner_server",
            output="screen",
            parameters=[params_file],
            remappings=remappings,
        ),
        Node(
            package="nav2_behaviors",
            executable="behavior_server",
            name="behavior_server",
            output="screen",
            parameters=[params_file],
            remappings=remappings,
        ),
        Node(
            package="nav2_bt_navigator",
            executable="bt_navigator",
            name="bt_navigator",
            output="screen",
            parameters=[params_file],
            remappings=remappings,
        ),
        Node(
            package="nav2_waypoint_follower",
            executable="waypoint_follower",
            name="waypoint_follower",
            output="screen",
            parameters=[params_file],
            remappings=remappings,
        ),
        Node(
            package="nav2_velocity_smoother",
            executable="velocity_smoother",
            name="velocity_smoother",
            output="screen",
            parameters=[params_file],
            remappings=remappings + [
                ("cmd_vel", "cmd_vel_nav"),
                ("cmd_vel_smoothed", "cmd_vel_nav2_raw"),
            ],
        ),
        Node(
            package="nav2_lifecycle_manager",
            executable="lifecycle_manager",
            name="lifecycle_manager_cobot3_nav2",
            output="screen",
            parameters=[
                {"use_sim_time": use_sim_time},
                {"autostart": autostart},
                {"node_names": lifecycle_nodes},
            ],
        ),
    ])
