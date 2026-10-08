#!/usr/bin/env bash
# Builds the project's ROS 2 packages (ROS 2 Jazzy, e.g. Ubuntu 24.04 in WSL) in a workspace of their own,
# ~/uav_landmine_ws by default (UAV_ROS_WS), whose src links to this checkout. Extra arguments go to colcon build.
#   bash ros2_ws/build.sh            then:  source ros2_ws/env.sh
# For the direct link to PX4 it also builds PX4's messages and the Micro XRCE-DDS Agent, from source folders that
# stay as they are (linked, never changed): UAV_PX4_MSGS_SRC (px4_msgs at PX4's version, v1.17.0 for PX4 v1.17.0) and
# UAV_XRCE_AGENT_SRC (Micro-XRCE-DDS-Agent v2.4.3), by default in ~/dev/upstream. Without them that part is skipped.
set -eo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ws="${UAV_ROS_WS:-$HOME/uav_landmine_ws}"
source "/opt/ros/${ROS_DISTRO:-jazzy}/setup.bash"
mkdir -p "$ws/src"
for pkg in "$here"/src/*/; do
  ln -sfn "${pkg%/}" "$ws/src/$(basename "$pkg")"
done
for src in "${UAV_PX4_MSGS_SRC:-$HOME/dev/upstream/px4_msgs}" "${UAV_XRCE_AGENT_SRC:-$HOME/dev/upstream/Micro-XRCE-DDS-Agent}"; do
  if [ -f "$src/package.xml" ] || [ -f "$src/CMakeLists.txt" ]; then
    ln -sfn "$src" "$ws/src/$(basename "$src")"
  else
    echo "Not found, the direct link to PX4 is not built: $src"
  fi
done
cd "$ws"
# The agent uses the Fast DDS and Fast CDR that come with ROS, so its build downloads nothing; its console log is off
# (Ubuntu 24.04's spdlog cannot build the agent's v2.4.3 log lines).
colcon build --symlink-install --cmake-args -DUAGENT_SUPERBUILD=OFF -DUAGENT_USE_SYSTEM_FASTDDS=ON \
  -DUAGENT_USE_SYSTEM_FASTCDR=ON -DUAGENT_P2P_PROFILE=OFF \
  -DUAGENT_LOGGER_PROFILE=OFF -Wno-dev "$@"
echo "Built in $ws. Next: source $here/env.sh"
