#!/usr/bin/env bash
# Builds the project's ROS 2 packages (ROS 2 Jazzy, e.g. Ubuntu 24.04 in WSL) in a workspace of their own,
# ~/uav_landmine_ws by default (UAV_ROS_WS), whose src links to this checkout. Extra arguments go to colcon build.
#   bash ros2_ws/build.sh            then:  source ~/uav_landmine_ws/install/setup.bash
set -eo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ws="${UAV_ROS_WS:-$HOME/uav_landmine_ws}"
source "/opt/ros/${ROS_DISTRO:-jazzy}/setup.bash"
mkdir -p "$ws/src"
for pkg in "$here"/src/*/; do
  ln -sfn "${pkg%/}" "$ws/src/$(basename "$pkg")"
done
cd "$ws"
colcon build --symlink-install "$@"
echo "Built in $ws. Next: source $ws/install/setup.bash"
