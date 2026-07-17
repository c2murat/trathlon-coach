# Strava Historical Activity Import Strategy

## Purpose and boundaries

This document defines how TriCoach AI will import an athlete's historical Strava activities safely, completely, and repeatably. It extends the provider, domain, coaching, and data-model policies already documented. It is a strategy only: no import behavior is implemented by this document.

“Complete history” means every activity visible to the connected athlete under the granted Strava scopes at the time of the import snapshot. Provider privacy rules, removed activities, missing sensor data, and scope restrictions can make the visible history smaller than the athlete's total real-world training history. The product must describe those limitations honestly.

The import creates provider-neutral Completed Activities while retaining Strava provenance. It does not create Planned Workouts, infer plan matches, overwrite athlete-authored context, or begin coaching analysis before imported facts are durably available.

## 1. Goals

The historical import must:

1. Import the athlete's complete Strava history visible under current authorization.
2. Resume safely after interruption without restarting completed work unnecessarily.
3. Never create duplicate provider activities, including after retries, overlaps, or repeated imports.
4. Establish checkpoints and reconciliation rules reusable by future incremental synchronization.
5. Preserve provider facts separately from athlete-authored RPE, notes, corrections, and coaching interpretation.
6. Report progress, limitations, and failures without exposing credentials or raw provider responses.
7. Respect shared Strava rate limits and yield capacity to interactive, authorization, and future webhook work.

## 2. Import phases

Each phase has its own progress, checkpoint, retry budget, and completion condition. A later phase may process an activity only after the earlier phase has established its provider identity and basic provenance.

### Phase 1 — Activity summaries

Download paginated activity summaries for the fixed import range. Normalize enough information to establish the activity's provider identity, sport, start time, name, basic duration/distance, and discovery status.

This phase is optimized for coverage. It discovers which activities exist with relatively few requests, makes duplicate detection possible immediately, and supplies the activity inventory used to calculate later-phase work. It must not perform one detail request inside the summary-page transaction.

### Phase 2 — Activity details

Fetch the authoritative detail representation for each discovered activity that is eligible and not already complete for the current mapping version. Enrich provider-owned fields, validate ownership, and record whether detail is complete, unavailable, removed, or permanently unsupported.

This phase is separated because detail requests multiply request volume and fail independently. Summary coverage remains useful and resumable even when rate limits or one malformed activity prevent enrichment.

### Phase 3 — Laps

Import lap or split information for activities where Strava supplies meaningful lap data and the athlete has authorized it. Preserve lap ordering, timing, distance, and supported intensity observations without fabricating absent laps.

Laps are separated because they are optional, sport-dependent, larger than summaries, and may require different reconciliation. A missing lap must not invalidate an otherwise usable Completed Activity.

### Phase 4 — Streams (future)

Streams include dense time-series observations such as time, distance, heart rate, power, cadence, speed, altitude, and location-related data. They are explicitly deferred until storage, privacy, consent, retention, and processing costs are resolved.

Deferral prevents a useful history import from being blocked by the most expensive and sensitive data. Summary, detail, and lap imports must remain valid when streams are later added as a separately consented, resumable enrichment phase.

### Why phases remain independent

- Coverage is established before expensive enrichment.
- Each phase can pause or retry without discarding another phase's progress.
- Rate-limit budgets can favor summaries first and defer details or laps.
- A malformed or removed activity is isolated to its phase and item.
- Mapping changes can re-run only the affected phase.
- User progress can distinguish “activity discovered” from “fully enriched.”
- Future streams can adopt stricter privacy and retention without redesigning base import semantics.

## 3. Activity selection

### Import range and snapshot

At start, normalize the requested range in UTC and freeze a snapshot upper boundary. A complete first import uses an explicit earliest boundary representing all available history and a `before` boundary at snapshot start. Athlete-selected bounded imports use explicit `after` and `before` values. The same normalized range is retained for every retry.

Freezing the upper boundary prevents activities created during the backfill from continually shifting the working set. Activities occurring or uploaded after that boundary belong to a later incremental pass. A final overlap reconciliation catches late uploads whose activity time falls inside an already scanned range.

### Pagination

