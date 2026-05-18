#!/bin/bash
source /opt/ros/humble/setup.bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE="$(dirname "$0")/fastdds_no_shm.xml"
export ROS_DOMAIN_ID=130
exec python3 "$(dirname "$0")/publish_robot_description.py"
