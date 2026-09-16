# D.1 audit and descriptive policy

Baseline: `sprint-0.8a-authentication`, local/tracking/remote
`3508844f7d16555b270920f63300d619309d657d`; initial untracked folders only
`backups/` and `informe/` (excluded).

`domains/training_status/calculators.py` uses daily load L and exponential
factors `1-exp(-1/42)` for fitness and `1-exp(-1/7)` for fatigue. Each state
updates `previous + (L-previous)*factor`; form is fitness minus fatigue on the
same day. Missing daily source load becomes zero **in the existing calculator**;
D.1 never imputes missing persisted status days. Outputs are rounded to two
decimals, while internal accumulation retains precision. Warm-up is the first
84 history days. The application persists complete daily rows by athlete,
timezone and all three algorithm versions.

The existing page requests a 4/8/12-week series and latest status separately,
uses the browser timezone, and shows a graph plus numeric cards. Each read is
one SELECT (plus membership authorization per HTTP request). No trend/delta or
descriptive form bands exist in Training Status. Planning has a -10 form floor
for its own budget policy; it is not an appropriate descriptive classification
and is deliberately not imported.

## D.1 policy (presentation only, not clinical or training limits)

- `short_term`: compare last value with exactly seven days earlier, requiring all
  eight daily observations. `broader_context`: compare with 21 days earlier,
  requiring all 22 daily observations. Missing broader context does not discard
  valid seven-day evidence. No weighting, interpolation, missing-day fill or smoothing.
- `recent`: inspect the last three days (four observations) within a complete
  seven-day history. Stable means their full range is <=1 point. Rising/falling
  requires a net change >1/<-1 and all daily movements in that direction (plateaus
  allowed). Otherwise report mixed, never hide an oscillation as a sustained trend.
- A recent turn requires the preceding four-day net change (day -7 to day -3)
  outside the same +/-1 band and the opposite recent direction. Recovery turn
  additionally requires stored form to improve by >1 during those three days.
- A latest row older than one day relative to cutoff cannot describe current
  trends. Preserve its factual values/date, but report insufficient interpretation.
- Delta in [-1,+1] points is stable; >1 rising; <-1 falling in either horizon.
  Fatigue delta >=10 is marked rising fast over seven days; the same absolute
  magnitude over 21 days is presented as a clear increase, not as a daily rate.
  These are conservative UI deadbands, not physiological limits.
- Form: <=-20 highly loaded; (-20,-5) loaded; [-5,5] balanced; (5,20) fresh;
  >=20 very fresh. Use the **stored** form, never recompute it from rounded values.
- Notable relationship: fatigue is rising and its delta exceeds fitness delta by >1
  point; fatigue falling with stable/rising fitness; both stable; both falling.
- Overall precedence: insufficient; highly loaded; loaded; both falling
  (reduced load, without choosing recovery vs detraining); recovery trend;
  fresh/very fresh; fitness rising (building); balanced.
- Warm-up remains visible and is included as metadata/reason; it does not turn
  eight observed daily values into a claim of fully consolidated fitness.
- Empty, sparse, stale or mixed-source histories cannot invent a trend.

New GET `/training-status/overview` groups series, latest and interpretation.
It reuses existing read methods, two constant data SELECTs, with no extra SQL
for interpretation. Existing endpoints remain compatible. The latest-read
method gains an optional cutoff filter; its existing callers keep their behavior.
Requested end date is the explicit interpretation cutoff; no future dates.
The assembler retrieves at least 21 days plus the one-day freshness allowance
without another query. Frontend retains the chart, places the summary immediately
after it, and maps backend enums to short Spanish copy. Summary prioritizes the
21-day context and recent direction; miniinterpretations retain the seven-day
comparison and qualify it when a recent fatigue turn is present.
No LLM, extra physiological inputs, persistence or Planning coupling.