- Request explicit page sizes within verified provider limits.
- Treat Strava's activity list as reverse chronological, but validate every returned timestamp and never rely on ordering for deduplication.
- Persist progress only after every accepted item in a page has been reconciled durably.
- An empty page ends the scan; a short page is a likely end signal but should follow verified provider behavior.
- Protect against repeated pages by tracking page fingerprints and external IDs. Repeated content without forward progress pauses the job rather than looping.
- Resume from a persisted time window and page checkpoint with a deliberate overlap. Deduplication makes replay safe and avoids depending solely on a page number that may drift as provider data changes.

### Ordering

Newest-to-oldest discovery gives the athlete useful recent history quickly and establishes a high-water mark for later incremental synchronization. Canonical history is ordered by activity occurrence time, not discovery or import time. Equal timestamps are resolved by provider identity, never by assuming arrival order.

### `before` and `after` filters

Filters are UTC epoch boundaries with documented inclusive/exclusive assumptions verified by contract tests. Boundary activities are deliberately re-requested through a small overlap so uncertain edge semantics cannot create gaps. The same activity may therefore appear in adjacent windows and must reconcile to one source identity.

### Incremental imports

After historical completion, incremental synchronization starts from the latest safely observed activity time minus a configurable overlap. It uses the same mapping and deduplication rules as backfill. A periodically wider reconciliation window is needed because athletes can upload old activities or edit existing ones long after they occurred.

Incremental synchronization never trusts “newer start time” as proof that an activity is new. Provider identity remains authoritative.

### Updated activities

When an existing external activity appears again, compare the newly fetched provider representation with the last normalized provider-owned state and mapping version. Refresh only provider-owned facts. Never overwrite athlete RPE, notes, plan associations, manual corrections, or coaching evidence.

If Strava supplies no dependable activity revision marker, a detail fetch plus normalized content comparison determines whether provider-owned facts changed. Older or less complete observations never replace a newer, more complete known representation.

### Deleted or inaccessible activities

Absence from one list page is not proof of deletion. Deletion is established by an authoritative provider deletion signal, a detail response showing the activity is gone/inaccessible, or a conservative repeated reconciliation policy.

Provider removal marks the Strava source as removed and stops future provider refresh for that source. It does not automatically hard-delete athlete-owned context, another provider source, or the canonical Completed Activity. An activity that becomes private or inaccessible is reported separately from one confirmed deleted by the provider.

## 4. Deduplication and reconciliation

The stable identity for a Strava import is:

- provider: `strava`;
- the connected external provider account; and
- external activity ID.

The external ID is an alternate provider identity, never the internal identity of a Completed Activity. Time, name, distance, route, and duration are not safe deduplication keys.

### Reconciliation rules

1. First sight of an external identity creates one Strava source and, when no canonical activity exists for it, one Completed Activity.
2. Repeated sight of the same identity updates or confirms that source; it never creates a second Completed Activity.
3. Retry, page overlap, repeated full import, webhook delivery, and incremental sync all use the same identity rule.
4. Summary data may create the initial canonical view; detail and lap phases enrich it without changing its identity.
5. A mapping-version change recalculates provider-owned normalized fields but preserves athlete-owned information and history.
6. Two different Strava IDs are never merged merely because time and distance look alike.
7. Possible duplicates across Strava, Garmin, manual entry, FIT, TCX, or GPX require a separate explicit reconciliation workflow and athlete confirmation.
8. A provider removal changes source status; it is not a new activity and does not erase other provenance.
9. Ownership mismatch between the connected athlete and returned activity is a permanent security failure for that item and halts unsafe processing.

## 5. Import state machine

### States

- **Pending:** Accepted and eligible to run, but no worker currently owns execution.
- **Running:** Actively scanning or enriching within one phase and making checkpointed progress.
- **Paused:** Intentionally stopped with resumable state, for example by the athlete, rate-limit protection, expired authorization, or an operational circuit breaker.
- **Completed:** Every phase included in the job's declared scope reached a terminal accounted outcome with no unresolved retryable item.
- **Failed:** Cannot continue automatically because of an unexpected or permanent job-level problem. Completed work and checkpoints remain available.
- **Cancelled:** Athlete or authorized operator ended the job. No new requests begin; already committed activities remain.

### Transitions

```text
Pending ──start──> Running
Running ──rate/user/auth pause──> Paused
Paused ──resume/reconnect/budget available──> Running
Running ──all scoped work accounted──> Completed
Running ──unrecoverable job error──> Failed
Failed ──explicit retry after correction──> Pending
Pending|Running|Paused|Failed ──cancel──> Cancelled
```

