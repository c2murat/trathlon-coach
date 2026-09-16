from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.domains.training_status.interpretation import (
    TrainingStatusInterpreter, TrainingStatusObservation, TrainingStatusInterpretation,
    FitnessTrend, FatigueTrend, FormState, OverallState, NotableTrend, InterpretationReason,
)

ATHLETE = UUID(int=1)
CUTOFF = date(2026, 9, 16)


def observations(*, fitness_delta=0, fatigue_delta=0, form=0, age=0, warmup=False):
    fitness_delta, fatigue_delta, form = map(lambda value: Decimal(str(value)), (fitness_delta, fatigue_delta, form))
    return tuple(TrainingStatusObservation(athlete_id=ATHLETE, date=CUTOFF-timedelta(days=age+7-index),
        fitness=Decimal(100)-fitness_delta+fitness_delta*index/7,
        fatigue=Decimal(100)-form-fatigue_delta+fatigue_delta*index/7,
        form=form, is_warmup=warmup, timezone_name="UTC", training_load_algorithm_version="0.7b.1",
        manual_strength_algorithm_version="0.7e.1", training_status_algorithm_version="0.7f.1") for index in range(8))


def interpret(rows=None, **kwargs):
    return TrainingStatusInterpreter().interpret(athlete_id=ATHLETE, as_of_date=CUTOFF,
        observations=observations(**kwargs) if rows is None else rows)


@pytest.mark.parametrize("delta,expected", [(-1.01,"FALLING"),(-1,"STABLE"),(0,"STABLE"),(1,"STABLE"),(1.01,"RISING")])
def test_fitness_boundaries(delta, expected):
    assert interpret(fitness_delta=delta).fitness_trend == expected


@pytest.mark.parametrize("delta,expected", [(-1.01,"FALLING"),(-1,"STABLE"),(0,"STABLE"),(1,"STABLE"),(1.01,"RISING"),(9.99,"RISING"),(10,"RISING_FAST"),(10.01,"RISING_FAST")])
def test_fatigue_boundaries(delta, expected):
    assert interpret(fatigue_delta=delta).fatigue_trend == expected


@pytest.mark.parametrize("value,expected", [(-20.01,"HIGHLY_LOADED"),(-20,"HIGHLY_LOADED"),(-19.99,"LOADED"),
    (-5.01,"LOADED"),(-5,"BALANCED"),(0,"BALANCED"),(5,"BALANCED"),(5.01,"FRESH"),(19.99,"FRESH"),(20,"VERY_FRESH"),(20.01,"VERY_FRESH")])
def test_form_boundaries(value, expected):
    result = interpret(form=value)
    assert result.form_state == expected
    assert result.form == Decimal(str(value))


@pytest.mark.parametrize("fitness,fatigue,form,state,notable", [
    (2,10,-30,"HIGH_LOAD","FATIGUE_RISING_FASTER_THAN_FITNESS"),
    (2,10,-10,"LOADED","FATIGUE_RISING_FASTER_THAN_FITNESS"),
    (2,-2,0,"RECOVERING","RECOVERY_TREND"),
    (0,-2,2,"RECOVERING","RECOVERY_TREND"),
    (0,0,0,"BALANCED","BOTH_STABLE"),
    (-2,-3,0,"REDUCED_LOAD","BOTH_FALLING"),
    (-2,-3,-30,"HIGH_LOAD","BOTH_FALLING"),
    (2,2,0,"BUILDING","NO_NOTABLE_TREND"),
    (0,0,10,"FRESH","BOTH_STABLE"),
])
def test_combined_states_and_precedence(fitness, fatigue, form, state, notable):
    result = interpret(fitness_delta=fitness, fatigue_delta=fatigue, form=form)
    assert result.overall_state == state
    assert result.notable_trend_key == notable


@pytest.mark.parametrize("difference,expected", [(1,"NO_NOTABLE_TREND"),(1.01,"FATIGUE_RISING_FASTER_THAN_FITNESS")])
def test_relative_delta_boundary(difference, expected):
    assert interpret(fitness_delta=2, fatigue_delta=2+difference).notable_trend_key == expected


