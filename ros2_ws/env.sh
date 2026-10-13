# Source this in a WSL terminal to use the project's ROS 2 packages (after ros2_ws/build.sh):
#   source /mnt/c/<path to the project>/ros2_ws/env.sh
# It also selects Fast DDS over shared memory, as landmine.launch.py does, so ros2 topic / ros2 bag see the nodes.
ws="${UAV_ROS_WS:-$HOME/uav_landmine_ws}"
source "$ws/install/setup.bash"
export FASTRTPS_DEFAULT_PROFILES_FILE="${FASTRTPS_DEFAULT_PROFILES_FILE:-$ws/install/uav_landmine_ros/share/uav_landmine_ros/config/fastdds_shm.xml}"
