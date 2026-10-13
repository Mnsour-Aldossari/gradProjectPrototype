"""The mission bridge, the detector node and mission control together. UAV_USERNAME and UAV_PASSWORD must be set
(a backend account to read); UAV_CONTROL_USERNAME and UAV_CONTROL_PASSWORD (a supervisor's) for the commands.

  ros2 launch uav_landmine_ros landmine.launch.py                      # the next mission that flies
  ros2 launch uav_landmine_ros landmine.launch.py mission_id:=12       # one mission, flown or flying
  ros2 launch uav_landmine_ros landmine.launch.py record:=true         # and record it in ~/uav_bags
  ros2 launch uav_landmine_ros landmine.launch.py rviz:=true           # with RViz (ros-jazzy-rviz2 installed)
"""

from datetime import datetime
from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from uav_landmine_ros.launching import dds_profile, shared_file

# Recorded: what the bridge and the detector publish, and the transforms.
RECORDED = [
    "/mission/info", "/sensors/readings", "/uav/fix", "/uav/pose", "/uav/path", "/uav/battery",
    "/landmine/detections", "/landmine/candidates", "/landmine/markers", "/tf", "/tf_static", "/diagnostics",
]  # fmt: skip


def generate_launch_description() -> LaunchDescription:
    params = LaunchConfiguration("params_file")
    bag = str(Path.home() / "uav_bags" / datetime.now().strftime("mission_%Y-%m-%d_%H-%M-%S"))
    return LaunchDescription(
        [
            *dds_profile(),
            DeclareLaunchArgument("backend_url", default_value="http://127.0.0.1:8000"),
            DeclareLaunchArgument("mission_id", default_value="0", description="0: the next mission that flies"),
            DeclareLaunchArgument("params_file", default_value=shared_file("config", "params.yaml")),
            DeclareLaunchArgument("record", default_value="false", description="record the topics in ~/uav_bags"),
            DeclareLaunchArgument("rviz", default_value="false"),
            Node(
                package="uav_landmine_ros",
                executable="mission_bridge",
                parameters=[params, {name: LaunchConfiguration(name) for name in ("backend_url", "mission_id")}],
                output="screen",
            ),
            Node(package="uav_landmine_ros", executable="landmine_detector", parameters=[params], output="screen"),
            Node(
                package="uav_landmine_ros",
                executable="mission_control",
                parameters=[params, {"backend_url": LaunchConfiguration("backend_url")}],
                output="screen",
            ),
            ExecuteProcess(
                cmd=[
                    "ros2", "bag", "record", "-s", "mcap", "-o", bag, "--qos-profile-overrides-path",
                    shared_file("config", "qos_latched.yaml"), "--topics", *RECORDED,
                ],
                output="screen",
                condition=IfCondition(LaunchConfiguration("record")),
            ),  # fmt: skip
            Node(
                package="rviz2",
                executable="rviz2",
                arguments=["-d", shared_file("rviz", "landmine.rviz")],
                condition=IfCondition(LaunchConfiguration("rviz")),
            ),
        ]
    )
