"""Plays a recording (landmine.launch.py record:=true) to the detector node alone, without the backend, and compares
its final potential detections with the backend's that were recorded.

  ros2 launch uav_landmine_ros replay.launch.py bag:=$HOME/uav_bags/mission_2026-10-08_14-03-12
  ros2 launch uav_landmine_ros replay.launch.py bag:=... rate:=10 rviz:=true
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, RegisterEventHandler, Shutdown, TimerAction
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from uav_landmine_ros.launching import dds_profile, shared_file

# Only what the detector takes, and the backend's detections to compare with; the rest plays too, for RViz.
PLAYED = [
    "/mission/info", "/sensors/readings", "/landmine/detections", "/uav/pose", "/uav/path", "/tf", "/tf_static",
]  # fmt: skip


def generate_launch_description() -> LaunchDescription:
    compare = Node(
        package="uav_landmine_ros",
        executable="compare_with_backend",
        parameters=[{"against": "recording", "timeout_s": 600.0}],
        output="screen",
        condition=IfCondition(LaunchConfiguration("compare")),
    )
    return LaunchDescription(
        [
            *dds_profile(),
            DeclareLaunchArgument("bag", description="the recording's folder"),
            DeclareLaunchArgument("rate", default_value="1.0", description="playback speed"),
            DeclareLaunchArgument("compare", default_value="true"),
            DeclareLaunchArgument("rviz", default_value="false"),
            Node(
                package="uav_landmine_ros",
                executable="landmine_detector",
                parameters=[shared_file("config", "params.yaml")],
                output="screen",
            ),
            compare,
            TimerAction(  # the detector and the comparison subscribe first
                period=2.0,
                actions=[
                    ExecuteProcess(
                        cmd=[
                            "ros2", "bag", "play", LaunchConfiguration("bag"), "-r", LaunchConfiguration("rate"),
                            "--qos-profile-overrides-path", shared_file("config", "qos_latched.yaml"),
                            "--topics", *PLAYED,
                        ],
                        output="screen",
                    )
                ],
            ),  # fmt: skip
            RegisterEventHandler(OnProcessExit(target_action=compare, on_exit=[Shutdown(reason="compared")])),
            Node(
                package="rviz2",
                executable="rviz2",
                arguments=["-d", shared_file("rviz", "landmine.rviz")],
                condition=IfCondition(LaunchConfiguration("rviz")),
            ),
        ]
    )
