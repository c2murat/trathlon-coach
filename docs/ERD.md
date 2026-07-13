# Triathlon Coach Entity-Relationship Diagrams

These diagrams describe the conceptual relationships in [DATA_MODEL.md](DATA_MODEL.md). They are split by logical area for readability. UUID fields are internal keys; fields ending in `external_id` are alternate provider identities, never primary keys. The diagrams do not prescribe SQLAlchemy or migration implementation.

Mermaid cardinality legend: `||` exactly one, `o|` zero or one, `|{` one or more, and `o{` zero or more.

## Complete conceptual model: identity and integrations

```mermaid
erDiagram
    USER ||--o| ATHLETE_PROFILE : has
    USER ||--o| COACH_PROFILE : has
    COACH_PROFILE ||--o{ COACH_ATHLETE_RELATIONSHIP : requests
    ATHLETE_PROFILE ||--o{ COACH_ATHLETE_RELATIONSHIP : grants
    ATHLETE_PROFILE ||--|| ATHLETE_SETTINGS : configures
    ATHLETE_PROFILE ||--o{ INTEGRATION_ACCOUNT : connects
    INTEGRATION_ACCOUNT ||--o| OAUTH_CREDENTIAL : secures
    INTEGRATION_ACCOUNT ||--o{ SYNC_JOB : runs
    INTEGRATION_ACCOUNT o|--o{ WEBHOOK_EVENT : receives
    SYNC_JOB o|--o{ WEBHOOK_EVENT : processes
    USER ||--o{ NOTIFICATION : receives
    USER o|--o{ AUDIT_EVENT : performs
    ATHLETE_PROFILE o|--o{ AUDIT_EVENT : concerns

    USER {
        uuid id PK
        text email UK
        text auth_subject UK
        text status
        timestamptz created_at
        timestamptz deleted_at
    }
    ATHLETE_PROFILE {
        uuid id PK
        uuid user_id FK,UK
        text timezone
        text unit_system
        timestamptz created_at
    }
    COACH_PROFILE {
        uuid id PK
        uuid user_id FK,UK
        text display_name
        text verification_status
    }
    COACH_ATHLETE_RELATIONSHIP {
        uuid id PK
        uuid coach_profile_id FK
        uuid athlete_id FK
        text status
        text_array scopes
        timestamptz accepted_at
        timestamptz revoked_at
    }
    ATHLETE_SETTINGS {
        uuid id PK
        uuid athlete_id FK,UK
        text timezone
        text display_unit_system
        smallint week_starts_on
    }
    INTEGRATION_ACCOUNT {
        uuid id PK
        uuid athlete_id FK
        text provider
        text external_account_id
        text status
        timestamptz last_synced_at
    }
    OAUTH_CREDENTIAL {
        uuid id PK
        uuid integration_account_id FK,UK
        bytea access_token_encrypted
        bytea refresh_token_encrypted
        timestamptz expires_at
        text key_version
    }
    SYNC_JOB {
        uuid id PK
        uuid athlete_id FK
        uuid integration_account_id FK
        text job_type
        text idempotency_key
        text status
        timestamptz created_at
    }
    WEBHOOK_EVENT {
        uuid id PK
        uuid integration_account_id FK
        uuid sync_job_id FK
        text provider
        text deduplication_key
        text status
        timestamptz received_at
    }
    NOTIFICATION {
        uuid id PK
        uuid user_id FK
        uuid athlete_id FK
        text notification_type
        text channel
        text status
    }
    AUDIT_EVENT {
        uuid id PK
        uuid actor_user_id FK
        uuid athlete_id FK
        text action
        text entity_type
        uuid entity_id
        timestamptz occurred_at
    }
```

`CoachAthleteRelationship` is the consent boundary, not merely a membership join. `OAuthCredential` is isolated one-to-one from the athlete-visible integration record. Webhooks form an idempotent inbox and may create a retryable sync job. Notifications and coach collaboration are not MVP requirements, but their ownership boundaries are reserved.

## Complete conceptual model: planning, activities, and equipment

