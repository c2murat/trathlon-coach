"""Volume policy projection with controlled endurance duration authority.

The existing duration policies are a bottom-up volume source. Load shares are
recorded as evidence, never relabelled as minute shares. A top-down independent
volume policy does not yet exist; this report deliberately makes that visible.
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from pydantic import model_validator

from app.domains.planning.contracts import FrozenModel
from app.domains.planning.weekly_intent import SPORTS, DurationTrace, IntentReason, WeeklyPlanningIntent, reason, prescriptions_by_intent
from app.domains.planning.workout_builder import workout_duration_seconds


class RoleVolumeIntent(FrozenModel):
    intent_id: str
    sport: str
    role: str
    target_duration_intent: int
    sport_share: Decimal
    previous_week_value: int | None
    rolling_reference: Decimal | None
    progression_factor: Decimal | None
    progression_increment_minutes: int | None
    proposed_value: int
    cap: int | None
    floor: int | None
    final_value: int
    trace: DurationTrace
    reasons: tuple[IntentReason, ...]


class SportVolumeIntent(FrozenModel):
    sport: str
    minutes_target: int
    volume_share: Decimal
    legacy_load_share: Decimal | None
    roles: tuple[RoleVolumeIntent, ...]


class WeeklyVolumeIntent(FrozenModel):
    planning_intent: WeeklyPlanningIntent
    week_start: date
    phase: str
    weekly_load_budget: Decimal | None
    weekly_minutes_target: int
    run_minutes_target: int
    bike_minutes_target: int
    swim_minutes_target: int
    strength_minutes_target: int
    source: str = "SUM_EXISTING_PREPLACEMENT_ROLE_DURATION_POLICIES"
    allocation_method: str = "BOTTOM_UP_EXISTING_ROLES_NOT_LOAD_WEIGHTS"
    historical_weekly_minutes: Decimal | None
    load_provenance: tuple[IntentReason, ...]
    sports: tuple[SportVolumeIntent, ...]
    weekly_capacity_minutes: int
    session_capacity: int
    aggregate_excess_minutes: int
    reasons: tuple[IntentReason, ...]

    @model_validator(mode="after")
    def reconcile(self):
        if self.planning_intent.weekly_minutes_target != self.weekly_minutes_target:
            raise ValueError("WEEKLY_MINUTES_SHADOW_SNAPSHOT")
        if sum(s.minutes_target for s in self.sports) != self.weekly_minutes_target:
            raise ValueError("SPORT_VOLUME_RECONCILIATION")
        if tuple(s.minutes_target for s in self.sports) != (
                self.run_minutes_target, self.bike_minutes_target,
                self.swim_minutes_target, self.strength_minutes_target):
            raise ValueError("NAMED_SPORT_VOLUME_RECONCILIATION")
        for sport in self.sports:
            if sum(r.target_duration_intent for r in sport.roles) != sport.minutes_target:
                raise ValueError("ROLE_VOLUME_RECONCILIATION")
            if any(r.final_value != r.target_duration_intent or r.final_value < 0 for r in sport.roles):
                raise ValueError("ROLE_VOLUME_VALUE")
        return self


class StrengthStructureObservation(FrozenModel):
    intent_id: str
    exercises: tuple[str, ...]
    movement_patterns: tuple[str, ...]
    sets: tuple[int | None, ...]
    reps: tuple[int | None, ...]
    rest_seconds: tuple[int | None, ...]
    rpe_bounds: tuple[str, ...]
    duration_seconds: int | None
    duration_source: str = "PRESCRIBED_TIME_DIVIDED_AMONG_EXERCISES"
    independently_derivable: bool = False
    reason: str = "NO_REPETITION_TEMPO_OR_INDEPENDENT_TRANSITION_TIME_POLICY"


class RoleVolumeObservation(FrozenModel):
    intent_id: str
    placed: bool
    prescription_minutes: int | None
    workout_minutes: Decimal | None
    minutes_variance: Decimal | None
    reason: str


class WeeklyVolumeComparison(FrozenModel):
    intent: WeeklyVolumeIntent
    actual_minutes: Decimal | None
    known_workout_minutes: Decimal
    prescription_minutes: int
    minutes_variance: Decimal | None
    minutes_variance_percent: Decimal | None = None
    minutes_tolerance: Decimal | None = None
    minutes_tolerance_source: str = "NO_EXISTING_VOLUME_TOLERANCE_DIAGNOSTIC_ONLY"
    estimated_load: Decimal | None
    load_variance: Decimal | None
    constrained_minutes: int
    capacity_assessment: str
    daily_violations: tuple[date, ...]
    diagnostics: tuple[str, ...]
    sessions: tuple[RoleVolumeObservation, ...]
    strength_volume_intent: tuple[StrengthStructureObservation, ...]


class VolumeShadowReport(FrozenModel):
    algorithm_version: str = "0.8G.2E.1-volume-shadow-3"
    mode: str = "SHADOW_NO_WORKOUT_OR_ARTIFACT_EFFECT"
    context_fingerprint: str
    weeks: tuple[WeeklyVolumeComparison, ...]


def activate_endurance_volume(context, intent, config):
    """Consume one volume projection; never apply progression a second time.

    Existing duration rules supply the candidates. Strength is deliberately
    excluded from authority even though its fixed minutes reconcile the total.
    """
    projection = project_volume_intent(context, intent, config)
    roles = {r.intent_id: r for sport in projection.sports for r in sport.roles}
    sessions = []
    for session in intent.session_intents:
        if session.sport == "strength":
            sessions.append(session.model_copy(update={"duration_source": "historical_legacy"}))
            continue
        target = roles[session.intent_id].target_duration_intent
        trace = session.progression
        # The projection already applies policy caps/floors and availability.
        # Do not silently accept a future projection that bypasses a hard cap.
        if trace.cap_minutes is not None and target > trace.cap_minutes:
            raise ValueError("VOLUME_INTENT_EXCEEDS_EXISTING_CAP")
        if trace.floor_minutes is not None and target < trace.floor_minutes:
            raise ValueError("VOLUME_INTENT_BELOW_EXISTING_FLOOR")
        decisions = trace.decisions + (reason("ENDURANCE_VOLUME_DURATION_AUTHORITY", "volume_intent.activate_endurance_volume",
            duration_source="coherent_volume_intent", weekly_minutes_target=projection.weekly_minutes_target,
            sport_minutes_target=next(s.minutes_target for s in projection.sports if s.sport == session.sport),
            session_role_target=target, legacy_candidate=session.target_duration_minutes),)
        if trace.cap_minutes is not None and trace.proposed_minutes is not None and trace.proposed_minutes > trace.cap_minutes:
            decisions += (reason("VOLUME_CONSTRAINED_BY_CAP", trace.progression_source,
                                proposed=trace.proposed_minutes, cap=trace.cap_minutes, final=target),)
        sessions.append(session.model_copy(update={"target_duration_minutes": target,
            "duration_source": "coherent_volume_intent", "progression": trace.model_copy(update={"decisions": decisions})}))
    return projection.planning_intent.model_copy(update={"session_intents": tuple(sessions),
        "duration_authority": "endurance_volume_intent"})


def project_volume_intent(context, intent, config, previous=None):
    """Called before workout builder. No duration formula is reimplemented."""
    previous = previous or {}
    total = sum(s.target_duration_minutes for s in intent.session_intents)
    totals = {sport: sum(s.target_duration_minutes for s in intent.session_intents if s.sport == sport) for sport in SPORTS}
    occurrence = defaultdict(int)
    roles = defaultdict(list)
    for s in intent.session_intents:
        occurrence[s.role] += 1
        prior = previous.get((s.role, occurrence[s.role]))
        t = s.progression
        increment = None
        factor = None
        decisions = list(t.decisions)
        for decision in t.decisions:
            inputs = {v.name: v.value for v in decision.inputs}
            if decision.code in {"LONG_PREVIOUS_PLUS_STEP", "SWIM_PREVIOUS_PLUS_STEP_LIMIT"}:
                increment = int(inputs["step"])
            if decision.code in {"TAPER_REPLACES_PROPOSAL", "DELOAD_REPLACES_CAPPED_PROPOSAL", "RECOVERY_DURATION_FACTOR_AND_FLOOR"}:
                factor = Decimal(str(inputs["factor"]))
        proposed = t.proposed_minutes if t.proposed_minutes is not None else s.target_duration_minutes
        if t.cap_minutes is not None and proposed >= t.cap_minutes and s.target_duration_minutes == t.cap_minutes:
            decisions.append(reason("CAP_REACHED", t.progression_source, proposed=proposed, cap=t.cap_minutes,
                                    final=s.target_duration_minutes))
        if increment is not None and proposed > s.target_duration_minutes:
            decisions.append(reason("PROGRESSION_LIMITED", t.progression_source))
        decisions.append(reason("EXISTING_ROLE_DURATION_SOURCE", t.progression_source,
                                prior_same_role=prior, phase=intent.phase))
        if s.sport == "strength":
            decisions.append(reason("STRENGTH_DURATION_NOT_STRUCTURE_DERIVED", "workout_builder._strength_steps",
                                    historical_mean=t.historical_mean_minutes, default=config.default_strength_minutes))
        roles[s.sport].append(RoleVolumeIntent(
            intent_id=s.intent_id, sport=s.sport, role=s.role, target_duration_intent=s.target_duration_minutes,
            sport_share=Decimal(s.target_duration_minutes) / totals[s.sport] if totals[s.sport] else Decimal(0),
            previous_week_value=prior, rolling_reference=t.historical_longest_minutes if t.historical_longest_minutes is not None else
            Decimal(t.historical_mean_minutes) if t.historical_mean_minutes is not None else None,
            progression_factor=factor, progression_increment_minutes=increment, proposed_value=proposed,
            cap=t.cap_minutes, floor=t.floor_minutes, final_value=s.target_duration_minutes, trace=t, reasons=tuple(decisions)))
    slots = {s.weekday: s for s in intent.daily_availability}
    competition_days = {g.event_date for g in intent.competition_context if g.occurs_this_week}
    capacity = sessions = 0
    from app.domains.planning.session_compatibility import daily_capacity
    for offset in range((intent.week_end - intent.week_start).days + 1):
        day = intent.week_start + timedelta(days=offset)
        slot = slots.get(day.weekday())
        if day in intent.unavailable_days or day in competition_days or slot is None:
            continue
        limit = daily_capacity(context, slot, config)
        if limit > 0:
            capacity += slot.available_minutes
            sessions += limit
    return WeeklyVolumeIntent(
        planning_intent=intent.model_copy(update={
            "weekly_minutes_target": total, "weekly_minutes_unknown_reason": "",
            "desired_composition": tuple(c.model_copy(update={"volume_minutes_target": totals[c.sport],
                "volume_unknown_reason": ""}) for c in intent.desired_composition),
            "reasons": tuple(r for r in intent.reasons if r.code not in {
                "NO_INDEPENDENT_WEEKLY_MINUTES_POLICY", "EXISTING_SPORT_ALLOCATION_IS_LOAD_NOT_VOLUME"}) +
                (reason("SHADOW_VOLUME_SUM_OF_EXISTING_ROLE_POLICIES", "session_planning._duration"),),
        }),
        week_start=intent.week_start, phase=intent.phase, weekly_load_budget=intent.weekly_load_budget,
        weekly_minutes_target=total, historical_weekly_minutes=intent.historical_weekly_minutes,
        run_minutes_target=totals["running"], bike_minutes_target=totals["cycling"],
        swim_minutes_target=totals["swimming"], strength_minutes_target=totals["strength"],
        load_provenance=(reason("EXISTING_WEEKLY_LOAD_BUDGET", "weekly_budget.build_weekly_budget_plan",
                                target=intent.weekly_load_budget),) + intent.progression_context,
        sports=tuple(SportVolumeIntent(sport=sport, minutes_target=totals[sport],
            volume_share=Decimal(totals[sport]) / total if total else Decimal(0),
            legacy_load_share=next(c.target_share for c in intent.desired_composition if c.sport == sport),
            roles=tuple(roles[sport])) for sport in SPORTS),
        weekly_capacity_minutes=capacity, session_capacity=min(sessions, max(0, intent.max_weekly_sessions - intent.competition_sessions)),
        aggregate_excess_minutes=max(0, total - capacity),
        reasons=(reason("MINUTES_INDEPENDENT_OF_LOAD", "session_planning._duration"),
                 reason("LOAD_WEIGHTS_AFFECT_COMPOSITION_NOT_MINUTE_SHARES", "weekly_budget._discipline_budgets"),
                 reason("AGGREGATE_CAPACITY_IS_UPPER_BOUND_NOT_PLACEMENT_PROOF", "weekly_distribution")))


class VolumeShadowBuild:
    """One planning pass, local state only. prepare runs before content.prepare."""
    def __init__(self, context, config):
        self.context = context
        self.config = config
        self.intents = {}
        self.previous = {}

    def prepare(self, intent, prescriptions=()):
        if intent.week_start in self.intents:
            raise ValueError("VOLUME_WEEK_PREPARED_TWICE")
        volume = project_volume_intent(self.context, intent, self.config, self.previous)
        self.intents[intent.week_start] = volume
        occurrence = defaultdict(int)
        self.previous = {}
        for session in intent.session_intents:
            occurrence[session.role] += 1
            self.previous[(session.role, occurrence[session.role])] = session.target_duration_minutes
        return volume

    def finish(self, plan, shadow, drafts, load_reconciliation=None):
        # Drafts have exactly the same order as the final prescriptions.
        by_prescription = {id(s): d for s, d in zip((s for w in plan.weeks for s in w.sessions), drafts, strict=True)}
        loads = {w.week_start: w for w in load_reconciliation.weeks} if load_reconciliation else {}
        results = []
        for week, captured in zip(plan.weeks, shadow.weeks, strict=True):
            original = captured.intent
            volume = self.intents[week.week_start]
            placed = prescriptions_by_intent(original, week)
            observations = []; strength = []; daily = defaultdict(list)
            for session in original.session_intents:
                prescription = placed.get(session.intent_id)
                draft = by_prescription[id(prescription)] if prescription is not None else None
                definition = draft.definition if draft else None
                seconds = workout_duration_seconds(definition) if definition else None
                actual = Decimal(seconds) / 60 if seconds is not None else None
                variance = actual - session.target_duration_minutes if actual is not None else None
                observations.append(RoleVolumeObservation(intent_id=session.intent_id, placed=prescription is not None,
                    prescription_minutes=prescription.target_duration_minutes if prescription else None,
                    workout_minutes=actual, minutes_variance=variance,
                    reason="UNPLACED_INTENT" if prescription is None else "WORKOUT_DURATION_UNKNOWN" if actual is None else
                    "MINUTES_RECONCILED" if variance == 0 else "EXPLICIT_WORKOUT_DURATION_DIVERGENCE"))
                if prescription is not None:
                    daily[prescription.date].append(prescription)
                if definition and session.sport == "strength":
                    nodes = definition.steps
                    strength.append(StrengthStructureObservation(intent_id=session.intent_id,
                        exercises=tuple(n.title or "" for n in nodes), movement_patterns=tuple(n.movement_pattern or "" for n in nodes),
                        sets=tuple(n.sets for n in nodes), reps=tuple(n.reps for n in nodes),
                        rest_seconds=tuple(n.rest_seconds for n in nodes), duration_seconds=seconds,
                        rpe_bounds=tuple(f"{n.target.minimum}/{n.target.maximum}" for n in nodes)))
            slots = {s.weekday: s for s in original.daily_availability}
            from app.domains.planning.session_compatibility import daily_capacity
            violations = tuple(sorted(day for day, ss in daily.items() if day in original.unavailable_days or day.weekday() not in slots or
                len(ss) > daily_capacity(self.context, slots[day.weekday()], self.config) or
                sum(s.target_duration_minutes or 0 for s in ss) > slots[day.weekday()].available_minutes or
                sum(Decimal(workout_duration_seconds(by_prescription[id(s)].definition) or 0) / 60
                    for s in ss if by_prescription[id(s)].definition is not None) > slots[day.weekday()].available_minutes))
            known = sum((s.workout_minutes for s in observations if s.workout_minutes is not None), Decimal(0))
            actual = known if all(s.workout_minutes is not None for s in observations if s.placed) else None
            missing = sum(s.target_duration_minutes for s in original.session_intents if s.intent_id not in placed)
            variance = actual - volume.weekly_minutes_target if actual is not None else None
            diagnostics = ["MINUTES_UNKNOWN" if variance is None else "MINUTES_RECONCILED" if variance == 0 else
                           "MINUTES_OVER_TARGET" if variance > 0 else "MINUTES_UNDER_TARGET"]
            if missing or volume.aggregate_excess_minutes or violations:
                diagnostics.append("CAPACITY_CONSTRAINED" if volume.aggregate_excess_minutes or violations else "PLACEMENT_CONSTRAINED")
            diagnostics.extend(sorted({r.code for s in volume.sports for role in s.roles for r in role.reasons
                                       if r.code in {"CAP_REACHED", "PROGRESSION_LIMITED", "VOLUME_CONSTRAINED_BY_CAP"}}))
            load = loads.get(week.week_start)
            results.append(WeeklyVolumeComparison(intent=volume, actual_minutes=actual, known_workout_minutes=known,
                prescription_minutes=sum(s.target_duration_minutes or 0 for s in placed.values()), minutes_variance=variance,
                minutes_variance_percent=variance / volume.weekly_minutes_target * 100 if variance is not None and volume.weekly_minutes_target else
                    Decimal(0) if variance == 0 else None,
                estimated_load=load.prescribed_estimated_total if load else None, load_variance=load.variance if load else None,
                constrained_minutes=missing, capacity_assessment="FINAL_DAILY_VIOLATION" if violations else
                "AGGREGATE_OVER_CAPACITY" if volume.aggregate_excess_minutes else "UNPLACED_NOT_PROOF_OF_INFEASIBILITY" if missing else "FINAL_PLACEMENT_FITS",
                daily_violations=violations, diagnostics=tuple(diagnostics), sessions=tuple(observations), strength_volume_intent=tuple(strength)))
        active = any(w.intent.planning_intent.duration_authority == "endurance_volume_intent" for w in results)
        return VolumeShadowReport(context_fingerprint=self.context.fingerprint, weeks=tuple(results),
            mode="ENDURANCE_VOLUME_AUTHORITY_STRENGTH_LEGACY" if active else "SHADOW_NO_WORKOUT_OR_ARTIFACT_EFFECT")
