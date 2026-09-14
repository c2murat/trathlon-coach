# C.7 capability reassessment audit

Baseline: `sprint-0.8a-authentication`, local/tracking/remote HEAD
`d3ad388d62b1256383199ebbbfd1d7fc494cbbfa`. Initial tree contains only
untracked `backups/` and `informe/`; neither belongs to this change.

## Production primitives and boundaries

`AthletePerformanceProfileVersion` supplies the numeric FTP (watts), running
threshold (seconds/km) and CSS (seconds/100 m) used by both Planning and
`AthleteCapabilityContext.performance_references`. Its effective date, ID,
origin and algorithm version are available; per-value quality is **not**.
`AthletePerformanceReference` separately has quality and provenance. Those
records do not populate the profile's numeric fields and cannot be substituted
or used to claim quality for a different profile value. Derived zones are
reference-based classifications, not new measurements or assessment protocols.
No productive FTP test, threshold time trial, CSS test or assessment protocol
was found in the application. No protocol will be invented.

`workout_builder._family` and `_resolved_target` explicitly anchor quality:

| Sport | Session types | Reference | Unit |
|---|---|---|---|
| cycling | BIKE_TEMPO, BIKE_THRESHOLD, BIKE_INTERVAL | FTP | watts |
| running | RUN_TEMPO, RUN_THRESHOLD, RUN_INTERVAL | threshold_pace | seconds_per_km |
| swimming | SWIM_THRESHOLD, SWIM_INTERVAL | CSS | seconds_per_100m |

This is an eligibility mapping, never proof of anchoring by itself. C.1 only
retains compared bounds/unit, losing the original target's reference metadata.
C.7 therefore requires an immutable, athlete/session/date-scoped snapshot of
the actual first repeated work target (the same block C.1 compares), with
explicit reference, reference value, resolved bounds and unit. Bounds must
match C.1 exactly. The reference value must equal the current profile and the
session must not predate its effective date. Targets carrying capability or
Planning adaptation are conservatively excluded. Similarity, zones and overlap
are not anchoring evidence. Missing provenance fails closed.

## Architecture and query decision

C.7 adds independent domain and application modules; C.1--C.6 and Planning
remain untouched. The standalone assembler reuses C.1 (at most three queries)
and C.2. When capability is absent, **one** additional constant SQL statement
loads the latest profile and window-scoped workout provenance together using
outer joins; no activity/lap/stream queries are added. With a supplied scoped
capability/reference context it performs zero additional queries and accepts
already available target snapshots. If those snapshots are absent, it reports
insufficient anchored evidence, rather than silently issuing extra queries or
guessing provenance. Callers retaining workouts can build snapshots in memory.

## Evidence policy decision

Reuse C.2 interpretation on only the explicitly anchored subset: at least three
HIGH/MEDIUM structured comparisons, at least two recent, directional fraction
0.67, and its existing extreme-overshoot guards. These thresholds only establish
grounds for review; they do not estimate a physiological value. Additional C.7
guards reject unknown/unmatched majorities among mapped quality sessions,
recent partials, mixed/adverse evidence, and repeated use of one source activity.
Absent activity provenance cannot establish independent repetition. C.2's
duration-only MAINTAIN cannot establish adequate C.7 evidence. Reference age is
reported in days only, without an invented expiration threshold or confidence
bonus. Recent is age <28; background is 28--83; the 84-day window excludes cutoff
and future sessions. The inclusive C.1 lower boundary (exact age 84) is retained
in the factual session count but does not contribute to either evidence band.
No weighting. C.2 is reinterpreted on the anchored subset
in memory, so unrelated sessions cannot create a capability signal.

C.7 is advisory and outside all Planning, preview and workout fingerprints.
It does not consume C.3 directions, C.6 ladders or C.5 failures. C.6's conclusion
that no safe production ladder exists remains unchanged.