```mermaid
erDiagram
    ATHLETE_PROFILE ||--o{ TRAINING_ZONE_SET : owns
    TRAINING_ZONE_SET ||--|{ TRAINING_ZONE : contains
    TRAINING_ZONE_SET o|--o{ TRAINING_ZONE_SET : supersedes
    ATHLETE_PROFILE ||--o{ RACE : schedules
    RACE ||--o{ RACE_GOAL : defines
    RACE o|--o{ TRAINING_PLAN : targets
    ATHLETE_PROFILE ||--o{ TRAINING_PLAN : owns
    TRAINING_PLAN ||--|{ TRAINING_WEEK : divides
    TRAINING_WEEK ||--o{ PLANNED_WORKOUT : schedules
    TRAINING_PLAN ||--o{ PLANNED_WORKOUT : contains
    PLANNED_WORKOUT ||--o{ PLANNED_WORKOUT_STEP : prescribes
    PLANNED_WORKOUT_STEP o|--o{ PLANNED_WORKOUT_STEP : groups
    TRAINING_ZONE o|--o{ PLANNED_WORKOUT_STEP : targets
    ATHLETE_PROFILE ||--o{ COMPLETED_ACTIVITY : performs
    COMPLETED_ACTIVITY ||--o{ ACTIVITY_LAP : contains
    COMPLETED_ACTIVITY ||--o{ ACTIVITY_STREAM : has
    COMPLETED_ACTIVITY ||--|{ ACTIVITY_SOURCE : originates_from
    INTEGRATION_ACCOUNT o|--o{ ACTIVITY_SOURCE : supplies
    PLANNED_WORKOUT ||--o{ PLANNED_COMPLETED_MATCH : participates
    COMPLETED_ACTIVITY ||--o{ PLANNED_COMPLETED_MATCH : participates
    ATHLETE_PROFILE ||--o{ EQUIPMENT : owns
    EQUIPMENT ||--o{ EQUIPMENT_USAGE : accumulates
    COMPLETED_ACTIVITY ||--o{ EQUIPMENT_USAGE : records
    EQUIPMENT o|--o{ PLANNED_WORKOUT : preferred_for

    ATHLETE_PROFILE {
        uuid id PK
        uuid user_id FK
        text timezone
    }
    TRAINING_ZONE_SET {
        uuid id PK
        uuid athlete_id FK
        text sport
        text intensity_reference
        date effective_from
        date effective_to
        uuid supersedes_zone_set_id FK
    }
    TRAINING_ZONE {
        uuid id PK
        uuid zone_set_id FK
        smallint position
        numeric lower_value
        numeric upper_value
        text unit
    }
    RACE {
        uuid id PK
        uuid athlete_id FK
        text name
        text sport
        timestamptz start_at
        text timezone
        text priority
    }
    RACE_GOAL {
        uuid id PK
        uuid race_id FK
        text goal_type
        smallint priority_order
        numeric target_value
        text unit
    }
    TRAINING_PLAN {
        uuid id PK
        uuid athlete_id FK
        uuid target_race_id FK
        date start_date
        date end_date
        text status
    }
    TRAINING_WEEK {
        uuid id PK
        uuid training_plan_id FK
        smallint week_number
        date start_date
        date end_date
    }
    PLANNED_WORKOUT {
        uuid id PK
        uuid athlete_id FK
        uuid training_plan_id FK
        uuid training_week_id FK
        uuid equipment_id FK
        text sport
        timestamptz scheduled_start_at
        text status
    }
    PLANNED_WORKOUT_STEP {
        uuid id PK
        uuid planned_workout_id FK
        uuid parent_step_id FK
        uuid zone_id FK
        smallint position
        text step_type
        text target_type
    }
    COMPLETED_ACTIVITY {
        uuid id PK
        uuid athlete_id FK
        text sport
        timestamptz start_at
        bigint elapsed_time_s
        double distance_m
        smallint rpe
    }
    ACTIVITY_LAP {
        uuid id PK
        uuid completed_activity_id FK
        integer lap_index
        text external_lap_id
        bigint elapsed_time_s
        double distance_m
    }
    ACTIVITY_STREAM {
        uuid id PK
        uuid completed_activity_id FK
        text stream_type
        text storage_kind
        bigint sample_count
        text object_key
    }
    ACTIVITY_SOURCE {
        uuid id PK
        uuid completed_activity_id FK
        uuid integration_account_id FK
        text provider
        text external_activity_id
        text source_file_hash
    }
    INTEGRATION_ACCOUNT {
        uuid id PK
        uuid athlete_id FK
        text provider
        text external_account_id
    }
    PLANNED_COMPLETED_MATCH {
        uuid id PK
        uuid athlete_id FK
        uuid planned_workout_id FK
        uuid completed_activity_id FK
        text match_method
        text status
        timestamptz reversed_at
    }
    EQUIPMENT {
        uuid id PK
        uuid athlete_id FK
        text equipment_type
        text name
        text status
        text external_equipment_id
    }
    EQUIPMENT_USAGE {
        uuid id PK
        uuid athlete_id FK
        uuid equipment_id FK
        uuid completed_activity_id FK
        double distance_m
        bigint duration_s
        timestamptz removed_at
    }
```

