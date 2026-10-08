# How PX4 stands, read from PX4 itself (uXRCE-DDS), not from the backend.
std_msgs/Header header
bool armed
bool landed            # PX4's land detector: on the ground
bool maybe_landed
uint8 nav_state        # PX4's vehicle_status.nav_state
string nav_state_name  # e.g. "auto_mission", "auto_rtl", "auto_land"
bool failsafe
float32 battery_remaining  # 0 to 1; -1 when PX4 does not know
bool position_valid
float64 latitude
float64 longitude
float32 altitude_amsl_m