Completed and Cancelled are terminal for that job identity. A later incremental import is a new job that safely reuses established activity identities. Retrying a Failed job preserves its range, phase, checkpoints, and attempt history rather than presenting it as a new unexplained import.

An import with committed activities and unresolved retryable items is not falsely labeled Completed. It is Paused when automatic continuation is scheduled or Failed when intervention is required; progress remains visible in both cases.

## 6. Retry strategy

### Temporary errors

Network timeouts, connection resets, selected provider `5xx` responses, and transient dependency failures use bounded exponential backoff with full jitter. Retry the smallest safe unit—page, detail, or lap item—rather than replaying the whole import. Persist the checkpoint and safe error category before waiting.

### Permanent errors

Most invalid requests, unsupported activity shapes after validation, ownership conflicts, and authorization that cannot be refreshed are not blindly retried. Isolate an activity-level failure where safe; pause or fail the whole job for authentication, configuration, or ownership failures. Store only redacted error categories and actionable athlete-facing guidance.

An invalid item may be permanently excluded only when its external identity, phase, reason, and mapping version are accounted for. Otherwise the import retains unresolved status.

### Rate limits

Rate limiting pauses new provider work until a safe retry time. Honor a valid provider retry instruction; otherwise estimate the reset conservatively from observed limit windows. Do not consume daily capacity with aggressive retries.

### Unexpected failures

Unknown exceptions fail the current bounded unit, preserve the last committed checkpoint, and trip a circuit breaker when repetition suggests a systemic problem. They never expose raw provider bodies or secrets. Automatic retry is limited; repeated unknown failures require investigation and an explicit resume.

### Retry budget

Each unit records attempts and next eligible retry time. Budgets differ by category: temporary failures receive a small bounded series, rate limits wait for reset rather than spending attempts rapidly, and permanent failures receive none until evidence changes. Successful progress resets consecutive-failure pressure without erasing attempt history.

## 7. Rate-limit strategy

Strava rate limits are shared application capacity, not an unlimited allowance per athlete. Historical backfill has lower priority than authorization safety, interactive requests, and future webhook-driven updates.

### Header observations

Read and validate the provider's general limit/usage headers and read-specific limit/usage headers on every applicable response. The currently documented names are `X-RateLimit-Limit`, `X-RateLimit-Usage`, `X-ReadRateLimit-Limit`, and `X-ReadRateLimit-Usage`. Treat header values and the provider application dashboard as authoritative over hard-coded defaults; absent or malformed headers trigger conservative behavior.

Record only numeric limit observations, their observation time, and the endpoint category. Never retain authorization headers, credentials, or response bodies as rate-limit evidence.

### Adaptive waiting

- Reserve configurable short-window and daily headroom.
- Reduce concurrency and page throughput as usage approaches the reserve.
- Pause detail and lap work before summary coverage when capacity is tight.
- Yield historical work to token safety, interactive status, and future event-driven synchronization.
- Resume after the observed or conservatively estimated reset boundary with jitter to prevent simultaneous workers from surging.
- Use a shared rate view across workers and athletes; process-local counters alone are insufficient.

### Exponential backoff

Use bounded exponential backoff with full jitter for network errors and retryable provider failures. A valid `Retry-After` takes precedence when longer than the calculated delay. Rate-window waiting and transient-error backoff are distinct: repeatedly probing a known-exhausted window is prohibited.

### Progress persistence

Before any adaptive wait, persist phase, range, page/window cursor, last durably reconciled activity, counts, rate observation, and next eligible attempt. A restart resumes from this checkpoint with overlap and deduplication. Waiting must not hold an activity transaction or claim progress that has not committed.

## 8. Mapping to Completed Activity

Mapping translates Strava-specific representations into the provider-neutral business concept Completed Activity. Raw provider responses are not the canonical activity.

### Identity and ownership

- Resolve ownership only through the authenticated Strava connection; never trust an athlete identifier supplied by an import request.
- Preserve provider `strava`, external account identity, and external activity ID as provenance.
- Never use an external ID as the Completed Activity's own identity.

### Normalized meaning

