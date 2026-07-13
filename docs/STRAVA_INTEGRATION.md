# Strava Integration Technical Specification

## 1. Scope and goals

This document specifies the Strava adapter for Triathlon Coach. Sprint 0.2.4 implements connect/callback authorization, credential persistence, secret-free status, and secure disconnect; activity clients, synchronization, refresh scheduling, and webhooks remain design contracts only.

The integration must:

- connect one athlete account to one Strava account with explicit consent;
- import a bounded history of activities and resume interrupted work;
- receive future activity changes through Strava webhooks instead of polling;
- refresh short-lived access tokens safely and rotate refresh tokens;
- disconnect, revoke, and delete credentials without silently deleting imported training history;
- normalize Strava data into provider-neutral records so future Garmin support does not change the coaching domain.

The initial application is personal-first. Provider identities remain scoped alternate keys, never internal primary keys. The source of truth is the canonical `CompletedActivity`; provider state belongs to `IntegrationAccount`, `OAuthCredential`, `SyncJob`, and `WebhookEvent` as described in [DATA_MODEL.md](DATA_MODEL.md).

Official references: [Strava authentication](https://developers.strava.com/docs/authentication/), [API reference](https://developers.strava.com/docs/reference/), [webhooks](https://developers.strava.com/docs/webhooks/), and [rate limits](https://developers.strava.com/docs/rate-limits/).

## 2. Configuration and provider endpoints

Secrets and deployment-specific URLs are environment variables:

| Setting | Secret | Purpose |
|---|---:|---|
| `STRAVA_CLIENT_ID` | No | Registered Strava application ID |
| `STRAVA_CLIENT_SECRET` | Yes | Application credential used for token exchange/revocation and subscription management |
| `STRAVA_REDIRECT_URI` | No | Exact backend OAuth callback URL under the registered callback domain |
| `STRAVA_WEBHOOK_CALLBACK_URL` | No | Public deployed webhook callback URL |
| `STRAVA_WEBHOOK_VERIFY_TOKEN` | Yes | Random application-chosen token used for subscription validation |
| `STRAVA_SCOPES` | No | Allow-listed scopes; Sprint 0.2.2 requires `read,activity:read_all` |
| `STRAVA_AUTHORIZATION_URL` | No | Public authorization endpoint; safe official default |
| `STRAVA_TOKEN_URL` | No | Public token endpoint used by the Sprint 0.2.3 authorization-code exchange |
| `OAUTH_STATE_TTL_SECONDS` | No | Short-lived state expiry; safe development default of 600 seconds |

Official external endpoints used by the web integration are:

- authorization: `GET https://www.strava.com/oauth/authorize`;
- token exchange/refresh: `POST https://www.strava.com/oauth/token` (the official examples may also show the equivalent API v3 path);
- preferred revocation as of June 2026: `POST https://www.strava.com/oauth/revoke` using HTTP Basic authentication for the application;
- activities: `GET https://www.strava.com/api/v3/athlete/activities` and, when detail is required, `GET https://www.strava.com/api/v3/activities/{id}`;
- webhook subscriptions: `https://www.strava.com/api/v3/push_subscriptions`.

No URL, client secret, verification token, scope set, timeout, or operational limit is embedded in domain code. Redirect URIs must be allow-listed, not accepted from arbitrary request input.

## 3. OAuth authorization design

### Requested scopes

| Scope | Reason | MVP decision |
|---|---|---|
| `read` | Basic public profile access and the baseline authorization context returned for the authenticated athlete. | Request initially. Revalidate during implementation whether the specific profile fields retained by the MVP require it independently of activity access. |
| `activity:read_all` | Read all of the athlete's activities, including activities with Only Me visibility, and receive privacy-related webhook behavior with full authorized visibility. This supports a complete personal training history. | Request with a clear explanation that private activities enter a private personal coaching system. |

The narrower alternative is `activity:read`, which can list activities visible to the app but filters Only Me activities. A first internal prototype could use it if private activities are intentionally out of scope. The product MVP promises a useful personal history and therefore proposes `activity:read_all`, but authorization must still work in a degraded state if the athlete grants less. No `activity:write`, `profile:write`, or other write permission is requested.

### Authorization sequence

1. An authenticated athlete requests `GET /integrations/strava/connect`.
2. The backend confirms that the caller owns the athlete profile and that no connect attempt is already being consumed.
3. It creates a cryptographically random, single-use `state`, stores only a hash plus athlete/user binding, intended post-auth destination, creation time, and short expiry in a server-side transient store, and returns a browser redirect to Strava.
4. The Strava authorization URL contains `client_id`, the exact allow-listed `redirect_uri`, `response_type=code`, requested `scope`, `state`, and normally `approval_prompt=auto`. Reconsent can explicitly use `force`.
5. Strava redirects to the callback with either `error=access_denied` or a short-lived, one-use `code`, granted `scope`, and the original `state`.
6. The backend atomically consumes and verifies state before any token exchange. Missing, expired, reused, or mismatched state fails closed.
7. For an accepted flow, the backend sends the code, client ID, client secret, and `grant_type=authorization_code` to the token endpoint over TLS.
8. It validates the response, external athlete identity, and actual granted scopes. Requested scopes are never assumed to have been granted.
9. In one database transaction, it creates or reconnects `IntegrationAccount`, stores tokens only in its one-to-one `OAuthCredential`, records scopes/expiry, and writes a secret-free audit event.
10. The browser receives a safe redirect to a fixed frontend result page. Tokens and authorization codes never enter the frontend URL or response.

### Denial, partial authorization, and reconnection

- `error=access_denied` consumes state, creates no credential, emits `strava.authorization_denied`, and redirects with a non-sensitive result code.
- Missing `activity:read_all` produces `scope_insufficient` for the complete-history experience. If `activity:read` is available, the product may offer an explicit limited mode; it must show that private activities are excluded. The initial implementation may instead require reauthorization.
- The granted scope set from the callback/token response is persisted on both connection/credential metadata as appropriate and displayed by status without tokens.
- Reconnecting the same athlete to the same external Strava athlete updates the existing soft-disconnected `IntegrationAccount` and replaces its credential atomically.
- Attempting to connect a different external Strava athlete to an existing active relationship requires explicit confirmation; it must never silently relabel imported activities.
- If the external Strava identity is already actively connected to another local athlete, reject the callback as a conflict and retain no returned tokens beyond immediate secure revocation/cleanup.

### Token lifetime and refresh

Access is made with `Authorization: Bearer <access_token>`. The credential stores Strava's `expires_at` UTC instant. Before a provider call, `StravaTokenService` refreshes when expired or within a configurable safety window. Strava currently documents six-hour access tokens and recommends refresh near the last hour, but the implementation trusts the returned expiry rather than a hard-coded lifetime.

Refresh sends `grant_type=refresh_token`, the current refresh token, client ID, and client secret to the token endpoint. A database/advisory or distributed lock keyed by integration account permits one refresh at a time. After acquiring the lock, the service reloads the credential because another worker may already have refreshed it. On success, it atomically replaces the access token, expiry, and refresh token. The refresh token returned by Strava is always persisted, even if it appears unchanged; the previous refresh token must be treated as invalid when rotation occurs.

## 4. Planned backend endpoint contracts

These application endpoints are provider-specific adapters under a provider-neutral integration feature. They are unimplemented.

### `GET /integrations/strava/connect`

- **Purpose:** begin authorization for the authenticated athlete.
- **Authentication:** required user session/access token; caller must own an active `AthleteProfile`.
- **Request:** optional `return_to` identifier selected from a server-side allow-list; no client-provided redirect URI or scope escalation. An optional explicit `force_reconsent=true` may be added later with CSRF-safe authenticated navigation.
- **Success:** HTTP `302` to the official Strava authorization URL. Browser redirect, not JSON.
- **Errors:** `401` unauthenticated; `403` inactive/unauthorized athlete; `409` conflicting active connection/attempt; `503` configuration or transient state store unavailable.
- **Security:** generate high-entropy state; bind it to user/athlete and intended destination; short TTL; SameSite/secure session controls; no secret or external token in URL/logs.
- **Database changes:** no durable integration/credential change. A short-lived authorization-attempt record is stored in an expiring server-side store; creation may produce a secret-free audit event.

### `GET /integrations/strava/callback`

- **Purpose:** finish OAuth after Strava redirects the browser.
- **Authentication:** the original authenticated session should be present, and state binding is always required. State remains authoritative against login-CSRF; a missing browser session requires a deliberately designed recovery flow, not automatic acceptance.
- **Request query:** `state`; either `code` and granted `scope`, or `error=access_denied`. Reject ambiguous requests, unexpected parameters, and oversized values.
- **Sprint 0.2.3 success:** HTTP `200` JSON containing only `provider=strava` and `status=connected|reconnected`, with `Cache-Control: no-store`. A fixed frontend result redirect is deferred until the frontend route exists.
- **Sprint 0.2.3 denial:** HTTP `200` with only `provider=strava` and `status=denied`; no credential is created.
- **Errors:** secret-free `400/403/409/500/502/503` JSON codes cover invalid state/input, insufficient scope, ownership conflict, persistence failure, token exchange failure, and provider unavailability. Responses use no-store headers and never contain provider bodies or credentials.
- **Security:** atomically consume state before exchange; verify callback origin indirectly through state and registered redirect; exchange over TLS; validate returned athlete ID/scopes; redact code, tokens, client secret, provider body, and Basic/Bearer headers from logs/errors/audit.
- **Database changes:** create/reconnect `IntegrationAccount`; insert/update the single `OAuthCredential`; persist actual scopes/expiry; audit connection creation/reconnection, authorization denial, insufficient scope, exchange failure, and ownership conflict. A global unique constraint on `(provider, external_account_id)` prevents silent cross-athlete reassignment. Do not start a backfill in the request.
- **Development limits:** OAuth state is an in-memory, process-local store. Tokens are plaintext development placeholders under the existing encryption TODO and are not production-safe. Unit tests use SQLite and a mocked transport; PostgreSQL locking/concurrency and migration execution require integration validation.

### `GET /integrations/strava/status`

- **Purpose:** return connection and synchronization state for the current athlete.
- **Authentication:** required; athlete owner (future coach access is excluded).
- **Request:** no provider ID accepted for the personal MVP.
- **Sprint 0.2.4 success:** HTTP `200` no-store JSON with only provider, `connection_status`, connected flag, external athlete ID, granted scope names, stored connection/update/token-expiry/last-sync timestamps, reconnect flag, and a safe message. No synchronization state is invented.
- **Errors:** `401`, `403`; operational provider unavailability does not prevent reading stored status.
- **Security:** fixed response schema explicitly excludes access token, refresh token, client secret, raw provider responses, cursor, and internal error details. Cache privately or not at all.
- **Database changes:** read-only. Optional access audit only if policy requires it.

Example connected response:

```json
{
  "provider": "strava",
  "connection_status": "connected",
  "connected": true,
  "external_athlete_id": "123456",
  "granted_scopes": ["activity:read_all", "read"],
  "connected_at": "2026-07-13T09:00:00Z",
  "updated_at": "2026-07-13T09:00:00Z",
  "token_expires_at": "2026-07-13T15:00:00Z",
  "requires_reconnect": false,
  "last_sync_at": null,
  "message": "Strava is connected."
}
```

### `DELETE /integrations/strava/disconnect`

- **Purpose:** stop synchronization and revoke/delete credentials while preserving imported activities unless separately requested.
- **Authentication:** required athlete owner; destructive request requires normal application CSRF protection when cookie-authenticated and may require recent reauthentication.
- **Request:** no token or provider account ID in body. Optional explicit `delete_imported_activities=false` is not supported initially; activity deletion is a separate privacy workflow.
- **Success:** HTTP `200` no-store JSON with `provider=strava` and `status=disconnected`. No account or an already disconnected account returns `status=already_disconnected`; both are idempotent.
- **Errors:** `502` for provider authentication/configuration rejection, `503` for temporary provider/transport failure, and a generic `500` if the final local transaction fails. Provider bodies and internal exception details are never returned.
- **Remote endpoint:** Sprint 0.2.4 uses only `POST https://www.strava.com/oauth/revoke` (configurable by `STRAVA_REVOCATION_URL`). It sends the client ID/secret with HTTP Basic authentication and the current access token plus `token_type_hint=access_token` as secret form data. HTTP `200`, including an already-invalid token response, is success. No legacy deauthorize fallback is implemented.
- **Failure/retry policy:** authentication/configuration or temporary failure is audited by safe category, returns an honest error, leaves the account state and only retry credential intact, and permits a later repeat. The provider response body is discarded. No activity API exists in this sprint, so retained retry credentials have no other application consumer.
- **Local deletion:** after confirmed remote success—or when no usable credential exists—the endpoint hard-deletes `OAuthCredential`, marks `IntegrationAccount.status=disconnected`, sets `disconnected_at`, and records secret-free completion audits in one transaction. Plaintext development storage cannot guarantee physical secure erasure; production encryption/key destruction remains mandatory.
- **Activity distinction:** disconnect does not delete or detach `CompletedActivity` records. Imported-activity deletion belongs to a separate explicit privacy workflow.

## 5. Token security

- Client ID is configuration; client secret comes from a production secret manager/environment injection and never from repository files.
- Access and refresh tokens exist only in `OAuthCredential`. They never appear in `IntegrationAccount`, public schemas, URLs, logs, exception text, tracing attributes, audit metadata, test snapshots, or AI context.
- Current database columns are explicitly development-only plaintext placeholders. Production activation is blocked until envelope encryption is implemented with keys stored outside PostgreSQL, versioned ciphertext, rotation, and tested failure recovery.
- ORM representations, structured log processors, HTTP client logging, error capture, and database diagnostics must redact fields and `Authorization` headers by name and classification.
- Refresh uses a per-integration lock plus reload-after-lock. A process-local lock alone is insufficient once multiple workers exist.
- Every successful refresh atomically rotates all returned token material and expiry; failed refresh does not destroy the last credential prematurely.
- `401` after one safe refresh attempt moves the connection toward `refresh_required`/`revoked`; it must not loop refreshes.
- Revocation uses the configured `/oauth/revoke` mechanism, retains the only retry credential on unconfirmed failure, and ends in credential hard deletion after confirmed success. No other token-consuming feature exists yet.
- An expired access token with a usable refresh token is normal and not a reconnect state. Invalid/revoked refresh credentials or insufficient scopes require reauthorization.

## 6. Historical synchronization

Historical import is a later roadmap capability and does not run in the OAuth callback.

1. **Start:** create a `SyncJob(job_type=historical_import)` with a stable idempotency key derived from integration, requested UTC range, and import version. Default date range and athlete override remain product decisions.
2. **Range:** use Strava's `after` and `before` epoch filters. Record requested/normalized range in UTC. Never request an unbounded lifetime repeatedly.
3. **Pagination:** call `GET /athlete/activities` with explicit page and configurable `per_page`; stop on an empty/short page according to verified API behavior. Persist checkpoint only after the page is durably committed.
4. **Mapping:** normalize each supported summary activity. Fetch individual detail only when required fields are absent and budget permits; do not create an unconditional detail-request N+1 pattern.
5. **Deduplication:** upsert by `(IntegrationAccount.id, external_activity_id)`, never by provider ID as PK and never by time/distance heuristics across providers. Current MVP stores this alternate key on `CompletedActivity` until documented `ActivitySource` is implemented.
6. **Incremental checkpoint:** retain last completed page/range cursor plus latest safely observed activity time. Apply a configurable overlap window on later incremental sync to catch changes; deduplication makes overlap safe.
7. **Partial failure:** commit bounded batches. Record counts and redacted error codes. Retry failed pages/items independently; mark the job `partially_succeeded` when usable data was imported but unresolved items remain.
8. **Resume:** a retry reuses job identity/checkpoints and skips already committed external IDs. It never restarts from page one without reason.
9. **Progress:** expose queued/running/retry/partial/succeeded state, range, pages/items processed, and safe failure summaries through status. Counts are approximate if provider data changes during backfill.
10. **Efficiency:** prioritize webhooks and interactive status/detail requests; pause backfill near short-window/daily limits; avoid polling and repeated enrichment of unchanged activities.

Provider updates use a documented ownership policy: Strava refresh may update provider-owned facts, but never silently overwrite athlete-entered RPE, coaching notes, or future planned/completed matches.

## 7. Webhook strategy

Webhooks are notification envelopes, not complete activity objects. Activity create/update notifications normally enqueue a separate authenticated activity fetch before canonical mapping.

### Subscription validation

- Strava permits one webhook subscription per application, covering authorizing athletes.
- Subscription creation is an operational deployment task using client ID/secret, HTTPS callback, and an application-chosen verification token.
- Strava sends `GET` validation parameters `hub.mode`, `hub.challenge`, and `hub.verify_token` to the callback.
- The callback uses constant-time comparison against the configured verification token, requires `hub.mode=subscribe`, and returns HTTP `200` JSON containing the exact challenge. Official documentation currently requires a response within two seconds.
- The verification token is not an OAuth token and is never returned except comparison of the incoming value; the challenge is safe to echo as required.

### Event receipt and processing

1. Accept only HTTPS in deployed environments; terminate through trusted proxy configuration and enforce body size/content type.
2. Parse the documented envelope: `object_type`, `aspect_type`, `object_id`, `owner_id`, `subscription_id`, `event_time`, and optional `updates`.
3. Derive a versioned deduplication key from stable documented fields because the envelope does not promise a standalone event ID. A candidate is a hash of provider, subscription, owner, object type/ID, aspect, event time, and canonicalized updates. This exact composition must be contract-tested before implementation.
4. Insert `WebhookEvent` with unique `(provider, deduplication_key)`. Store normalized envelope fields and hash by default; raw payload is justified only for short replay/debug incidents, restricted and purged within 30 days.
5. Return `200` immediately after durable receipt/duplicate detection—target under two seconds—and enqueue background processing. Do not fetch an activity in the callback.
6. For activity `create`/`update`, fetch the current activity and upsert it. One athlete action may generate multiple updates; final provider state is authoritative for provider-owned fields.
7. For activity `delete`, mark provider provenance/deletion and reconcile the canonical record without automatically erasing athlete-owned data or another provider source.
8. For athlete deauthorization (`object_type=athlete`, `updates.authorized=false`), mark the integration revoked, block token use, delete credentials safely, stop sync, and notify the athlete locally.

Duplicate events return success without duplicate jobs. Out-of-order events are compared using provider event time and, more importantly, a fresh authoritative fetch; stale update work cannot overwrite a newer observed provider version. A delete arriving before create must remain safe. Processing is retryable and eventually dead-lettered with a user-visible sync error, never an infinite retry loop.

Retain normalized event/status records for 90 days as proposed by the data model and raw bodies for at most 30 days. Subscription ID and verification token configuration are operational state; subscription changes are audited without secrets.

## 8. Rate-limit strategy

- Parse and record the official `X-RateLimit-Limit` and `X-RateLimit-Usage` pairs and the read-specific `X-ReadRateLimit-Limit` / `X-ReadRateLimit-Usage` pairs from every relevant response. Treat absent/malformed headers conservatively.
- Strava applies short-window and daily application limits. Published defaults and account capacity can change; initialize operational alerts from current documentation/settings, but headers and the application dashboard remain authoritative.
- Maintain shared application-level rate state, not only per athlete, because limits apply to the application. Store numeric usage/reset estimates and observation time—never request headers containing credentials.
- Reserve configurable headroom. Prioritize token/revocation safety and interactive user requests, then webhook detail fetches, then incremental sync, then historical backfill.
- Do not poll for new activities. Webhooks trigger future synchronization.
- On approaching a limit, throttle/pause background jobs and persist `next_retry_at`. Resume after the observed/configured reset boundary with jitter to avoid a worker stampede.
- On `429`, honor a valid `Retry-After` header when present. If absent, calculate a conservative delay from limit window observations/configuration. Apply bounded exponential backoff with full jitter for transient `429`/`5xx`/network failures; do not retry most `4xx` errors.
- Requests that exceed a short limit may still affect daily usage, so aggressive retry is prohibited. Circuit-break prolonged provider failures and show a temporary-unavailable state.
- Log endpoint category, status, safe request ID, usage counters, and scheduled retry—not query/body secrets, tokens, client secret, or athlete payload.

## 9. Provider client boundaries

These are responsibilities/interfaces, not Python classes yet:

### `StravaOAuthClient`

Builds allow-listed authorization URLs; exchanges authorization codes; refreshes token sets; revokes tokens; validates provider response shape. It handles HTTP only and returns typed provider DTOs with secret-safe representations.

### `StravaApiClient`

Performs authenticated Strava resource requests, attaches bearer credentials without logging them, parses rate headers, applies timeouts/error mapping, and exposes list/get activity operations. It does not write domain records or refresh recursively.

### `StravaTokenService`

Owns credential lookup, expiry checks, refresh locking, token rotation, connection-state transitions, and secret deletion. It gives the API client a usable token through a narrow secret-bearing boundary.

### `StravaActivityMapper`

Converts provider DTOs into a provider-neutral activity mutation plus provenance/deduplication identity. It maps sports, units, timestamps, optional data, privacy, and data-quality flags using a versioned mapping policy. It performs no HTTP or database commit.

### `StravaSyncService`

Coordinates bounded backfills and event-driven fetches, creates/resumes `SyncJob`, checkpoints batches, upserts safely, schedules retries, reports progress, and triggers later downstream work. It respects shared rate state.

### `StravaWebhookService`

Validates subscription challenges, validates/parses event envelopes, derives idempotency keys, durably records receipts, acknowledges quickly, and dispatches background work. It never embeds activity mapping or token refresh logic.

Application use cases depend on provider-neutral ports. Strava DTOs stop at the adapter boundary; they do not become ORM or API response models. Unknown provider fields are ignored unless justified as short-retention raw data, and unknown sport types map to `other` while preserving safe provenance for later mapper updates.

## 10. Activity mapping

Fields are nullable unless the official resource and canonical model require them. Summary and detailed activity representations differ, and values may be absent because of sport, recording device, privacy, athlete settings, granted scope, or Strava processing state.

| Strava field/context | Canonical target | Rule and caveat |
|---|---|---|
| `id` | `CompletedActivity.external_activity_id` with source integration | Convert to text; unique with integration account; never PK. Temporary until `ActivitySource`. |
| authenticated athlete / `athlete.id` | `IntegrationAccount.external_account_id`, then `athlete_id` | Resolve only through the authorized integration; reject owner mismatch. |
| `sport_type` (fallback legacy `type`) | `sport` | Versioned mapping to swimming, cycling, running, strength, multisport, or other. Preserve unknown category safely; do not fail the whole import. |
| `start_date` | `start_at` | Parse documented ISO-8601 instant and normalize UTC. Be aware Strava may obscure start times for privacy; do not infer hidden precision. |
| `timezone` and athlete settings | `timezone` | Extract/validate an IANA zone when supplied; preserve athlete setting as fallback and flag uncertainty. Do not treat a fixed UTC offset as a timezone. |
| `name` | `name` | Required canonical name; safe fallback such as sport label if missing. |
| `elapsed_time` | `elapsed_time_s` | Non-negative seconds. |
| `moving_time` | `moving_time_s` | Optional non-negative seconds. |
| `distance` | `distance_m` | Already metres; optional for some sports/manual entries. |
| `total_elevation_gain` | `elevation_gain_m` | Metres; optional. |
| `average_heartrate`, `max_heartrate` | corresponding bpm fields | Optional; depends on sensor, privacy, and processing. |
| `average_speed` | `average_speed_mps` | Metres/second; optional. |
| `max_speed` | future `max_speed_mps` | Current persistence model lacks this field; schema addition required before retention. |
| `average_cadence` | future `average_cadence` with unit/context | Current model lacks it; meaning varies by sport. Do not coerce into a generic value without sport/unit semantics. |
| `average_watts` | `average_power_w` | Primarily cycling and optional; record whether device/estimate when the canonical model supports it. |
| `max_watts` | `max_power_w` | Optional, typically cycling. |
| `weighted_average_watts` | future `weighted_average_power_w` | Current model lacks it; add deliberately and retain Strava semantics/provenance rather than relabeling it as a universal metric. |
| `trainer` | `indoor` | Provider trainer flag; optional/default false only when documented response supplies it. |
| `commute` | `commute` | Optional boolean. |
| `private` / documented visibility | future canonical privacy field | Current model lacks explicit visibility. Must be added before privacy is faithfully persisted; API presentation always defaults private. |
| `manual` | future `manual` flag | Current model lacks it; add before relying on it for analysis/data quality. |
| provider update information | `provider_updated_at`, `last_synced_at` | Use a documented activity update timestamp only if supplied. Webhook `event_time` is event provenance, not automatically the activity's update timestamp. Always set local sync time separately. |

`source_summary` is `strava`; all metric values remain metric. `description`, calories, flags, and other already-supported canonical fields may be mapped when present and authorized. Do not retain maps, coordinates, photos, social data, segment data, or full payload merely because Strava returns them.

Raw provider payload is not the canonical record. Default behavior stores normalized fields plus payload hash/provenance. A raw response may be encrypted/restricted for a documented replay/support case and must have `raw_payload_expires_at` no later than 30 days. Secrets are never part of raw payload storage.

## 11. Error and lifecycle states

Connection state and synchronization state are distinct so a connected athlete can see a delayed backfill without appearing disconnected.

| State | User-facing message | Internal behavior and audit |
|---|---|---|
| Not connected | “Connect Strava to import your activities.” | No active account/credential; no failure audit needed for normal view. |
| Authorization pending | “Finish authorization in Strava.” | Short-lived state exists; `strava.authorization_started`. |
| Connected | “Strava is connected.” | Active account and credential with sufficient scopes; `strava.connected`/`reconnected`. |
| Token refresh required | “Strava access needs to be renewed.” | Refresh unusable/failed conclusively; block sync; `strava.token_refresh_required`. |
| Temporarily unavailable | “Strava is temporarily unavailable; we’ll retry.” | Bounded retry/circuit state; `strava.provider_unavailable` only on meaningful transition, not every retry. |
| Scope insufficient | “Additional activity permission is needed to include your full history.” | Store actual scope/state without running unsupported import; `strava.scope_insufficient`. |
| Revoked | “Strava access was revoked. Reconnect to resume syncing.” | Credential blocked/deleted, jobs stopped; `strava.revoked`. |
| Disconnected | “Strava is disconnected. Imported activities are still available.” | Credential deleted, account retained as disconnected; `strava.disconnected`. |
| Synchronization running | “Importing activities…” with progress | Active `SyncJob`; `strava.sync_started`. |
| Synchronization partially failed | “Some activities could not be imported; retry is scheduled/available.” | Preserve successes/checkpoint; `strava.sync_partially_failed`. |
| Synchronization completed | “Strava activities are up to date as of …” | Terminal job and freshness time; `strava.sync_completed`. |

Audit metadata contains internal IDs, safe status/error codes, granted scope names, and timestamps only. It never contains authorization codes, tokens, client secret, raw provider bodies, Basic/Bearer headers, or sensitive activity content.

## 12. Privacy, disconnect, and deletion

- **Athlete disconnects:** stop new work, revoke remotely using the supported endpoint, hard-delete local credential, mark integration disconnected, and retain canonical imported activities. Clearly tell the athlete that disconnect is not activity deletion.
- **Athlete revokes in Strava:** process deauthorization webhook, block tokens immediately, delete credential, stop jobs, mark revoked, and show reconnect guidance. A later `401` may provide the same fallback signal if the webhook is delayed.
- **Data export:** include canonical imported activities and safe provenance (provider, external ID, sync timestamps/status) but exclude access/refresh tokens, client secret, raw webhook bodies, rate-limit internals, and other users' data.
- **Deletion request:** revoke/block credentials first; delete queued/retry work, raw payloads, canonical activities, integration/provenance, webhooks that remain attributable, and profile data according to the idempotent deletion workflow. Retain only minimized/anonymized deletion proof and disclosed encrypted backup expiry.
- **Reconnect later:** reuse the disconnected account only when the local athlete and external Strava athlete identity match; create a new credential and resync with deduplication. Previously imported activities remain and are updated rather than duplicated.

Remote revocation failure must not allow further local token use. The system records a safe retry state, attempts revocation according to official semantics, and deletes credentials according to the approved security policy rather than holding usable secrets indefinitely.

## 13. Testing plan

Tests use mocked HTTP transports/provider fixtures by default and never call the real Strava API in CI.

- **Unit:** authorization URL allow-listing, scope parsing, expiry decisions, sport/field mapping, idempotency-key derivation, error mapping, redaction, rate-header parsing, checkpoint behavior.
- **OAuth callback:** success, denial, missing/partial scopes, malformed response, external athlete mismatch, reconnect, conflicting account, one-use code error, provider timeout.
- **CSRF state:** entropy/format, user/athlete binding, expiry, missing state, tampering, replay, concurrent consumption, return destination allow-list.
- **Token refresh:** valid-token fast path, expiry safety window, one concurrent refresh, reload-after-lock, rotation, invalid refresh, `401` single retry, rollback, secret-free errors.
- **Secret redaction:** ORM/DTO repr, structured logs, exceptions, traces, audit, HTTP debug logging, API status and test snapshots contain no token/client-secret values.
- **Webhook:** validation token/challenge, response deadline design, malformed/oversized body, duplicate event, hash stability, out-of-order create/update/delete, deauthorization, fast durable acknowledgement, retry/dead letter, raw retention.
- **Activity mapping:** representative swim/ride/run/strength/unknown fixtures; nullable device fields; private/manual/trainer; metric units; UTC/timezone; obscured/missing data; unsupported-field gaps.
- **Rate limits:** all documented header pairs, malformed/missing headers, thresholds, `429` with/without `Retry-After`, jitter bounds, shared budget priority, pause/resume, no secret logging.
- **Failure/retry:** pagination partial commit, checkpoint resume, provider `401/403/404/429/5xx`, timeout, stale events, duplicate external activity, idempotent jobs.
- **Contract:** captured/synthetic fixtures shaped only from official Strava response schemas; mocked OAuth, athlete, activity, revoke, and webhook subscription responses.
- **Persistence:** uniqueness of integration external identity, `(integration, external_activity_id)`, webhook dedupe, and sync idempotency; credential isolation and deletion.

Later optional manual verification uses a registered development application/account: callback domain and redirect verification, consent/denial, granted scopes, token refresh/rotation, activity visibility behavior, webhook subscription validation under two seconds, create/update/delete/deauthorization delivery, rate-header observation, disconnect/revoke, and confirmation that logs contain no secrets. It is never required for normal unit tests and uses no production athlete data.

## 14. Implementation sequence

### 0.2.1 — Configuration and provider interfaces

- **Scope:** typed non-secret/secret configuration validation; HTTP transport boundary; DTO/error/redaction policy; interfaces for the six provider components.
- **Acceptance:** application fails safely when required production settings are missing; interface tests use mock transport; no secret repr/logging.
- **Excluded:** endpoints, token persistence use cases, real Strava calls, backfill, webhook routes.

### 0.2.2 — Connect endpoint and OAuth state

- **Scope:** authenticated connect route, allow-listed redirect construction, server-side state issue/TTL/binding/atomic consumption contract.
- **Development implementation:** one process-local, thread-safe in-memory store binds state to the temporary local MVP user for 600 seconds by default. It is replaceable through FastAPI dependencies and is explicitly unsuitable for restarts, multiple workers, multiple hosts, or production.
- **Acceptance:** valid request redirects to Strava with minimum scopes; CSRF state, replay, return target, authentication, and conflict tests pass.
- **Excluded:** callback exchange, credentials, sync, webhook subscription.

### 0.2.3 — Callback and token storage

- **Scope:** denial/success callback, code exchange, athlete/scope validation, transactional integration/credential creation and reconnect, safe browser result redirect.
- **Development implementation:** an injectable async `httpx` transport applies explicit connect/response timeouts; validated typed results redact secrets and discard the raw response. The endpoint returns a minimal no-store JSON result until a frontend redirect exists. Same-owner reconnect rotates both token values; a different local/external ownership pairing is rejected without reassignment.
- **Acceptance:** callback cases pass with mocked Strava; actual scopes persist; no token reaches logs/API/audit; conflict cleanup is safe.
- **Excluded:** historical import, webhook routes, automatic refresh beyond storage of expiry.

### 0.2.4 — Status and disconnect endpoints

- **Scope:** secret-free status projection; idempotent local disconnect; supported remote revocation; credential deletion and state/audit transitions.
- **Development implementation:** status is an owned read-only projection with no status-view audit. Disconnect uses injectable HTTP transport, explicit timeouts, Basic-auth revocation at `/oauth/revoke`, safe failure audits, and hard credential deletion only after success. SQLite tests verify behavior; live PostgreSQL concurrency remains unverified.
- **Acceptance:** owner sees accurate safe state; disconnect blocks use and removes credentials; revocation failures are retryable and visible without leaking secrets.
- **Excluded:** deleting imported activities, full account deletion, UI, webhooks.

### 0.2.5 — Token refresh

- **Scope:** expiry safety window, distributed/database locking, rotation, single safe `401` refresh retry, reconnect/revoked state transitions.
- **Acceptance:** concurrency and rotation tests prove newest-token persistence; failures do not loop or expose secrets.
- **Excluded:** general job scheduler, historical activity calls, webhooks.

### 0.2.6 — Tests and documentation

- **Scope:** complete mocked contract/security suite, operational runbook, privacy/security review, official-documentation recheck.
- **Acceptance:** all existing/new tests pass; no real API call in default suite; manual checklist is documented; production encryption remains an explicit release blocker if not delivered.
- **Excluded:** expanding scopes, activity write, backfill, webhook implementation.

### Later — historical import

- **Acceptance:** bounded paginated backfill resumes without duplicates, reports progress/partial failures, and pauses under shared rate pressure.
- **Excluded:** polling, activity write, analytics, automatic coaching changes.

### Later — webhooks

- **Acceptance:** HTTPS validation works within Strava's deadline; duplicate/out-of-order events and deauthorization are safe; callback acknowledges after durable receipt and processing runs in background.
- **Excluded:** treating envelope as full activity, synchronous provider fetch in callback, additional providers.

## 15. Decisions, assumptions, and unresolved questions

### Confirmed decisions

1. Request `read,activity:read_all`; never request write scopes.
2. Use browser redirects for connect/callback and minimal no-store JSON for status/disconnect; disconnect returns `200` for explicit idempotent outcomes.
3. Verify actual scopes and external athlete identity before persistence.
4. Keep tokens only in `OAuthCredential`; production encryption is mandatory.
5. Use a server-side single-use OAuth state bound to user/athlete/destination.
6. Use official webhook notifications plus background activity fetch, never polling.
7. Use provider/integration-scoped external IDs for deduplication, never as PKs.
8. Separate connection, sync, and canonical activity lifecycles.
9. Preserve imported activities on ordinary disconnect; deletion is separate.
10. Treat rate limits and provider schema as configurable/versioned external behavior.

### Security assumptions

- Deployed callbacks use HTTPS, trusted proxy configuration, secure cookies/session authentication, CSRF protection, strict redirect allow-lists, and centralized secret redaction.
- Secret manager/environment injection, encrypted database/backups, least-privilege database roles, and restricted operational access exist before production.
- Workers share a reliable lock/rate-state mechanism and durable queue; a process-local memory cache is insufficient for multi-process production.

### Deployment dependencies

- Registered Strava application with correct authorization callback domain and branding/terms compliance.
- Public HTTPS webhook callback that can acknowledge validation/events promptly.
- Secret storage for client secret, verification token, token-encryption keys, and state-signing/storage secrets.
- Durable transient OAuth-state store, background queue/worker, shared rate-limit state, scheduler, clock synchronization, and observability with redaction.
- A production PostgreSQL instance and an approved data-retention/deletion runbook.

### Questions before implementation

1. Which shared production store (PostgreSQL, Redis, or another durable TTL store) will replace the Sprint 0.2.2 in-memory store? The development TTL defaults to 600 seconds and remains configurable.
2. Is `activity:read_all` mandatory at first release, or will a clearly labeled `activity:read` limited mode be supported?
3. What historical import default range and athlete-selectable maximum balance product value and rate budget?
4. What refresh safety window and lock mechanism fit the initial single-worker deployment while remaining safe when scaled?
5. What frontend success/error routes and stable public message codes form the callback contract?
6. Which encryption/key-management service must be implemented before real credentials are persisted in production?
7. Should revocation failure retain encrypted token material solely for retry, or destroy it immediately and require manual remote cleanup? Security review must decide.
8. How will the provider mapping schema add maximum speed, cadence, weighted power, privacy, and manual flags without prematurely implementing the broader `ActivitySource` model?
9. What exact webhook deduplication-key canonicalization is proven stable against duplicate and multi-field update events?
10. What webhook/event/raw-response retention is required by the current Strava API Agreement and deployment jurisdiction at implementation time?
11. Does the initial deployment need a shared Redis-like rate/lock store, or can PostgreSQL advisory locks and rows satisfy both needs?
12. What operational process creates/rotates the application's single webhook subscription across environments without conflicts?

Official Strava documentation and API terms must be rechecked at implementation and release time. Where this specification proposes local policy beyond the official contract, it labels that choice rather than presenting it as Strava behavior.