A plan optionally targets a race and groups weeks/workouts. A completed activity never belongs to a plan directly. The reversible match entity links plan to execution and permits suggested, confirmed, and reversed states. Activity sources hold external identities; equipment usage is derived from activity assignments rather than a mutable total.

## Complete conceptual model: wellness, metrics, and coaching

```mermaid
erDiagram
    ATHLETE_PROFILE ||--o{ WELLNESS_ENTRY : records
    ATHLETE_PROFILE ||--o{ INJURY_OR_PAIN_ENTRY : records
    COMPLETED_ACTIVITY o|--o{ INJURY_OR_PAIN_ENTRY : contextualizes
    ATHLETE_PROFILE ||--o{ RECOVERY_METRIC : receives
    ATHLETE_PROFILE ||--o{ DAILY_TRAINING_METRIC : receives
    ATHLETE_PROFILE ||--o{ WEEKLY_TRAINING_METRIC : receives
    TRAINING_ZONE_SET o|--o{ DAILY_TRAINING_METRIC : interprets
    TRAINING_ZONE_SET o|--o{ WEEKLY_TRAINING_METRIC : interprets
    ATHLETE_PROFILE ||--o{ COACHING_RECOMMENDATION : receives
    COACHING_RECOMMENDATION ||--|{ COACHING_EVIDENCE : cites

    ATHLETE_PROFILE {
        uuid id PK
        uuid user_id FK
        text timezone
    }
    WELLNESS_ENTRY {
        uuid id PK
        uuid athlete_id FK
        date local_date
        bigint sleep_duration_s
        smallint fatigue
        smallint soreness
        smallint stress
        text illness_status
    }
    INJURY_OR_PAIN_ENTRY {
        uuid id PK
        uuid athlete_id FK
        uuid related_activity_id FK
        text entry_type
        text body_location
        smallint severity
        timestamptz onset_at
        text status
    }
    COMPLETED_ACTIVITY {
        uuid id PK
        uuid athlete_id FK
        text sport
        timestamptz start_at
    }
    RECOVERY_METRIC {
        uuid id PK
        uuid athlete_id FK
        date local_date
        text metric_type
        numeric value
        text algorithm_version
        timestamptz calculated_at
    }
    DAILY_TRAINING_METRIC {
        uuid id PK
        uuid athlete_id FK
        uuid zone_set_id FK
        date local_date
        text sport_scope
        text metric_type
        numeric value
        text algorithm_version
    }
    WEEKLY_TRAINING_METRIC {
        uuid id PK
        uuid athlete_id FK
        uuid zone_set_id FK
        date week_start_date
        text sport_scope
        text metric_type
        numeric value
        text algorithm_version
    }
    TRAINING_ZONE_SET {
        uuid id PK
        uuid athlete_id FK
        text sport
        text intensity_reference
        date effective_from
    }
    COACHING_RECOMMENDATION {
        uuid id PK
        uuid athlete_id FK
        text recommendation_type
        text generator_type
        text status
        text model_name
        text prompt_version
        timestamptz created_at
    }
    COACHING_EVIDENCE {
        uuid id PK
        uuid recommendation_id FK
        text evidence_type
        uuid evidence_entity_id
        text relationship
        text input_hash
    }
```

Wellness and pain are source evidence, while recovery/daily/weekly metric rows are reproducible deterministic outputs with algorithm versions. Recommendations are interpretations or proposals and cannot masquerade as deterministic metrics. Every future AI recommendation has one or more evidence links; access to each link is limited by the source evidence's privacy class.

## Simplified MVP-only diagram

This view omits future coach/AI records, post-MVP streams/notifications, and most operational detail. It shows the minimum product path from one user through planning, synchronization, completed training, recovery, and analysis.

