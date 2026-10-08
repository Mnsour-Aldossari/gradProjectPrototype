# A potential detection: never a confirmed mine until trained personnel verify it.
int64 id               # the backend's detection id; 0 for one found by the detector node
string method          # adaptive or baseline
string category        # high, suspect, clutter
string category_label  # High priority, Needs verification, Likely clutter
float64 latitude
float64 longitude
float64 x_m            # in the "survey" frame
float64 y_m
float64 confidence     # ranking score for verification, 0..1; not a probability
float64 peak_md
float64 peak_gpr
float64 est_depth_m    # NaN when the radar gave no depth
int32 n_hits
string explanation
string status          # pending, confirmed_by_team, false_alarm; empty for the detector node's
