# The mission the bridge follows, sent again when it changes. x = y = 0 in the "survey" frame is the origin.
int64 id
string name
string status             # planned, running, completed, stopped, failed
string sensor_collection  # complete, partial, failed, not_started; empty when not recorded
string soil_type          # dry_sand, wet_clay, mineralized_rocky
float64 altitude_m        # planned sensor height above the ground
float64 speed_mps
float64 line_spacing_m
float64 sample_period_s   # time between readings that the detector's windows assume
float64 origin_latitude   # centre of the survey area
float64 origin_longitude
float64[] area_latitude
float64[] area_longitude
float64 progress          # share of the survey path flown, 0..1
int64 readings_published  # readings sent on /sensors/readings so far
bool readings_complete    # the mission has ended and every reading has been sent
