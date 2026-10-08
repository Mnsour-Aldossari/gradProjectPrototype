"""The mission bridge and the detector node together. UAV_USERNAME and UAV_PASSWORD must be set (a backend account).

  ros2 launch uav_landmine_ros landmine.launch.py                      # the next mission that flies
  ros2 launch uav_landmine_ros landmine.launch.py mission_id:=12       # one mission, flown or flying
  ros2 launch uav_landmine_ros landmine.launch.py rviz:=true           # with RViz (ros-jazzy-rviz2 installed)
"""

import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, SetEnvironmentVariable
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    backend_url = LaunchConfiguration("backend_url")
    mission_id = LaunchConfiguration("mission_id")
    share = FindPackageShare("uav_landmine_ros")
    # Fast DDS over shared memory (config/fastdds_shm.xml says why), unless another profile is chosen.
    dds = []
    if "FASTRTPS_DEFAULT_PROFILES_FILE" not in os.environ:
        profile = PathJoinSubstitution([share, "config", "fastdds_shm.xml"])
        dds = [SetEnvironmentVariable("FASTRTPS_DEFAULT_PROFILES_FILE", profile)]
    return LaunchDescription(
        [
            *dds,
            DeclareLaunchArgument("backend_url", default_value="http://127.0.0.1:8000"),
            DeclareLaunchArgument("mission_id", default_value="0", description="0: the next mission that flies"),
            DeclareLaunchArgument("rviz", default_value="false"),
            Node(
                package="uav_landmine_ros",
                executable="mission_bridge",
                parameters=[{"backend_url": backend_url, "mission_id": mission_id}],
                output="screen",
            ),
            Node(package="uav_landmine_ros", executable="landmine_detector", output="screen"),
            Node(
                package="rviz2",
                executable="rviz2",
                arguments=["-d", PathJoinSubstitution([share, "rviz", "landmine.rviz"])],
                condition=IfCondition(LaunchConfiguration("rviz")),
            ),
        ]
    )