@pytest.mark.parametrize("kind", ["empty","single","seven","gap","stale"])
def test_insufficient_never_invents_trends(kind):
    rows = observations(age=2 if kind == "stale" else 0)
    rows = () if kind == "empty" else rows[-1:] if kind == "single" else rows[1:] if kind == "seven" else rows[:3]+rows[4:] if kind == "gap" else rows
    result = interpret(rows)
    assert result.overall_state == OverallState.INSUFFICIENT_DATA
    assert result.fitness_trend == FitnessTrend.INSUFFICIENT_DATA
    assert result.fatigue_trend == FatigueTrend.INSUFFICIENT_DATA
    assert result.fitness_delta is result.fatigue_delta is None
    if kind == "stale": assert InterpretationReason.STALE_STATUS in result.reason_codes


def test_yesterday_is_recent_and_warmup_is_explicit():
    result = interpret(age=1, warmup=True)
    assert result.overall_state == OverallState.BALANCED
    assert InterpretationReason.MODEL_WARMUP in result.reason_codes


def test_cutoff_determinism_roundtrip_and_frozen_models():
    rows = observations(fitness_delta=3, fatigue_delta=12, form=-25)
    result = interpret(rows)
    future = rows[-1].model_copy(update={"date": CUTOFF+timedelta(days=1), "fitness": Decimal(999)})
    assert interpret(tuple(reversed(rows))+(future,)).model_dump_json() == result.model_dump_json()
    assert TrainingStatusInterpretation.model_validate_json(result.model_dump_json()) == result
    with pytest.raises(ValidationError): result.fitness = 0


@pytest.mark.parametrize("change", [{"athlete_id":UUID(int=2)}, {"timezone_name":"Europe/Madrid"}, {"training_status_algorithm_version":"other"}])
def test_cross_athlete_or_configuration_is_rejected(change):
    rows = observations()
    with pytest.raises(ValueError, match="mismatch|configuration"):
        interpret((rows[0].model_copy(update=change),)+rows[1:])


def test_duplicate_dates_rejected():
    rows = observations()
    with pytest.raises(ValueError, match="duplicate"):
        interpret(rows+(rows[0],))


def test_stored_form_is_not_recomputed_from_rounded_values():
    rows = observations()
    result = interpret(rows[:-1]+(rows[-1].model_copy(update={"form":Decimal("0.01")}),))
    assert result.form == Decimal("0.01")


@pytest.mark.parametrize("invalid", ["NaN","Infinity","-Infinity"])
def test_nonfinite_inputs_rejected(invalid):
    with pytest.raises(ValidationError):
        TrainingStatusObservation.model_validate({**observations()[0].model_dump(),"fitness":invalid})


def long_history(*, fitness_start=20, fatigue_start=20,
                 fitness_end=(40,41,42,43,44,44,44,44),
                 fatigue_end=(50,60,70,80,90,88,85,80)):
    template = observations()[0]
    fitness = [fitness_start]*14 + list(fitness_end)
    fatigue = [fatigue_start]*14 + list(fatigue_end)
    return tuple(template.model_copy(update={"date":CUTOFF-timedelta(days=21-index),
        "fitness":Decimal(str(f)), "fatigue":Decimal(str(a)), "form":Decimal(str(f))-Decimal(str(a))})
        for index, (f,a) in enumerate(zip(fitness,fatigue)))


def test_elevated_fatigue_with_recent_recovery_turn_and_stable_fitness():
    result = interpret(long_history())
    assert result.broader_context.fatigue_trend == "RISING_FAST"
    assert result.short_term.fatigue_trend == "RISING_FAST"
    assert result.recent.fatigue.direction == "FALLING"
    assert result.recent.fatigue.delta == -10
    assert result.recent.fatigue.changed_direction
    assert result.recent.recovery_turn
    assert result.recent.fitness.direction == "STABLE"
    assert result.broader_context.fitness_trend == "RISING"
    assert {"FATIGUE_ELEVATED_OVER_21D", "FATIGUE_RECENTLY_FALLING", "FITNESS_HIGHER_OVER_21D",
        "FITNESS_RECENTLY_STABLE", "RECENT_RECOVERY_TURN"} <= set(result.reason_codes)


@pytest.mark.parametrize("start,end,direction", [(100,(90,85,80,75,70,65,60,55),"FALLING"),
    (20,(30,35,40,45,50,55,60,65),"RISING_FAST")])
