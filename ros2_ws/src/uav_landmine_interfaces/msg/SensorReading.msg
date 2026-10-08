# One metal-detector (MD) and ground-penetrating-radar (GPR) reading, as the backend stored it. Simulated data.
# header.frame_id is "survey": metres from the centre of the survey area, x east, y north.
std_msgs/Header header
int64 mission_id
int64 id            # the backend's reading id; ids grow in the order the readings were taken
float64 t_s         # flight time of the reading
float64 latitude
float64 longitude
float64 x_m
float64 y_m
float64 height_m    # sensor height above the ground
float64 md          # metal detector, normalised units
float64 gpr_amp     # radar amplitude, normalised units
float64 gpr_twt_ns  # radar two-way travel time of the strongest reflector
