# Supplementary Solver Logs

This directory contains CBC logs that are useful for solver scalability
context but cannot be matched safely to a solver result JSON.

`medium_risk_0.5_cost_0.3_time_0.2/cbc_log_medium_R0.5_C0.3_11h.txt` is a
separate Medium risk-oriented run. Its final recorded progress line is at about
40,126 seconds with an incumbent of 0.26023133 and a best bound of 0.20166002.
The current solver JSON for this scenario has a different objective and an
aggregated runtime of about 17,996 seconds. Therefore, this log must not be
used to claim the termination status, bound, gap, or exact runtime of that JSON
solution.