- Map Strava sport categories to swimming, cycling, running, strength, multisport, or other through a versioned policy. Unknown types become `other` with safe provenance rather than failing the import.
- Normalize occurrence timestamps to UTC while preserving the activity or athlete timezone when reliable. Do not infer hidden precision from privacy-obscured times.
- Use metric units internally: metres, metres per second, watts, beats per minute, seconds, and metres of elevation.
- Preserve elapsed time and moving time as different concepts.
- Treat optional heart rate, power, cadence, speed, elevation, calories, and device-derived fields as absent when not supplied; never invent zero values.
- Mark indoor, commute, manual, privacy, and device context only when the source meaning is understood and the canonical concept can represent it faithfully.
- Preserve safe data-quality context for estimates, missing sensors, unsupported fields, and uncertain timezone.

### Merge ownership

Summary discovery establishes an initial provider-owned view. Detail and lap phases enrich that view. Later Strava observations may replace only provider-owned mapped facts under a versioned merge policy. Athlete-authored RPE, session feedback, notes, equipment choices, plan matching, and coaching interpretation remain untouched.

Descriptions, maps, coordinates, photos, social data, segments, and full payloads are not retained merely because Strava returns them. Any exceptional raw-data retention requires a documented purpose, restricted access, encryption, and a short deletion deadline consistent with the existing data policy.

## 9. Future activity streams

Streams are imported later because they are high-volume, privacy-sensitive, expensive to request and process, and unnecessary for establishing basic history. Location traces may expose home, workplace, or habitual routes. Physiological streams may require stricter access and retention than summary training facts.

Before streams enter scope, the product must decide:

- athlete consent and per-stream selection;
- location minimization and privacy-zone behavior;
- storage and retention policy;
- resolution/downsampling rules;
- provider and device timestamp alignment;
- handling of gaps, duplicates, paused recording, and sensor dropouts;
- recalculation/versioning policy for stream-derived metrics;
- export and deletion behavior;
- rate-budget priority relative to current activity synchronization.

Stream enrichment will reference the already deduplicated provider activity identity. It must be independently resumable and must never create another Completed Activity.

## 10. Metrics after import

Import completion makes normalized evidence available; metric calculation is a separate downstream concern. Metrics must identify method, version, evidence coverage, sport context, and uncertainty.

Potential direct and derived metrics include:

- activity count and training frequency;
- elapsed duration and moving duration;
- distance by sport;
- elevation gain;
- average and maximum heart rate when supplied;
- average, maximum, and method-specific cycling power when supported;
- cadence with sport-specific meaning and units;
- average and maximum speed;
- running and swimming pace derived from valid distance and time context;
- weekly volume by sport and combined duration;
- long-session duration and distance trends;
- intensity distribution and time in zones once adequate detail or streams exist;
- RPE and session RPE load when the Athlete supplies them;
- plan adherence only after an explicit Planned Workout relationship;
- future versioned load trends such as TSS-like stress, CTL, ATL, and TSB, with documented limitations.

Missing data never becomes zero. Metrics from different sports, devices, providers, or intensity methods are not automatically comparable. AI may interpret calculated metrics but may not generate factual metric values.

## 11. Error handling and partial results

### Network failures

Retry the bounded request with timeout controls, backoff, and jitter. Keep committed pages and items. Show a temporary provider communication problem rather than an internal exception.

### Partial imports

Every committed activity remains available even when later work pauses or fails. The import reports phase-specific discovered, normalized, enriched, skipped, failed, and remaining counts. Partial progress is never rolled back merely to make the job appear atomic, and it is never mislabeled complete while retryable work remains.

### Provider outages

A sustained outage trips a circuit breaker, pauses provider requests, preserves credentials and checkpoints, and schedules a conservative retry. Athlete-facing status states that Strava is temporarily unavailable and that imported history remains safe.

### Activity removed during import

A detail or lap request may find that an activity discovered in Phase 1 was removed or became inaccessible. Mark the item accordingly, do not repeatedly retry a confirmed removal, and reconcile provider provenance without hard-deleting unrelated Athlete-owned context. Continue other items.

### Malformed or unsupported activities

Isolate the item, retain its safe external identity and redacted reason, and continue when ownership and pagination remain trustworthy. Unknown sport maps to `other`; invalid identity or ownership is a security-level failure and must not be normalized.

### Authentication changes

One controlled token refresh may be attempted by the future token service when authorization expires. A conclusively revoked or insufficient authorization pauses the job and asks the Athlete to reconnect. Import never loops authentication attempts or exposes credential details.

## 12. Athlete experience

The Athlete should see a stable import summary rather than provider internals:

