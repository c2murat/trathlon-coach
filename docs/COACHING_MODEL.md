# Initial Coaching Model

## Purpose and boundaries

The initial coaching model turns planned workouts, completed activities, athlete zones, and subjective recovery inputs into practical training summaries. It prioritizes consistency, progressive overload, recovery, specificity, and transparent uncertainty for an amateur triathlete.

This document defines concepts and behavior, not production formulas. Algorithms, thresholds, and validation evidence must be versioned before implementation. The model supports training decisions; it does not diagnose or replace a qualified coach or healthcare professional.

## Sport principles

### Swimming

Evaluate consistency, duration/distance, pool or open-water context, stroke, set completion, pace relative to current zones or critical swim speed, rest, technique intent, and RPE. Do not treat GPS open-water distance or pace as equally reliable as measured pool data.

### Cycling

Evaluate duration, distance, terrain/elevation, power when available, heart rate, cadence, time in zones, workout structure, and RPE. Power is useful for external work; heart rate and RPE add internal-response context. Indoor and outdoor sessions may not be directly comparable.

### Running

Evaluate duration, distance, surface, elevation, pace, heart rate, time in zones, structure, and RPE. Interpret pace in context: heat, hills, wind, trail conditions, fatigue, and GPS quality can make raw pace misleading.

### Strength

Evaluate movement pattern, exercises, sets, repetitions, external load, rest, RPE or repetitions in reserve, technique completion, and soreness response. Strength load should not be reduced to endurance distance, and interference with key swim/bike/run sessions must be considered.

## Intensity measures

- **Heart-rate zones:** athlete-specific zones based on a declared method and effective-dated threshold or maximum/resting values. Heart rate lags short efforts and is affected by heat, hydration, fatigue, medication, sensor quality, and cardiac drift.
- **Power zones:** primarily cycling zones based on an effective-dated tested/estimated threshold such as FTP. Device calibration, position, environment, and test method matter. Running power, if supported later, is not assumed equivalent to cycling power.
- **Pace zones:** sport- and context-specific zones based on current swim or run thresholds. Pool length, open water, terrain, weather, and measurement method must remain visible.
- **RPE:** athlete-reported whole-session or segment difficulty on a documented scale, initially 1-10. It remains valuable when device data is absent and may reveal unusual strain when device metrics look normal.
- **Session RPE:** a possible internal-load measure combining session duration and post-session RPE. Its exact calculation, collection timing, scale, and units must be defined and versioned before use.

Zones must retain their source, method, effective date, and uncertainty. Analysis uses the zones valid on the workout date and does not silently rewrite history when zones change.

## Planned versus completed workouts

Comparison starts only after a completed activity is linked to a planned workout, automatically with confidence or manually by the athlete. It should compare:

- sport and workout purpose;
- start time and completion status;
- duration and distance;
- prescribed versus observed intensity and time in zones;
- interval/set completion where compatible data exists;
- terrain or environment where relevant;
- RPE and recovery response.

Results should describe adherence and meaningful deviations, not reduce every workout to pass/fail. A shorter easy session may meet its purpose; extra volume may be inappropriate. Missing streams, unmatched intervals, uncertain zones, sensor errors, and low-confidence matches must be shown. The canonical completed activity is never altered to make it agree with the plan.

## Weekly analysis

### Volume

Summarize frequency, duration, and sport-appropriate distance for swimming, cycling, running, and strength. Show combined duration carefully, while preserving per-sport detail because kilometers and physiological demands are not interchangeable.

### Intensity distribution

Report time or session distribution across the athlete's current zone model, plus RPE when available. State which signal was used (power, pace, heart rate, or prescription), its coverage, and conflicts between signals. Avoid claiming precision when streams or zones are missing.

### Progression

Compare recent weeks with an appropriate prior window for volume, frequency, intensity, long-session demand, and recovery. Favor gradual, sustained progression and planned recovery over fixed universal percentage rules. Account for race proximity, training age, interruptions, illness, pain, and discipline-specific changes. One exceptional workout should not drive a major plan change.

## Future load metrics

Future versions may calculate:

- **TSS (Training Stress Score or analogous stress):** estimated session stress relative to a threshold.
- **CTL (Chronic Training Load):** a longer-term weighted load trend, often interpreted as fitness context.
- **ATL (Acute Training Load):** a shorter-term weighted load trend, often interpreted as fatigue context.
- **TSB (Training Stress Balance):** the relationship between chronic and acute load, often interpreted as freshness context.

These are model outputs, not direct measurements of fitness, fatigue, readiness, or health. Results depend on valid thresholds, complete activity data, chosen time constants, and the underlying stress model. Scores from power, pace, heart rate, session RPE, different sports, or different vendors are not automatically equivalent. Strength and technical swim stress are especially easy to underrepresent. The platform must expose method/version, inputs, coverage, freshness, and limitations and must not present a single number as a training decision.

## Recovery inputs

Recovery context combines trends and athlete reports rather than treating any one input as definitive:

- sleep duration and perceived quality;
- general fatigue;
- muscle soreness and location when available;
- life stress;
- pain, location, severity, onset, and change when voluntarily reported;
- illness symptoms/status;
- future optional resting heart rate and HRV with baseline and device context.

The athlete can correct entries and see missing/stale data. Concerning inputs trigger conservative safety messaging, not a hidden readiness override or diagnosis.

## Safety rules

1. Never diagnose, rule out a condition, or present analysis as medical advice.
2. Never recommend training through chest pain, severe or rapidly worsening symptoms, acute injury, or illness. Recommend stopping or avoiding training and seeking appropriate urgent or professional medical help according to symptom severity.
3. Avoid aggressive volume, intensity, or plan changes based on one workout or one unusual measurement.
4. Flag uncertainty, conflicting signals, stale zones, missing data, and low-confidence activity matches.
5. Prefer conservative guidance when safety-relevant context is incomplete.
6. Require athlete review and explicit acceptance before a material recommendation changes planned training.

## Deterministic calculations and AI interpretation

Deterministic processing owns reproducible facts and rules: totals, zone time, planned/completed differences, trend windows, data-quality flags, calculation versions, and safety gates. Given the same stored inputs and version, it should produce the same result.

AI may later translate those results into readable interpretation, identify questions, or propose options. It must not invent measurements, bypass safety rules, silently mutate the plan, or obscure contradictory evidence.

Every AI recommendation must be explainable and based on stored evidence. Its record should identify the relevant workouts, activities, recovery entries, races, zones, deterministic metrics, data freshness, missing inputs, prompt/model version, and reasoning summary. The athlete must be able to inspect that evidence and accept or reject any proposed change.
