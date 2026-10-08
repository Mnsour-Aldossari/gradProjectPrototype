# All potential detections of a mission at one moment (not a change): each message replaces the previous one.
std_msgs/Header header
string source      # "backend" (stored and verified there) or "ros_detector" (the detector node)
int64 mission_id
bool final         # the mission has ended and every reading was used
Detection[] detections
