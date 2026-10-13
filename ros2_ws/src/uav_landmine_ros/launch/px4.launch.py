"""PX4 read directly: the Micro XRCE-DDS Agent (PX4's uxrce_dds_client connects to it, on UDP port 8888) and px4_link,
which publishes /px4/fix and /px4/status and checks PX4 against the backend. The backend still flies the mission;
commands still go through it (/mission/start, /mission/control, /mission/fly of landmine.launch.py).

  ros2 launch uav_landmine_ros px4.launch.py                     # the agent and px4_link
  ros2 launch uav_landmine_ros px4.launch.py landmine:=true      # and the bridge, the detector and mission control
  ros2 launch uav_landmine_ros px4.launch.py agent:=false        # an agent is already running

ros2_ws/build.sh builds px4_msgs and the agent. PX4 must be on the same computer (here: WSL), since the agent's ROS
side uses shared memory: the participant PX4 asks the agent for is built from PX4's own XML, which leaves out the
default profile (config/fastdds_shm.xml), so the agent gets FASTDDS_BUILTIN_TRANSPORTS=SHM instead
(agent_transports:=DEFAULT where UDP works).
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from uav_landmine_ros.launching import dds_profile, shared_file


def generate_launch_description() -> LaunchDescription:
    params = LaunchConfiguration("params_file")
    backend_url = LaunchConfiguration("backend_url")
    return LaunchDescription(
        [
            *dds_profile(),
            DeclareLaunchArgument("backend_url", default_value="http://127.0.0.1:8000"),
            DeclareLaunchArgument("mission_id", default_value="0", description="0: the PX4 mission flying, or the last"),
            DeclareLaunchArgument("params_file", default_value=shared_file("config", "params.yaml")),
            DeclareLaunchArgument("port", default_value="8888", description="the agent's UDP port (PX4's uxrce_dds_port)"),
            DeclareLaunchArgument("agent", default_value="true", description="start the Micro XRCE-DDS Agent"),
            DeclareLaunchArgument("landmine", default_value="false", description="also landmine.launch.py"),
            DeclareLaunchArgument(
                "agent_transports", default_value="SHM", description="Fast DDS's built-in transports for the agent"
            ),
            ExecuteProcess(
                cmd=["MicroXRCEAgent", "udp4", "-p", LaunchConfiguration("port")],
                name="micro_xrce_dds_agent",
                additional_env={"FASTDDS_BUILTIN_TRANSPORTS": LaunchConfiguration("agent_transports")},
                output="screen",
                condition=IfCondition(LaunchConfiguration("agent")),
            ),
            Node(
                package="uav_landmine_ros",
                executable="px4_link",
                parameters=[params, {"backend_url": backend_url, "mission_id": LaunchConfiguration("mission_id")}],
                output="screen",
            ),
            IncludeLaunchDescription(
                shared_file("launch", "landmine.launch.py"),
                launch_arguments={"backend_url": backend_url, "params_file": params}.items(),
                condition=IfCondition(LaunchConfiguration("landmine")),
            ),
        ]
    )