```mermaid
erDiagram
    USER ||--|| ATHLETE_PROFILE : owns
    ATHLETE_PROFILE ||--|| ATHLETE_SETTINGS : configures
    ATHLETE_PROFILE ||--o{ INTEGRATION_ACCOUNT : connects
    INTEGRATION_ACCOUNT ||--o| OAUTH_CREDENTIAL : secures
    INTEGRATION_ACCOUNT ||--o{ SYNC_JOB : synchronizes
    INTEGRATION_ACCOUNT ||--o{ WEBHOOK_EVENT : receives
    ATHLETE_PROFILE ||--o{ TRAINING_ZONE_SET : versions
    TRAINING_ZONE_SET ||--|{ TRAINING_ZONE : contains
    ATHLETE_PROFILE ||--o{ RACE : schedules
    RACE ||--o{ RACE_GOAL : defines
    ATHLETE_PROFILE ||--o{ TRAINING_PLAN : owns
    RACE o|--o{ TRAINING_PLAN : targets
    TRAINING_PLAN ||--|{ TRAINING_WEEK : divides
    TRAINING_WEEK ||--o{ PLANNED_WORKOUT : schedules
    PLANNED_WORKOUT ||--o{ PLANNED_WORKOUT_STEP : prescribes
    ATHLETE_PROFILE ||--o{ COMPLETED_ACTIVITY : performs
    COMPLETED_ACTIVITY ||--o{ ACTIVITY_LAP : contains
    COMPLETED_ACTIVITY ||--|{ ACTIVITY_SOURCE : originates_from
    PLANNED_WORKOUT ||--o{ PLANNED_COMPLETED_MATCH : links
    COMPLETED_ACTIVITY ||--o{ PLANNED_COMPLETED_MATCH : links
    ATHLETE_PROFILE ||--o{ EQUIPMENT : owns
    EQUIPMENT ||--o{ EQUIPMENT_USAGE : accumulates
    COMPLETED_ACTIVITY ||--o{ EQUIPMENT_USAGE : records
    ATHLETE_PROFILE ||--o{ WELLNESS_ENTRY : records
    ATHLETE_PROFILE ||--o{ INJURY_OR_PAIN_ENTRY : records
    ATHLETE_PROFILE ||--o{ RECOVERY_METRIC : derives
    ATHLETE_PROFILE ||--o{ DAILY_TRAINING_METRIC : derives
    ATHLETE_PROFILE ||--o{ WEEKLY_TRAINING_METRIC : derives
    USER ||--o{ AUDIT_EVENT : performs

    USER {
        uuid id PK
    }
    ATHLETE_PROFILE {
        uuid id PK
        uuid user_id FK
    }
    ATHLETE_SETTINGS {
        uuid id PK
        uuid athlete_id FK
    }
    INTEGRATION_ACCOUNT {
        uuid id PK
        uuid athlete_id FK
        text external_account_id
    }
    OAUTH_CREDENTIAL {
        uuid id PK
        uuid integration_account_id FK
    }
    SYNC_JOB {
        uuid id PK
        uuid integration_account_id FK
    }
    WEBHOOK_EVENT {
        uuid id PK
        text deduplication_key UK
    }
    TRAINING_ZONE_SET {
        uuid id PK
        uuid athlete_id FK
    }
    TRAINING_ZONE {
        uuid id PK
        uuid zone_set_id FK
    }
    RACE {
        uuid id PK
        uuid athlete_id FK
    }
    RACE_GOAL {
        uuid id PK
        uuid race_id FK
    }
    TRAINING_PLAN {
        uuid id PK
        uuid athlete_id FK
    }
    TRAINING_WEEK {
        uuid id PK
        uuid training_plan_id FK
    }
    PLANNED_WORKOUT {
        uuid id PK
        uuid athlete_id FK
    }
    PLANNED_WORKOUT_STEP {
        uuid id PK
        uuid planned_workout_id FK
    }
    COMPLETED_ACTIVITY {
        uuid id PK
        uuid athlete_id FK
    }
    ACTIVITY_LAP {
        uuid id PK
        uuid completed_activity_id FK
    }
    ACTIVITY_SOURCE {
        uuid id PK
        uuid completed_activity_id FK
        text external_activity_id
    }
    PLANNED_COMPLETED_MATCH {
        uuid id PK
        uuid planned_workout_id FK
        uuid completed_activity_id FK
    }
    EQUIPMENT {
        uuid id PK
        uuid athlete_id FK
    }
    EQUIPMENT_USAGE {
        uuid id PK
        uuid equipment_id FK
        uuid completed_activity_id FK
    }
    WELLNESS_ENTRY {
        uuid id PK
        uuid athlete_id FK
    }
    INJURY_OR_PAIN_ENTRY {
        uuid id PK
        uuid athlete_id FK
    }
    RECOVERY_METRIC {
        uuid id PK
        uuid athlete_id FK
        text algorithm_version
    }
    DAILY_TRAINING_METRIC {
        uuid id PK
        uuid athlete_id FK
        text algorithm_version
    }
    WEEKLY_TRAINING_METRIC {
        uuid id PK
        uuid athlete_id FK
        text algorithm_version
    }
    AUDIT_EVENT {
        uuid id PK
        uuid actor_user_id FK
    }
```

The MVP still stores athlete ownership explicitly, even for a single athlete. This makes athlete-scoped authorization, export, deletion, and future multi-athlete support possible without changing core keys.