- current overall state and active phase;
- activities discovered and imported;
- items enriched with details and laps;
- items remaining in the known queue;
- pages or time windows scanned;
- approximate percentage when a denominator is known;
- estimated completion time as a range, or “estimating” when evidence is insufficient;
- last imported activity's safe name, sport, and occurrence time;
- last successful progress time;
- paused-until time for rate limiting;
- safe error category, affected phase/item count, and whether action is required;
- controls to pause, resume, retry, or cancel where applicable.

Strava does not necessarily provide a total activity count before pagination completes. During Phase 1, “remaining” and estimated completion are explicitly approximate or unknown. After discovery, Phase 2 and Phase 3 queue sizes provide better estimates, but rate resets and provider outages can still change completion time.

Cancellation explains that already imported activities remain and that restarting is deduplicated. Errors never display tokens, raw responses, stack traces, or sensitive activity content.

## 13. Acceptance criteria

An import is successful when all of the following are true:

1. The fixed requested history range has been scanned to its verified end.
2. Every visible summary has one accounted provider identity and at most one canonical Completed Activity.
3. Every required detail and lap item for the declared import version is completed or has an explicit permanent, visible exclusion reason.
4. No retryable items remain unresolved.
5. Replaying the same range creates no duplicate activities and does not erase Athlete-owned fields.
6. An interrupted run resumes from its checkpoint with safe overlap rather than restarting blindly.
7. Updated provider-owned facts reconcile without overwriting Athlete-authored context.
8. Confirmed removals are represented according to provenance policy without unintended hard deletion.
9. Progress counts reconcile with discovered, imported, excluded, and failed outcomes.
10. Rate limits, retry instructions, and shared capacity reserves were respected.
11. All timestamps, sport mappings, units, and optional metrics satisfy the versioned mapping contract.
12. No credential, raw provider body, or sensitive header appears in user-visible errors, logs, progress, or import summaries.
13. A final incremental-overlap pass can begin from the established high-water mark without creating duplicates.

“Complete” does not mean streams are present; Phase 4 remains outside the declared historical-import scope until separately introduced.

## 14. Future extensions

The import coordinator should remain provider-neutral while each source owns its parsing and provenance rules.

### Garmin

Garmin synchronization will use Garmin account and activity identities, its own rate and authorization semantics, and the same canonical Completed Activity boundary. Similar-looking Strava and Garmin recordings are not automatically merged.

### FIT

FIT file import uses a stable file fingerprint plus embedded session identity where reliable. It must handle device timestamps, multiple sessions, developer fields, and sensor records without assuming Strava semantics.

### TCX

TCX import preserves file provenance, sport context, laps, trackpoints, and timezone uncertainty. Reimporting the same file must be idempotent.

### GPX

GPX primarily supplies track and time/location information and may lack sport, physiological data, or reliable timezone. Missing concepts remain absent and require Athlete confirmation rather than invention.

Cross-source duplicate suggestions may use time, duration, and route similarity only to request Athlete confirmation. Provider/file identities remain separate and reversible regardless of canonical duplicate resolution.

## 15. Risks and mitigations

| Risk | Consequence | Mitigation |
|---|---|---|
| Pagination changes during a long import | Gaps or repeated activities | Fixed snapshot boundary, overlapping time windows, page fingerprints, external-ID deduplication, final reconciliation pass |
| Late upload with an old activity date | Missed historical activity | Incremental overlap plus periodic wider reconciliation |
| Repeated retries | Duplicate activities or wasted quota | Stable provider identity, idempotent reconciliation, bounded unit retries |
| Shared rate exhaustion | All athletes and interactive work delayed | Shared usage view, reserved headroom, priority classes, adaptive pause |
| Provider outage | Stalled import | Circuit breaker, durable checkpoint, visible Paused state, conservative resume |
| Token expiry or revocation | Unauthorized or looping requests | Controlled future refresh, pause on conclusive failure, reconnect guidance |
| Mapping defect | Incorrect canonical facts | Versioned mapping, synthetic contract fixtures, phase isolation, safe recalculation |
| Provider schema drift | Malformed items or silent data loss | Strict tolerant validation, unknown-field policy, monitoring, quarantined item errors |
| Activity removed mid-import | Infinite retry or accidental deletion | Treat authoritative not-found as accounted removal; preserve non-provider context |
| Athlete/provider ownership mismatch | Cross-athlete data exposure | Resolve through connected account, validate returned ownership, halt unsafe work |
| Summary/detail disagreement | Stale or regressed facts | Detail authority for provider-owned fields, completeness comparison, observed-version policy |
| Missing total count | Misleading progress estimate | Show discovery progress and unknown/approximate remaining until inventory exists |
| Dense streams imported too early | Privacy, cost, and storage risk | Defer Phase 4 pending explicit consent and retention design |
| Raw response retention | Privacy and compliance exposure | Normalize by default; exceptional encrypted, restricted, short-lived retention only |
| Cross-provider near-duplicates | Double-counted training | Keep source identities distinct; athlete-confirmed reversible reconciliation |
| Worker crash after provider response | Lost or repeated work | Commit bounded idempotent units; checkpoint only after durable reconciliation |

