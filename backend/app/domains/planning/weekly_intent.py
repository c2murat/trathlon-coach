"""Weekly structure authority for explicit frequency; observational for NULL.

All collections in the public contracts are tuples, including provenance. A frozen
Pydantic model containing mutable dictionaries would not be an immutable intent.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import field_validator

from app.domains.planning.contracts import AvailabilitySlot, FrozenModel


SHADOW_VERSION = "0.8G.2E.1-weekly-intent-shadow-1"
SPORTS = ("running", "cycling", "swimming", "strength")
UNKNOWN_MINUTES = "NO_INDEPENDENT_WEEKLY_MINUTES_POLICY"
UNKNOWN_VOLUME = "EXISTING_SPORT_ALLOCATION_IS_LOAD_NOT_VOLUME"


class EvidenceValue(FrozenModel):
    name: str
    value: str | int | bool | None

    @field_validator("value", mode="before")
    @classmethod
    def exact_decimal_text(cls, value):
        # Decimal/string unions cannot round-trip unambiguously through JSON.
        # Evidence uses exact text; typed quantities elsewhere remain Decimal.
        return str(value) if isinstance(value, Decimal) else value


class IntentReason(FrozenModel):
    code: str
    source: str
    inputs: tuple[EvidenceValue, ...] = ()


class DurationTrace(FrozenModel):
    basis_role: str
    progression_source: str
    historical_window_days: int | None = None
    historical_activity_count: int | None = None
    historical_duration_seconds: int | None = None
    historical_mean_minutes: int | None = None
    historical_longest_minutes: Decimal | None = None
    pre_progression_minutes: int | None = None
    proposed_minutes: int | None = None
    cap_minutes: int | None = None
    floor_minutes: int | None = None
    final_legacy_minutes: int
    structurally_derived: bool = False
    decisions: tuple[IntentReason, ...]


class SportCompositionIntent(FrozenModel):
    sport: str
    sessions: int
    target_share: Decimal | None
    allocated_load: Decimal | None
    volume_minutes_target: int | None = None
    volume_unknown_reason: str = UNKNOWN_VOLUME
    reasons: tuple[IntentReason, ...]


class SessionIntent(FrozenModel):
    intent_id: str
    ordinal: int
    sport: str
    role: str
    importance: str
    key_session: bool
    preferred_day: int | None
    allocated_load: Decimal | None
    target_duration_minutes: int | None
    progression: DurationTrace
    compatibility_class: str
    related_goal_ids: tuple[UUID, ...]
    # Lossless adapter data for legacy prescription/workout rules, not new rules.
    purpose: str | None = None
    intensity: str | None = None
    optional: bool = False
    target_share: Decimal | None = None
    phase: str | None = None
    duration_source: str | None = None


class GoalIntentContext(FrozenModel):
    goal_id: UUID
    event_date: date
    category: str
    priority: str
    segment_sports: tuple[str, ...]
    segment_distances_m: tuple[int, ...]
    occurs_this_week: bool


class CompatibleDouble(FrozenModel):
    first_intent_id: str
    second_intent_id: str
    preference_cost: int
    source: str = "session_compatibility.pair_cost"


class IntentConstraint(FrozenModel):
    code: str
    source: str
    enabled: bool = True
    values: tuple[EvidenceValue, ...] = ()


class WeeklyPlanningIntent(FrozenModel):
    schema_version: int = 1
    algorithm_version: str = SHADOW_VERSION
    athlete_id: UUID
    context_fingerprint: str
    week_start: date
    week_end: date
    phase: str
    phase_exposure: tuple[EvidenceValue, ...]
    competition_context: tuple[GoalIntentContext, ...]
    frequency_source: Literal["explicit", "legacy"]
    requested_sessions: int | None
    phase_adjusted_sessions: int | None
    horizon_adjusted_sessions: int | None
    resolved_sessions: int
    frequency_capacity: int
    frequency_reasons: tuple[IntentReason, ...]
    requested_strength_sessions: int
    strength_sessions: int
    endurance_sessions: int
    desired_composition: tuple[SportCompositionIntent, ...]
    session_intents: tuple[SessionIntent, ...]
    key_session_roles: tuple[str, ...]
    weekly_load_budget: Decimal | None
    weekly_load_unknown_reason: str | None
    weekly_minutes_target: int | None = None
    weekly_minutes_unknown_reason: str = UNKNOWN_MINUTES
    historical_weekly_minutes: Decimal | None
    historical_weekly_load: Decimal | None
    unavailable_days: tuple[date, ...]
    preferred_free_days: tuple[int, ...]
    preferred_long_run_day: int | None
    preferred_long_bike_day: int | None
    max_daily_sessions: int
    max_weekly_sessions: int
    daily_availability: tuple[AvailabilitySlot, ...]
    doubles_enabled: bool
    compatible_doubles: tuple[CompatibleDouble, ...]
    progression_context: tuple[IntentReason, ...]
    hard_constraints: tuple[IntentConstraint, ...]
    soft_preferences: tuple[IntentConstraint, ...]
    reasons: tuple[IntentReason, ...]
    authority: Literal["shadow", "frequency_composition"] = "shadow"
    competition_sessions: int = 0
    duration_authority: Literal["legacy", "endurance_volume_intent"] = "legacy"

    @property
    def intended_session_count(self):
        return self.resolved_sessions

    @property
    def total_calendar_sessions(self):
        return self.resolved_sessions + self.competition_sessions

    def validate_structure(self):
        if (sum(c.sessions for c in self.desired_composition) != self.resolved_sessions
                or len(self.session_intents) != self.resolved_sessions
                or self.strength_sessions > self.resolved_sessions
                or Counter(s.sport for s in self.session_intents) != Counter({c.sport: c.sessions for c in self.desired_composition if c.sessions})):
            raise ValueError("SESSION_INTENT_COMPOSITION_INVARIANT")
        if self.horizon_adjusted_sessions != self.resolved_sessions:
            raise ValueError("SESSION_INTENT_FREQUENCY_INVARIANT")
        return self


class UnplacedSessionIntent(FrozenModel):
    session: SessionIntent
    reason: str


class StructuralWeekResult(FrozenModel):
    intent: WeeklyPlanningIntent
    requested_training_sessions: int
    phase_adjusted_sessions: int
    intended_sessions: int
    competition_sessions: int
    total_calendar_sessions: int
    generated: int
    generated_workout_count: int | None
    placed: int
    placed_intent_ids: tuple[str, ...]
    unplaced: tuple[UnplacedSessionIntent, ...]
    occupied_days: int
    double_days: int
    classification: Literal["exact_frequency", "phase_adjusted", "constrained_unplaced", "mismatch"]


class StructuralPlanningReport(FrozenModel):
    algorithm_version: str = "0.8G.2E.1-structural-intent-2"
    athlete_id: UUID
    context_fingerprint: str
    weeks: tuple[StructuralWeekResult, ...]


class ShadowDiscrepancy(FrozenModel):
    code: str
    kind: Literal["MISMATCH", "UNKNOWN", "OBSERVATION"]
    intent_id: str | None = None
    sport: str | None = None
    expected: str | int | None = None
    actual: str | int | None = None
    reason: str


class ActualSessionObservation(FrozenModel):
    intent_id: str | None
    sport: str
    role: str
    date: date
    target_duration_minutes: int | None
    allocated_load: Decimal | None
    key_session: bool


class WeeklyIntentComparison(FrozenModel):
    week_start: date
    actual_sessions: int
    actual_composition: tuple[EvidenceValue, ...]
    actual_roles: tuple[str, ...]
    actual_minutes: int | None
    actual_placement: tuple[ActualSessionObservation, ...]
    requested_target_met: bool | None
    resolved_generation_matches: bool
    fully_satisfies_intent: bool
    status: Literal["MATCH", "MISMATCH", "INCOMPLETE"]
    discrepancies: tuple[ShadowDiscrepancy, ...]


class WeeklyIntentShadow(FrozenModel):
    intent: WeeklyPlanningIntent
    comparison: WeeklyIntentComparison


class PlanningIntentShadowReport(FrozenModel):
    algorithm_version: str = SHADOW_VERSION
    mode: Literal["SHADOW_NO_GENERATION_EFFECT", "STRUCTURAL_INTENT"] = "SHADOW_NO_GENERATION_EFFECT"
    athlete_id: UUID
    context_fingerprint: str
    plan_fingerprint: str
    weeks: tuple[WeeklyIntentShadow, ...]


def evidence(**values):
    return tuple(EvidenceValue(name=k, value=v) for k, v in sorted(values.items()))


def reason(code, source, **inputs):
    return IntentReason(code=code, source=source, inputs=evidence(**inputs))


def build_weekly_intent(context, budget, baseline, config, needs, trace, previous_long, previous_dates,
                        quality_exposure, quality_debt):
    """Capture decisions ALREADY made by _needs, before _place and workouts.

    No frequency, duration, quality, cap or allocation formula is repeated here.
    Pair compatibility is queried from the same pure policy used by placement.
    """
    from app.domains.planning.session_compatibility import explicit_doubles, daily_capacity, pair_cost

    freq = trace["frequency"]
    frequency_reasons = tuple(IntentReason.model_validate(x) for x in freq["reasons"])
    duration_traces = tuple(DurationTrace.model_validate(x) for x in trace["durations"])
    counts = Counter(dict(freq["counts"]))
    allocations = {a.discipline: a for a in budget.disciplines}
    composition = tuple(SportCompositionIntent(
        sport=sport, sessions=counts[sport],
        target_share=allocations[sport].target_share if sport in allocations else None,
        allocated_load=allocations[sport].target_load if sport in allocations else None,
        reasons=tuple(r for r in frequency_reasons if not any(v.name == "sport" for v in r.inputs)
                      or any(v.name == "sport" and v.value == sport for v in r.inputs)) + (
            reason(allocations[sport].rationale_code if sport in allocations else "SPORT_NOT_ACTIVE",
                   "weekly_budget._discipline_budgets", sport=sport, resolved_count=counts[sport]),),
    ) for sport in SPORTS)
    sessions = tuple(SessionIntent(
        intent_id=f"{context.request.athlete_id}/{budget.week_start.isoformat()}/{index + 1}", ordinal=index + 1,
        sport=n.discipline, role=n.session_type.value, importance=n.priority.value, key_session=n.key,
        preferred_day=context.preferences.preferred_long_run_day if n.session_type.value == "RUN_LONG" else
                      context.preferences.preferred_long_bike_day if n.session_type.value == "BIKE_LONG" else None,
        allocated_load=n.load, target_duration_minutes=n.duration, progression=duration_traces[index],
        compatibility_class=f"{n.discipline}:{'KEY' if n.key else 'NON_KEY'}", related_goal_ids=n.goals,
        purpose=n.purpose.value, intensity=n.intensity.value, optional=n.optional,
        target_share=n.share, phase=n.phase.value,
    ) for index, n in enumerate(needs))
    pairs = tuple(CompatibleDouble(first_intent_id=sessions[j].intent_id, second_intent_id=sessions[i].intent_id,
                                   preference_cost=cost)
                  for i, a in enumerate(needs) for j, b in enumerate(needs[:i])
                  if (cost := pair_cost(a, b, context)) is not None)
    slots = {s.weekday: s for s in context.preferences.availability_slots}
    dates = tuple(budget.week_start + timedelta(days=i) for i in range(budget.available_days_in_horizon))
    progression = (
        reason("PREVIOUS_PLANNED_LONGS", "session_planning.build_session_plan", **{k: v for k, v in sorted(previous_long.items())}),
        reason("PREVIOUS_PLANNED_LONG_DATES", "session_planning.build_session_plan", **{k: str(v) for k, v in sorted(previous_dates.items())}),
        reason("QUALITY_EXPOSURE_BEFORE_WEEK", "session_planning.build_session_plan", **{str(k): v for k, v in sorted(quality_exposure.items(), key=lambda x: str(x[0]))}),
        reason("QUALITY_DEBT_BEFORE_WEEK", "session_planning.build_session_plan", **dict(sorted(quality_debt.items()))),
    ) + tuple(reason(a.code, "weekly_budget.build_weekly_budget_plan", factor=a.factor) for a in budget.adjustments)
    return WeeklyPlanningIntent(
        athlete_id=context.request.athlete_id, context_fingerprint=context.fingerprint,
        week_start=budget.week_start, week_end=budget.week_end, phase=budget.dominant_phase.value,
        phase_exposure=tuple(EvidenceValue(name=x.phase.value, value=x.days) for x in budget.phase_exposure),
        competition_context=tuple(GoalIntentContext(
            goal_id=g.competition_goal_id, event_date=g.event_date, category=g.category, priority=g.priority,
            segment_sports=tuple(s.sport for s in g.segments), segment_distances_m=tuple(s.distance_m for s in g.segments),
            occurs_this_week=budget.week_start <= g.event_date <= budget.week_end,
        ) for g in sorted(context.goals, key=lambda g: (g.event_date, str(g.competition_goal_id)))),
        frequency_source=freq["source"], requested_sessions=context.preferences.target_sessions_per_week,
        phase_adjusted_sessions=freq["phase_adjusted_sessions"], horizon_adjusted_sessions=freq["horizon_adjusted_sessions"],
        resolved_sessions=sum(counts.values()), frequency_capacity=freq["capacity"], frequency_reasons=frequency_reasons,
        requested_strength_sessions=context.preferences.strength_sessions_per_week,
        strength_sessions=counts["strength"], endurance_sessions=sum(counts[s] for s in SPORTS if s != "strength"),
        desired_composition=composition, session_intents=sessions,
        key_session_roles=tuple(s.role for s in sessions if s.key_session),
        weekly_load_budget=budget.target_load,
        weekly_load_unknown_reason="EXISTING_WEEKLY_LOAD_BASELINE_UNAVAILABLE" if budget.target_load is None else None,
        historical_weekly_minutes=baseline.weekly_training_minutes, historical_weekly_load=baseline.weekly_load,
        unavailable_days=tuple(d for d in dates if d.weekday() not in slots or slots[d.weekday()].available_minutes <= 0 or slots[d.weekday()].max_sessions <= 0),
        preferred_free_days=context.preferences.preferred_rest_days,
        preferred_long_run_day=context.preferences.preferred_long_run_day,
        preferred_long_bike_day=context.preferences.preferred_long_bike_day,
        max_daily_sessions=context.preferences.max_sessions_per_day, max_weekly_sessions=context.preferences.max_sessions_per_week,
        daily_availability=context.preferences.availability_slots,
        doubles_enabled=any(daily_capacity(context, s, config) >= 2 for s in context.preferences.availability_slots),
        compatible_doubles=pairs, progression_context=progression,
        hard_constraints=(
            IntentConstraint(code="DAILY_AVAILABILITY_AND_MINUTES", source="session_planning._place"),
            IntentConstraint(code="DAILY_AND_SLOT_SESSION_LIMITS", source="session_compatibility.daily_capacity"),
            IntentConstraint(code="WEEKLY_LIMIT_INCLUDES_COMPETITION", source="session_planning._frequency/validate_session_plan"),
            IntentConstraint(code="COMPETITION_DAY_EXCLUSIVE", source="session_planning._place"),
            IntentConstraint(code="NO_STRENGTH_TWO_DAYS_BEFORE_EVENT", source="session_planning._place"),
            IntentConstraint(code="SAME_LONG_SPACING", source="session_planning._place",
                             values=evidence(minimum_days=config.minimum_same_long_spacing_days)),
            IntentConstraint(code="PAIR_COMPATIBILITY_AND_NO_TWO_KEYS", source="session_compatibility.pair_cost",
                             enabled=explicit_doubles(context)),
        ),
        soft_preferences=(
            IntentConstraint(code="PREFERRED_FREE_DAYS", source="PlanningPreferences",
                             values=tuple(EvidenceValue(name="weekday", value=d) for d in context.preferences.preferred_rest_days)),
            IntentConstraint(code="PREFERRED_LONG_DAYS", source="PlanningPreferences",
                             values=evidence(run=context.preferences.preferred_long_run_day, bike=context.preferences.preferred_long_bike_day)),
            IntentConstraint(code="STRENGTH_SEPARATION", source="weekly_distribution.score"),
            IntentConstraint(code="KEY_SEPARATION", source="weekly_distribution.score",
                             values=evidence(minimum_days=config.minimum_gap_between_key_sessions_days)),
            IntentConstraint(code="COMPATIBLE_DOUBLES_WHEN_BENEFICIAL", source="weekly_distribution.score"),
        ),
        reasons=(reason("SHADOW_ONLY_EXISTING_DECISIONS", "session_planning._needs", rule_version=config.version),
                 reason(UNKNOWN_MINUTES, "weekly_budget.WeeklyTrainingBudget"),
                 reason(UNKNOWN_VOLUME, "weekly_budget.DisciplineBudget")),
        competition_sessions=len(budget.competition_goal_ids),
    )


def create_weekly_planning_intent(context, budget, baseline, config, previous_long, previous_dates,
                                  quality_exposure, quality_debt, quality_trace, historical_exposure, *, coherent_volume=False):
    """Own frequency/composition once; reuse legacy role/duration/allocation rules."""
    from app.domains.planning.session_planning import _frequency, _needs
    frequency_trace = {}
    counts = _frequency(context, budget, config, frequency_trace, constrain_capacity=False)
    before_exposure, before_debt = dict(quality_exposure), dict(quality_debt)
    trace = {}
    needs = _needs(context, budget, config, previous_long, quality_exposure, quality_debt,
                   quality_trace, historical_exposure, trace, resolved_counts=counts, frequency_trace=frequency_trace)
    intent = build_weekly_intent(context, budget, baseline, config, needs, trace, previous_long, previous_dates,
                                before_exposure, before_debt)
    intent = intent.model_copy(update={
        "authority": "frequency_composition",
        "reasons": (reason("FREQUENCY_COMPOSITION_AUTHORITY", "weekly_intent.create_weekly_planning_intent"),)
                   + tuple(r for r in intent.reasons if r.code != "SHADOW_ONLY_EXISTING_DECISIONS"),
    })
    if coherent_volume:
        from app.domains.planning.volume_intent import activate_endurance_volume
        intent = activate_endurance_volume(context, intent, config)
    return intent.validate_structure()


def needs_from_intent(intent):
    """No frequency/type selection here. Project the fixed list losslessly."""
    from app.domains.planning.session_planning import _Need, SessionType, SessionPurpose, IntensityClass, SessionPriority
    from app.domains.planning.season_structure import SeasonPhase
    return [_Need(s.sport, SessionType(s.role), SessionPurpose(s.purpose), IntensityClass(s.intensity),
                  SessionPriority(s.importance), s.key_session, s.optional, s.target_duration_minutes,
                  s.target_share, s.allocated_load, s.related_goal_ids, SeasonPhase(s.phase))
            for s in intent.session_intents]


def structural_week_result(intent, week, unplaced_reasons):
    comparison = compare_weekly_intent(intent, week)
    placed_ids = tuple(s.intent_id for s in comparison.actual_placement if s.intent_id is not None)
    if len(placed_ids) != len(set(placed_ids)) or len(placed_ids) != comparison.actual_sessions:
        raise ValueError("PLACED_INTENT_IDENTITY_INVARIANT")
    unplaced = tuple(UnplacedSessionIntent(session=s, reason=unplaced_reasons.get(s.intent_id, "NO_FEASIBLE_ASSIGNMENT_WITHIN_SEARCH_BUDGET"))
                     for s in intent.session_intents if s.intent_id not in placed_ids)
    if len(placed_ids) + len(unplaced) != len(intent.session_intents):
        raise ValueError("SESSION_INTENT_LOST_WITHOUT_REASON")
    daily = Counter(s.date for s in week.sessions if s.discipline != "competition")
    return StructuralWeekResult(
        intent=intent, requested_training_sessions=intent.requested_sessions,
        phase_adjusted_sessions=intent.phase_adjusted_sessions, intended_sessions=intent.resolved_sessions,
        competition_sessions=intent.competition_sessions, total_calendar_sessions=len(week.sessions),
        generated=len(intent.session_intents), generated_workout_count=None,
        placed=comparison.actual_sessions, placed_intent_ids=placed_ids, unplaced=unplaced,
        occupied_days=len(daily), double_days=sum(n > 1 for n in daily.values()),
        classification="constrained_unplaced" if unplaced else
                       "phase_adjusted" if intent.phase_adjusted_sessions != intent.requested_sessions else "exact_frequency",
    )


def compare_weekly_intent(intent: WeeklyPlanningIntent, week) -> WeeklyIntentComparison:
    """Pure observation of the FINAL legacy calendar; never mutates it."""
    sessions = tuple(s for s in week.sessions if s.discipline != "competition")
    actual_counts = Counter(s.discipline for s in sessions)
    discrepancies = []

    def issue(code, kind, why, session=None, expected=None, actual=None, sport=None):
        discrepancies.append(ShadowDiscrepancy(
            code=code, kind=kind, intent_id=session.intent_id if session else None,
            sport=session.sport if session else sport, expected=expected, actual=actual, reason=why,
        ))

    expected_total = intent.horizon_adjusted_sessions
    if expected_total is not None and len(sessions) != expected_total:
        issue("SESSION_COUNT_MISMATCH", "MISMATCH", "REQUESTED_AFTER_HORIZON_VS_GENERATED; see frequency_reasons for capacity/competition",
              expected=expected_total, actual=len(sessions))
    if len(sessions) != intent.resolved_sessions:
        issue("RESOLVED_SESSION_COUNT_MISMATCH", "MISMATCH", "NEEDS_LOST_OR_ADDED_AFTER_COMPOSITION",
              expected=intent.resolved_sessions, actual=len(sessions))
    if len(intent.session_intents) != intent.resolved_sessions:
        issue("SESSION_INTENT_COUNT_MISMATCH", "MISMATCH", "EXISTING_NEEDS_DID_NOT_MATERIALIZE_RESOLVED_FREQUENCY",
              expected=intent.resolved_sessions, actual=len(intent.session_intents))
    for composition in intent.desired_composition:
        if actual_counts[composition.sport] != composition.sessions:
            issue("SPORT_COMPOSITION_MISMATCH", "MISMATCH", "PRE_PLACEMENT_COUNT_VS_FINAL_CALENDAR",
                  expected=composition.sessions, actual=actual_counts[composition.sport], sport=composition.sport)

    unmatched = list(range(len(sessions)))
    observations = []
    generation_matches = len(sessions) == intent.resolved_sessions and all(
        actual_counts[c.sport] == c.sessions for c in intent.desired_composition)
    for desired in intent.session_intents:
        candidates = [i for i in unmatched if sessions[i].discipline == desired.sport and sessions[i].session_type.value == desired.role]
        candidates.sort(key=lambda i: (sessions[i].target_duration_minutes != desired.target_duration_minutes,
                                       sessions[i].target_load != desired.allocated_load, sessions[i].key_session != desired.key_session,
                                       sessions[i].date, i))
        if not candidates:
            issue("MISSING_ROLE", "MISMATCH", desired.role, desired, expected=desired.role)
            generation_matches = False
            continue
        index = candidates[0]; unmatched.remove(index); actual = sessions[index]
        observations.append(ActualSessionObservation(intent_id=desired.intent_id, sport=actual.discipline,
            role=actual.session_type.value, date=actual.date, target_duration_minutes=actual.target_duration_minutes,
            allocated_load=actual.target_load, key_session=actual.key_session))
        if actual.target_duration_minutes != desired.target_duration_minutes or desired.progression.final_legacy_minutes != desired.target_duration_minutes:
            issue("UNEXPLAINED_DURATION", "MISMATCH", "FINAL_DURATION_DIFFERS_FROM_CAPTURED_LEGACY_RULE", desired,
                  expected=desired.target_duration_minutes, actual=actual.target_duration_minutes)
            generation_matches = False
        if actual.target_load != desired.allocated_load:
            issue("ALLOCATED_LOAD_MISMATCH", "MISMATCH", "PRE_PLACEMENT_ALLOCATION_CHANGED", desired,
                  expected=str(desired.allocated_load), actual=str(actual.target_load))
            generation_matches = False
        if actual.key_session != desired.key_session:
            issue("KEY_ROLE_MISMATCH", "MISMATCH", "KEY_CLASSIFICATION_CHANGED", desired)
            generation_matches = False
        trace = desired.progression
        if trace.cap_minutes is not None and trace.proposed_minutes is not None and trace.proposed_minutes >= trace.cap_minutes:
            issue("CAP_REACHED", "OBSERVATION", "PROPOSED_AT_OR_ABOVE_EXISTING_CAP; modifiers/availability may subsequently replace it",
                  desired, expected=trace.cap_minutes, actual=trace.final_legacy_minutes)
        if desired.sport == "strength" and not trace.structurally_derived:
            issue("HISTORICAL_STRENGTH_DURATION" if trace.historical_mean_minutes is not None else "DEFAULT_STRENGTH_DURATION",
                  "OBSERVATION", "DURATION_NOT_DERIVED_FROM_SETS_REPS_RESTS", desired, actual=trace.final_legacy_minutes)
        if desired.preferred_day is not None and actual.date.weekday() != desired.preferred_day:
            issue("PREFERRED_DAY_MISS", "MISMATCH", "FINAL_CALENDAR_DIFFERS_FROM_EXPLICIT_LONG_DAY", desired,
                  expected=desired.preferred_day, actual=actual.date.weekday())
    for index in unmatched:
        actual = sessions[index]
        issue("UNEXPECTED_ROLE", "MISMATCH", actual.session_type.value, actual=actual.session_type.value, sport=actual.discipline)
        observations.append(ActualSessionObservation(intent_id=None, sport=actual.discipline, role=actual.session_type.value,
            date=actual.date, target_duration_minutes=actual.target_duration_minutes, allocated_load=actual.target_load, key_session=actual.key_session))
        generation_matches = False
    used_free = sorted({s.date.weekday() for s in sessions if s.date.weekday() in intent.preferred_free_days})
    if used_free:
        issue("PREFERRED_FREE_DAY_MISS", "MISMATCH", "FINAL_TRAINING_USES_PREFERRED_FREE_DAY", actual=",".join(map(str, used_free)))
    actual_minutes = sum(s.target_duration_minutes for s in sessions) if all(s.target_duration_minutes is not None for s in sessions) else None
    if intent.weekly_minutes_target is None:
        issue("WEEKLY_MINUTES_INTENT_UNKNOWN", "UNKNOWN", intent.weekly_minutes_unknown_reason)
    elif actual_minutes != intent.weekly_minutes_target:
        issue("WEEKLY_MINUTES_MISMATCH", "MISMATCH", "INTENT_VS_FINAL_DURATION", expected=intent.weekly_minutes_target, actual=actual_minutes)
    for composition in intent.desired_composition:
        if composition.sessions and composition.volume_minutes_target is None:
            issue("SPORT_VOLUME_INTENT_UNKNOWN", "UNKNOWN", composition.volume_unknown_reason, sport=composition.sport)
    if intent.weekly_load_budget is None:
        issue("WEEKLY_LOAD_INTENT_UNKNOWN", "UNKNOWN", intent.weekly_load_unknown_reason)
    mismatch = any(d.kind == "MISMATCH" for d in discrepancies)
    unknown = any(d.kind == "UNKNOWN" for d in discrepancies)
    return WeeklyIntentComparison(
        week_start=week.week_start, actual_sessions=len(sessions),
        actual_composition=tuple(EvidenceValue(name=s, value=actual_counts[s]) for s in SPORTS),
        actual_roles=tuple(s.session_type.value for s in sessions), actual_minutes=actual_minutes,
        actual_placement=tuple(sorted(observations, key=lambda s: (s.date, s.role, s.intent_id or ""))),
        requested_target_met=len(sessions) == expected_total if expected_total is not None else None,
        resolved_generation_matches=generation_matches, fully_satisfies_intent=not mismatch and not unknown,
        status="MISMATCH" if mismatch else "INCOMPLETE" if unknown else "MATCH", discrepancies=tuple(discrepancies),
    )


def seed_prescriptions(intent, week, needs, budget, config):
    from app.domains.planning.session_planning import _prescribe_need, SessionPlacementDecision
    placed = prescriptions_by_intent(intent, week)
    return tuple(placed.get(s.intent_id) or _prescribe_need(needs[i], budget, config, week.week_start,
                 SessionPlacementDecision(code="UNPLACED_INTENT_SEED")) for i, s in enumerate(intent.session_intents))


def prescriptions_by_intent(intent, week):
    observations = compare_weekly_intent(intent, week).actual_placement
    remaining = list(week.sessions)
    result = {}
    for observation in observations:
        if observation.intent_id is None:
            raise ValueError("PRESCRIPTION_WITHOUT_SESSION_INTENT")
        index = next(i for i, s in enumerate(remaining) if s.date == observation.date and
                     s.discipline == observation.sport and s.session_type.value == observation.role and
                     s.target_duration_minutes == observation.target_duration_minutes and s.target_load == observation.allocated_load)
        result[observation.intent_id] = remaining.pop(index)
    return result


def _build_with_reports(context, season, budgets, config, structural_intent, workout_observer=None, coherent_volume=False):
    from app.domains.planning.session_planning import build_session_plan

    intents = []
    results = []
    plan = build_session_plan(context, season, budgets, config, intent_observer=intents.append,
                              structural_observer=results.append, structural_intent=structural_intent, workout_observer=workout_observer,
                              coherent_volume=coherent_volume)
    report = PlanningIntentShadowReport(
        mode="STRUCTURAL_INTENT" if results else "SHADOW_NO_GENERATION_EFFECT",
        athlete_id=context.request.athlete_id, context_fingerprint=context.fingerprint, plan_fingerprint=plan.fingerprint,
        weeks=tuple(WeeklyIntentShadow(intent=intent, comparison=compare_weekly_intent(intent, week))
                    for intent, week in zip(intents, plan.weeks, strict=True)),
    )
    structural = StructuralPlanningReport(athlete_id=context.request.athlete_id, context_fingerprint=context.fingerprint,
                                          weeks=tuple(results)) if results else None
    return plan, report, structural


def build_session_plan_with_shadow(context, season, budgets, config, *, structural_intent=True):
    """Compatibility entry point; NULL remains observational, explicit owns structure."""
    plan, report, _ = _build_with_reports(context, season, budgets, config, structural_intent)
    return plan, report


def build_session_plan_with_intent(context, season, budgets, config, *, workout_observer=None, coherent_volume=False):
    return _build_with_reports(context, season, budgets, config, True, workout_observer, coherent_volume)
