"""What the launch files share."""

import os

from launch.actions import SetEnvironmentVariable
from launch.substitutions import PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def share():
    return FindPackageShare("uav_landmine_ros")


def shared_file(*parts: str) -> PathJoinSubstitution:
    return PathJoinSubstitution([share(), *parts])


def dds_profile() -> list:
    """Fast DDS over shared memory (config/fastdds_shm.xml says why), unless another profile is chosen."""
    if "FASTRTPS_DEFAULT_PROFILES_FILE" in os.environ:
        return []
    return [SetEnvironmentVariable("FASTRTPS_DEFAULT_PROFILES_FILE", shared_file("config", "fastdds_shm.xml"))]