def test_fatigue_same_direction_across_horizons(start,end,direction):
    result = interpret(long_history(fatigue_start=start,fatigue_end=end))
    assert result.short_term.fatigue_trend == result.broader_context.fatigue_trend == direction
    assert not result.recent.fatigue.changed_direction
    assert not result.recent.recovery_turn


def test_fitness_falls_weekly_but_remains_above_three_weeks_ago():
    result = interpret(long_history(fitness_end=(50,49,48,47,46,45,44,43)))
    assert result.short_term.fitness_trend == "FALLING"
    assert result.broader_context.fitness_trend == "RISING"
    assert result.recent.fitness.direction == "FALLING"


def test_incomplete_broader_context_keeps_valid_short_term():
    for rows in (long_history()[1:], long_history()[:5]+long_history()[6:], observations()):
        result = interpret(rows)
        assert result.broader_context.fitness_trend == "INSUFFICIENT_DATA"
        assert result.broader_context.fitness_delta is None
        assert result.short_term.fitness_trend != "INSUFFICIENT_DATA"
        assert "INSUFFICIENT_BROADER_CONTEXT" in result.reason_codes


@pytest.mark.parametrize("delta,direction", [(-1.01,"FALLING"),(-1,"STABLE"),(1,"STABLE"),(1.01,"RISING")])
def test_broader_context_exact_boundaries(delta,direction):
    result = interpret(long_history(fitness_start=Decimal(44)-Decimal(str(delta))))
    assert result.broader_context.fitness_trend == direction


@pytest.mark.parametrize("tail,direction,turn", [((90,89.5,89.2,89),"STABLE",False),
    ((90,89.5,89.2,88.99),"FALLING",True), ((90,89,91,89),"MIXED",False),
    ((90,90,89.5,88),"FALLING",True), ((90,90.5,90.8,91),"STABLE",False),
    ((90,90.5,90.8,91.01),"RISING",False)])
def test_recent_boundaries_and_no_turn_from_oscillation(tail,direction,turn):
    result = interpret(long_history(fatigue_end=(50,60,70,80)+tail))
    assert result.recent.fatigue.direction == direction
    assert result.recent.fatigue.changed_direction == turn


@pytest.mark.parametrize("prior_start,turn", [(89,False),(88.99,True)])
def test_turn_requires_prior_change_outside_deadband(prior_start,turn):
    result = interpret(long_history(fatigue_end=(prior_start,89,89,90,90,88,86,85)))
    assert result.recent.fatigue.changed_direction == turn


@pytest.mark.parametrize("improvement,expected", [(1,False),(1.01,True)])
def test_recovery_turn_requires_stored_form_improvement(improvement,expected):
    rows = long_history()
    rows = rows[:-1]+(rows[-1].model_copy(update={"form":rows[-4].form+Decimal(str(improvement))}),)
    assert interpret(rows).recent.recovery_turn == expected


def test_multihorizon_determinism_cutoff_and_isolation():
    rows = long_history()
    future = rows[-1].model_copy(update={"date":CUTOFF+timedelta(days=1)})
    assert interpret(rows).model_dump_json() == interpret(tuple(reversed(rows))+(future,)).model_dump_json()
    with pytest.raises(ValueError,match="mismatch"):
        interpret((rows[0].model_copy(update={"athlete_id":UUID(int=2)}),)+rows[1:])


def test_recent_fitness_direction_change_is_explicit():
    result = interpret(long_history(fitness_end=(40,41,42,43,44,43,42,41)))
    assert result.recent.fitness.changed_direction
    assert result.recent.fitness.direction == "FALLING"


@pytest.mark.parametrize("delta,expected", [(9.99,"RISING"),(10,"RISING_FAST"),(10.01,"RISING_FAST")])
def test_broader_fatigue_magnitude_boundary(delta,expected):
    result = interpret(long_history(fatigue_start=Decimal(80)-Decimal(str(delta))))
    assert result.broader_context.fatigue_trend == expected


def test_stale_rows_cannot_describe_any_current_horizon():
    rows = tuple(row.model_copy(update={"date":row.date-timedelta(days=2)}) for row in long_history())
    result = interpret(rows)
    assert result.short_term.fatigue_trend == result.broader_context.fatigue_trend == "INSUFFICIENT_DATA"
    assert result.recent.fatigue.direction == "INSUFFICIENT_DATA"
    assert not result.recent.recovery_turn
