"""Diagnostic projection of final workouts through existing load calculators.

No allocated load, planning context, or session type enters the estimator.
No workout mutation or automatic budget scaling occurs here.
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from app.domains.planning.contracts import FrozenModel
from app.domains.planning.models import StructuredWorkoutDefinition
from app.domains.training_load.calculators import calculate
from app.domains.training_load.models import Sport, TrainingLoadInput
from app.domains.manual_strength.calculators import calculate_manual_strength_load
from app.domains.manual_strength.models import BodyRegion, ManualStrengthLoadInput

VERSION = "0.8G.2E.1-prescribed-load-1"


def rounded(value):
    return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class PrescribedLoadEstimate(FrozenModel):
    algorithm_version: str = VERSION
    value: Decimal | None
    minimum: Decimal | None
    maximum: Decimal | None
    known_subtotal: Decimal
    method: str = "EXISTING_METHODS_LOAD_INTERVAL_MIDPOINT"
    methods: tuple[str, ...]
    quality: Literal['MEDIUM', 'LOW', 'UNAVAILABLE']
    coverage: Literal['COMPLETE', 'PARTIAL', 'UNAVAILABLE']
    known_duration_seconds: int
    estimated_duration_seconds: int
    unknown_steps: int
    warnings: tuple[str, ...]


class SessionLoadDiagnostic(FrozenModel):
    date: date
    sport: str
    session_type: str
    allocated_load: Decimal | None
    prescribed_load_estimate: PrescribedLoadEstimate


class WeeklyLoadReconciliation(FrozenModel):
    week_start: date
    weekly_load_budget: Decimal | None
    allocated_total: Decimal | None
    prescribed_estimated_total: Decimal | None
    prescribed_estimate_minimum: Decimal | None
    prescribed_estimate_maximum: Decimal | None
    known_subtotal: Decimal
    variance: Decimal | None
    absolute_variance: Decimal | None
    variance_percent: Decimal | None
    tolerance: Decimal
    within_tolerance: bool | None
    status: str
    coverage: str
    quality: str
    # Defaults keep older diagnostic snapshots readable; application reads and
    # acceptance always reconstruct these values from the verified prescription.
    reconciliation_state: Literal['RECONCILED', 'NOT_RECONCILED', 'REVIEW_REQUIRED', 'INSUFFICIENT_QUALITY'] = 'INSUFFICIENT_QUALITY'
    quality_warning: bool = True
    blocking_confidence: bool = False
    acceptance_blocked: bool = False
    competition_sessions: int
    sessions: tuple[SessionLoadDiagnostic, ...]


class PlannedLoadReconciliation(FrozenModel):
    algorithm_version: str = VERSION
    acceptance_policy: str = 'ESTIMATE_QUALITY_GUARD_V2'
    mode: str = 'DIAGNOSTIC_NO_SCALING'
    tolerance_source: str = 'SessionPlanningConfig.load_tolerance'
    weeks: tuple[WeeklyLoadReconciliation, ...]

    @property
    def acceptance_blocked(self) -> bool:
        return any(week.acceptance_blocked for week in self.weeks)


def _leaves(nodes, multiplier=1):
    # Traverse the tree once; repetitions multiply contributions, never expand it.
    for node in nodes:
        if node.kind == 'repeat':
            yield from _leaves(node.steps, multiplier * node.repetitions)
        else:
            yield node, multiplier


def _step_estimates(sport, node, seconds):
    target = node.target
    if (sport == 'strength' and target is not None and target.metric == 'rpe'
            and target.mode == 'absolute_range' and target.minimum is not None
            and target.maximum is not None and 1 <= target.minimum <= target.maximum <= 10
            and float(target.minimum).is_integer() and float(target.maximum).is_integer()):
        # Existing strength method is linear in duration. Normalize at 60 minutes
        # to respect its integer-minute input, then prorate actual step seconds.
        # FULL_BODY is a required calculator argument, not inferred exercise data;
        # body regions do not participate in this formula or leave this adapter.
        values = [calculate_manual_strength_load(ManualStrengthLoadInput(
            duration_minutes=60, perceived_exertion=int(rpe), body_regions=(BodyRegion.FULL_BODY,),
        )).load_value * seconds / 3600 for rpe in (target.minimum, target.maximum)]
        return min(values), max(values), 'strength_rpe', 'LOW', False, 'PRESCRIBED_RPE_IS_NOT_OBSERVED_RPE'
    compatible = {
        ('cycling', 'power'): ('watts', 'average_power_watts', 'ftp_watts'),
        ('running', 'pace'): ('seconds_per_km', 'average_pace_seconds_per_km', 'running_threshold_pace_seconds_per_km'),
        ('swimming', 'swim_pace'): ('seconds_per_100m', 'swim_pace_seconds_per_100m', 'swim_css_seconds_per_100m'),
    }
    binding = compatible.get((sport, target.metric)) if target is not None else None
    if (binding and target.mode == 'percent_reference' and target.resolved_unit == binding[0]
            and target.reference_unit == binding[0] and target.reference_value is not None
            and target.reference_value > 0 and target.resolved_minimum is not None
            and target.resolved_maximum is not None and target.resolved_minimum > 0):
        results = [calculate(TrainingLoadInput(sport=Sport(sport), moving_time_seconds=seconds,
            **{binding[1]: bound, binding[2]: target.reference_value}))
            for bound in (target.resolved_minimum, target.resolved_maximum)]
        return min(r.load for r in results), max(r.load for r in results), results[0].method.value, 'MEDIUM', False, None
    # No guessed conversion of RPE, zones or HR into power/pace. Reuse only
    # the existing low-quality duration fallback, explicitly marking coverage.
    if sport == 'strength':
        rate = calculate_manual_strength_load(ManualStrengthLoadInput(
            duration_minutes=60, perceived_exertion=None, body_regions=(BodyRegion.FULL_BODY,),
        )).load_value
        value = rate * seconds / 3600
        method = 'strength_duration'
    else:
        result = calculate(TrainingLoadInput(sport=Sport(sport), moving_time_seconds=seconds))
        value, method = result.load, result.method.value
    return value, value, method, 'LOW', True, 'DURATION_ONLY_TARGET_NOT_SUPPORTED'


def estimate_prescribed_load(definition: StructuredWorkoutDefinition | None) -> PrescribedLoadEstimate:
    if definition is None or definition.sport not in {'cycling', 'running', 'swimming', 'strength'}:
        return PrescribedLoadEstimate(value=None, minimum=None, maximum=None, known_subtotal=0,
            methods=(), quality='UNAVAILABLE', coverage='UNAVAILABLE', known_duration_seconds=0,
            estimated_duration_seconds=0, unknown_steps=1, warnings=('NO_SUPPORTED_WORKOUT',))
    lower = upper = Decimal(0)
    known = estimated = unknown = 0
    low_quality = partial = False
    methods = set(); warnings = set()
    for node, repeats in _leaves(definition.steps):
        duration = node.duration
        seconds = duration.seconds if duration.mode == 'time' else duration.estimated_seconds if duration.mode == 'distance' else None
        if seconds is None or seconds <= 0:
            unknown += repeats
            warnings.add('UNKNOWN_STEP_DURATION')
            continue
        if duration.mode == 'distance':
            estimated += seconds * repeats
            low_quality = True
            warnings.add('DISTANCE_STEP_USES_ESTIMATED_SECONDS')
        lo, hi, method, quality, fallback, warning = _step_estimates(definition.sport, node, seconds)
        lower += Decimal(str(lo)) * repeats
        upper += Decimal(str(hi)) * repeats
        known += seconds * repeats
        low_quality |= quality == 'LOW'
        partial |= fallback
        methods.add(method)
        if warning:
            warnings.add(warning)
    midpoint = rounded((lower + upper) / 2)
    return PrescribedLoadEstimate(value=midpoint if not unknown else None,
        minimum=rounded(lower) if not unknown else None, maximum=rounded(upper) if not unknown else None,
        known_subtotal=midpoint, methods=tuple(sorted(methods)),
        quality='UNAVAILABLE' if not known else 'LOW' if low_quality or unknown else 'MEDIUM',
        coverage='UNAVAILABLE' if not known else 'PARTIAL' if partial or unknown else 'COMPLETE',
        known_duration_seconds=known, estimated_duration_seconds=estimated, unknown_steps=unknown,
        warnings=tuple(sorted(warnings)))


def reconciliation_state(*, within_tolerance, coverage, quality, session_count, blocking_confidence=False):
    # Duration-only fallback is not a complete target-based estimate. Preserve
    # explicit uncertainty rather than treating its number as certification.
    if coverage != 'COMPLETE' or quality == 'UNAVAILABLE' or not session_count or within_tolerance is None:
        return 'INSUFFICIENT_QUALITY'
    # Method quality is not calibrated confidence for a budget acceptance gate.
    # No current prescription estimator supplies blocking confidence, including
    # MEDIUM: it projects target intervals, not observed effort. A future guard
    # requires separate, server-derived evidence; metadata cannot authorize it.
    if not within_tolerance and (quality not in {'MEDIUM', 'HIGH'} or not blocking_confidence):
        return 'REVIEW_REQUIRED'
    return 'RECONCILED' if within_tolerance else 'NOT_RECONCILED'


def reconcile_plan_load(plan, workout_drafts, tolerance=None):
    from app.domains.planning.session_planning import SessionPlanningConfig
    if tolerance is None:
        tolerance = SessionPlanningConfig(version='diagnostic', algorithm_version='diagnostic').load_tolerance
    if len(workout_drafts) != sum(len(w.sessions) for w in plan.weeks):
        raise ValueError('one workout draft per prescription required')
    weeks = []; position = 0
    for week in plan.weeks:
        sessions = []; competitions = 0
        for s in week.sessions:
            draft = workout_drafts[position]; position += 1
            if s.discipline == 'competition':
                competitions += 1
                continue  # Budget and estimates both exclude unestimated competition.
            sessions.append(SessionLoadDiagnostic(date=s.date, sport=s.discipline,
                session_type=s.session_type.value, allocated_load=s.target_load,
                prescribed_load_estimate=estimate_prescribed_load(draft.definition)))
        estimates = [s.prescribed_load_estimate for s in sessions]
        complete_values = all(e.value is not None for e in estimates)
        value = sum((e.value for e in estimates), Decimal(0)) if complete_values else None
        minimum = sum((e.minimum for e in estimates), Decimal(0)) if complete_values else None
        maximum = sum((e.maximum for e in estimates), Decimal(0)) if complete_values else None
        allocated = sum((s.allocated_load for s in sessions), Decimal(0)) if all(s.allocated_load is not None for s in sessions) else None
        budget = week.budget_target_load
        variance = rounded(value - budget) if value is not None and budget is not None else None
        percent = rounded(variance / budget * 100) if variance is not None and budget else Decimal(0) if variance == 0 else None
        within = abs(variance) <= abs(budget) * tolerance if variance is not None else None
        coverage = 'UNAVAILABLE' if not estimates else 'COMPLETE' if all(e.coverage == 'COMPLETE' for e in estimates) else 'PARTIAL' if any(e.known_duration_seconds for e in estimates) else 'UNAVAILABLE'
        quality = 'UNAVAILABLE' if coverage == 'UNAVAILABLE' else 'LOW' if any(e.quality != 'MEDIUM' for e in estimates) else 'MEDIUM'
        state = reconciliation_state(within_tolerance=within, coverage=coverage, quality=quality, session_count=len(sessions))
        weeks.append(WeeklyLoadReconciliation(week_start=week.week_start, weekly_load_budget=budget,
            allocated_total=allocated, prescribed_estimated_total=value,
            prescribed_estimate_minimum=minimum, prescribed_estimate_maximum=maximum,
            known_subtotal=sum((e.known_subtotal for e in estimates), Decimal(0)), variance=variance,
            absolute_variance=abs(variance) if variance is not None else None, variance_percent=percent,
            tolerance=tolerance, within_tolerance=within,
            status='UNAVAILABLE' if coverage == 'UNAVAILABLE' else 'PARTIAL_COVERAGE' if coverage != 'COMPLETE' else 'WITHIN_TOLERANCE' if within else 'OUTSIDE_TOLERANCE' if within is False else 'UNKNOWN_BUDGET',
            coverage=coverage, quality=quality, reconciliation_state=state,
            quality_warning=quality != 'MEDIUM' or coverage != 'COMPLETE',
            acceptance_blocked=state == 'NOT_RECONCILED',
            competition_sessions=competitions, sessions=tuple(sessions)))
    return PlannedLoadReconciliation(weeks=tuple(weeks))
