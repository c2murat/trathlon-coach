# Triathlon Coach Product

## Purpose

Triathlon Coach helps amateur triathletes plan training, collect completed activities, monitor recovery, and understand whether training is progressing toward their races. It brings plans, actual sessions, subjective feedback, and coaching analysis into one personal workspace.

The primary user is an amateur triathlete balancing swimming, cycling, running, strength work, recovery, work, and family commitments. The product should favor clear guidance and sustainable consistency over elite-level complexity.

## Main user journeys

1. **Connect Strava:** the athlete authorizes access, sees granted permissions and connection status, and can disconnect at any time.
2. **Import historical activities:** the athlete starts an import, monitors progress and errors, and receives deduplicated swim, bike, run, and related activities.
3. **Receive new activities automatically:** Strava events trigger an idempotent synchronization; the athlete can see freshness and retry failures.
4. **View a training dashboard:** the athlete sees recent activity, planned sessions, training consistency, recovery signals, upcoming races, and data freshness.
5. **Create races and goals:** the athlete records race date, distance, priority, target, and notes so planning can work backward from meaningful events.
6. **Create and adjust a training plan:** the athlete schedules sport-specific and strength sessions, moves them around real-life availability, and reviews material adjustments before applying them.
7. **Compare planned and completed sessions:** the athlete links an activity to its planned workout and compares sport, duration, distance, intensity, structure, and subjective response.
8. **Record RPE, fatigue, sleep, and pain:** quick check-ins add context that device data cannot provide and allow corrections later.
9. **Receive weekly and post-workout analysis:** the athlete receives evidence-based summaries of adherence, volume, intensity, progression, and recovery, with uncertainty shown when data is incomplete.

## MVP

The MVP is the stable personal platform targeted by version 1.0:

- Personal athlete profile, goals, training zones, availability, and equipment.
- Secure Strava OAuth, historical import, webhook-based updates, sync status, and disconnect.
- PostgreSQL storage for normalized activities and synchronization records.
- Dashboard for recent training, upcoming sessions/races, and basic recovery context.
- Race and goal management.
- Planned swim, bike, run, and strength workouts in a training calendar.
- Planned-versus-completed matching and comparison.
- Manual RPE, fatigue, sleep, soreness/pain, stress, and illness inputs.
- Deterministic weekly and post-workout analysis with freshness and missing-data indicators.
- Athlete-controlled export and deletion of personal data.

## Future features

- Explainable AI coaching conversations and plan-adjustment proposals.
- Garmin integration and broader device/provider support.
- Google Calendar synchronization.
- Weather context for planning and completed sessions.
- Workout export to compatible devices and platforms.
- Richer periodization, advanced load models, notifications, and multi-athlete/coaching support.

Future features must not weaken consent, traceability, or athlete approval of material plan changes.

## Privacy and data deletion

- Collect only data required for stated product functions and clearly identify its source.
- Encrypt provider credentials and tokens; never expose them in logs, client responses, or AI prompts.
- Show connection scopes, synchronization status, data freshness, and applicable retention behavior.
- Let the athlete disconnect a provider without losing unrelated manually entered data.
- Let the athlete request export and permanent deletion of profile, activities, wellness entries, plans, recommendations, provider tokens, and derived metrics.
- Deletion must include dependent records and queued/retryable work, subject only to clearly disclosed operational backup retention.
- Record and surface deletion progress or failure; do not claim completion before all active stores are handled.
- Retain raw provider payloads only when necessary for replay or support and remove them under a defined retention policy.

## Health and safety statement

Triathlon Coach is a training-planning and informational tool, not a medical diagnostic tool. It must not diagnose, treat, or rule out medical conditions. Concerning symptoms, pain, injury, or illness should lead to conservative guidance and appropriate professional medical evaluation.