## Remaining implementation work

Before historical import can run, the project still needs a secret-safe Strava activity client, token refresh coordination, provider activity result types, versioned summary/detail/lap mapping, durable job claiming and checkpoints, shared rate-limit coordination, activity provenance persistence, progress presentation, and mocked contract/integration tests. Streams remain a later design and implementation effort.

## Version 0.6A detailed activity enrichment

Detailed enrichment is independent from summary coverage and never creates a second `CompletedActivity`. `POST /integrations/strava/enrichments` selects a bounded set (default 10, maximum 50), optionally by athlete-owned local UUID, and returns `202 {"job_id":"�","status":"queued"}`. `GET /integrations/strava/enrichments/{job_id}` exposes only job status, selected/enriched/updated/skipped/failed counts, last local activity ID, timestamps, retry time and a safe error category.

Eligibility includes never-enriched activities, summaries whose provider-owned fields changed after enrichment, and retryable failed records. Each successfully mapped detail is committed independently, so a database or malformed-payload failure is isolated and earlier checkpoints survive. Rate limits and temporary provider failures use `retry_scheduled`; invalid credentials mark the account `refresh_required`; a provider 404/410 marks the source activity unavailable/provider-deleted.

Provider-owned detail fields include the separate `provider_description`, calories, device/gear identifiers, provider perceived exertion, suffer score, work/energy, temperature, maximum watts, workout type, counts and source flags. Athlete-authored `description` and `rpe` are never overwritten. Calculated analytics remain outside this mapper. Raw provider responses are never persisted.

This phase deliberately excludes laps, streams, maps, route rendering, analytics metrics, observations, recommendations, planning and AI. Those boundaries remain prerequisites for Version 0.6B and later work.

## Version 0.6B evidence retrieval

Evidence retrieval is separate from summary/detail enrichment and never mutates those facts. `POST /integrations/strava/evidence` accepts up to ten owned local activity UUIDs plus `include_laps`, `include_streams`, and `include_location`; detail enrichment must already have succeeded. Jobs commit one activity at a time and expose only counters/checkpoints through `GET /integrations/strava/evidence/{job_id}`.

Laps are relational rows keyed by activity and provider sequence. Streams are unique by activity/type and store only normalized values plus resolution/series metadata, checksum, version, source/fetch timestamps, retention class, and original/retained counts. SQLAlchemy JSON maps to JSONB on PostgreSQL and JSON on SQLite. No raw Strava response is retained.

When a source has more than `TC_ACTIVITY_STREAM_MAX_SAMPLES`, one deterministic uniformly spaced index set is generated for its aligned streams. Index zero and the final index are always retained. Applying the same indices to every aligned series preserves time/distance correspondence. Laps are never downsampled; malformed or differently sized streams are isolated.

Location retention is disabled by default. `latlng` is neither requested nor persisted while disabled, route/polyline evidence is hidden, and the cleanup endpoint deletes previously retained location rows. Logs and job responses contain no coordinates, stream values, tokens, URLs, or provider bodies. `TC_ACTIVITY_STREAM_RETENTION_DAYS=0` disables age-based deletion. With a positive value, expiry is enforced when a new evidence job starts; a standalone production scheduler remains future operational work.

`GET /activities/{activity_id}/evidence` is athlete-owned and response-bounded. It exposes supported factual streams only, never `latlng`; route output contains a polyline only when location retention is enabled. This sprint adds no analytics interpretation, sport metrics, observations, recommendations, coaching or AI.


La versi�n 0.6C consume �nicamente res�menes y evidencia almacenada; no solicita datos adicionales al proveedor durante el rec�lculo.
