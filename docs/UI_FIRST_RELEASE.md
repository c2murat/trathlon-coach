# First Visible Release — Version 0.4

## Purpose

Version 0.4 is the first usable TriCoach AI web interface. It exposes the
working backend in one focused athlete page without introducing analytics,
planning, or coaching behavior.

The page answers four immediate questions:

1. Is TriCoach AI online?
2. Is Strava connected?
3. Is synchronization current or in progress?
4. What training was imported most recently?

## Page contents

The first page must show:

- **TriCoach AI** title and a simple application shell.
- Backend status: **Online** or **Offline**.
- Strava status: **Connected**, **Disconnected**, **Reconnect required**, or
  **Temporarily unavailable** where returned by the backend.
- Imported activity total.
- Last synchronization timestamp in the athlete's timezone.
- Current/latest synchronization status and safe progress/error information.
- The 10 most recent activities, each showing sport, local date, name, distance,
  moving time, and elevation.
- **Connect Strava** when the account is disconnected or needs reconnection.
- **Synchronize activities** when Strava is connected and no sync is active.

Metric values come from canonical metric storage. The UI may format distance and
duration for readability but must not invent values when a summary field is
missing.

## Existing backend contracts to reuse

| UI need | Existing endpoint | Use |
|---|---|---|
| Backend availability | `GET /health` | Treat HTTP 200 and `status: ok` as online; network/timeout failure as offline |
| Strava connection | `GET /integrations/strava/status` | Render connection status, reconnect requirement, and `last_sync_at` |
| Connect Strava | `GET /integrations/strava/connect` | Browser navigation follows the existing OAuth redirect |
| Start synchronization | `POST /integrations/strava/imports` | Returns HTTP 202 with `job_id` and initial status |
| Poll known synchronization | `GET /integrations/strava/imports/{job_id}` | Render allow-listed counts, page, timestamps, retry time, and safe error category |

The frontend must never receive or retain OAuth tokens. The development
authentication dependency remains a fixed local user until a later
authentication sprint.

## Backend contracts implemented for Sprint 0.4

Version 0.4 adds the following athlete-scoped read contracts:

### `GET /activities?limit=10&offset=0`

An athlete-scoped, newest-first summary query. The minimal response should
contain:

- `items`: at most 10 activities;
- `total`: total imported, non-deleted activities for the athlete;
- per item: internal activity ID, sport, name, UTC start time, athlete timezone,
  distance metres, moving time seconds, and elevation gain metres.

The query needs deterministic ordering (`start_at DESC`, then internal ID),
bounded pagination, ownership isolation, exclusion of locally/provider-deleted
records, and no raw provider payload.

### `GET /integrations/strava/imports/latest`

Returns the latest owned Strava summary-import job using the same safe fields as
the existing job-status endpoint, or a clear empty result when no job exists.
This lets a fresh browser session show synchronization state without knowing a
previous `job_id`.

Because the current router already has `/{job_id}`, the static `/latest` route
must be registered before the dynamic UUID route (or otherwise structured so it
cannot be interpreted as a job identifier).

No activity-count-only endpoint is necessary if the activity-list response
includes `total`.

The backend allows only the configured `FRONTEND_ORIGIN` through CORS. Local
development defaults to `http://127.0.0.1:5173`; wildcard origins and
credentialed cross-origin requests are not enabled.

## Interaction behavior

### Initial load

Request health, Strava status, recent activities, and latest import status.
Connection and content requests may load independently so one failure does not
erase successful sections.

### Connect

When disconnected, **Connect Strava** navigates the browser to the existing
connect endpoint. Do not fetch the redirect as background JSON. After OAuth
returns, reload connection and activity state.

### Synchronize

When connected, **Synchronize activities** posts once to the import endpoint.
Store the returned `job_id` in page state and poll its status with a conservative
interval. Disable duplicate clicks while status is queued, running, or
retry-scheduled. Stop polling on terminal status or page exit.

### Freshness

Show `last_sync_at` using the athlete timezone and an exact timestamp available
on demand. Do not present frontend request time as synchronization time.

## Required states

- **Loading:** stable skeletons/placeholders; actions disabled only where their
  prerequisites are unresolved.
- **Empty:** connected but zero activities; explain that the athlete can start a
  synchronization.
- **Disconnected:** explain the read-only Strava connection and show Connect.
- **Synchronizing:** show safe status and counts; prevent duplicate start clicks.
- **Paused:** show retry timing/category without technical or secret detail.
- **Error:** keep successful sections visible, give a short actionable message,
  and offer a scoped retry.
- **Backend offline:** show a prominent offline state; do not mislabel Strava as
  disconnected when its status is simply unavailable.

## Textual wireframe

```text
+------------------------------------------------------------------+
| TriCoach AI                                      Backend: Online |
+------------------------------------------------------------------+
| Strava: Connected             Last sync: 14 Jul 2026, 10:42     |
| Sync: Completed               Imported activities: 1,381        |
|                                      [Synchronize activities]    |
+------------------------------------------------------------------+
| Recent activities                                               |
| RUN   14 Jul  Morning Run       8.2 km   42:18    74 m          |
| RIDE  13 Jul  Endurance Ride   61.4 km  2:11:05  620 m          |
| SWIM  12 Jul  Pool Session      2.4 km   49:10     n/a          |
| ... up to 10 newest activities                                  |
+------------------------------------------------------------------+
| Loading / empty / scoped error message when applicable          |
+------------------------------------------------------------------+
```

When disconnected, the Strava panel replaces the synchronization action with
`[Connect Strava]`.

## Acceptance criteria

- The page renders every required field and state on desktop and a narrow mobile
  viewport.
- Offline backend and disconnected Strava are distinct states.
- A disconnected athlete can enter the existing OAuth flow.
- A connected athlete can start one synchronization and observe its progress.
- Activity total and recent 10 reconcile with athlete-scoped PostgreSQL data.
- Missing metrics render as unavailable, not zero.
- No tokens, secrets, provider bodies, or health data enter browser state.
- Keyboard navigation, focus visibility, headings, labels, and status
  announcements pass an accessibility smoke check.

## Explicit exclusions

No activity detail page, filters, laps, streams, charts, advanced analytics,
training load, profile editing, zones, equipment management, calendar,
recovery, AI interpretation, Garmin, or deployment redesign is part of this
release.

## Version 0.5A extension

The single-page release now includes an independently loaded athlete overview: current-week totals, four normalized sport summaries, an accessible eight-week training-time trend, and deterministic consistency metrics. Analytics failure must not hide connection, synchronization, or recent-activity controls. These summaries are descriptive and are not coaching advice.
