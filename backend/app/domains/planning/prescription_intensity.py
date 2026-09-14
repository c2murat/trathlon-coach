"""Explicit prescription levels; no level catalog is authorized by policy C.6.

Zone sets, template progressions and capability blends are not interchangeable
prescriptions. The production catalog therefore returns NO_SUPPORTED_LADDER.
The contracts below define exact identification and adjacency without inventing
ranges, converting units, interpolating or interpreting evidence confidence.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from app.domains.planning.contracts import FrozenModel, PlanningContext, context_fingerprint
from app.domains.planning.session_planning import SessionType


PRESCRIPTION_INTENSITY_LEVEL_VERSION = "0.8G.2C.6"


class PrescriptionTargetRange(FrozenModel):
    minimum: Decimal = Field(gt=0, allow_inf_nan=False)
    maximum: Decimal = Field(gt=0, allow_inf_nan=False)
    unit: str

    @model_validator(mode="after")
    def valid_range(self):
        if self.minimum > self.maximum:
            raise ValueError("prescription target range cannot be inverted")
        return self


class LevelStepDirection(StrEnum):
    PROGRESSION = "PROGRESSION"
    REGRESSION = "REGRESSION"


class LevelResolutionStatus(StrEnum):
    LADDER_AVAILABLE = "LADDER_AVAILABLE"
    IDENTIFIED = "IDENTIFIED"
    ADJACENT_LEVEL = "ADJACENT_LEVEL"
    NO_SUPPORTED_LADDER = "NO_SUPPORTED_LADDER"
    CURRENT_LEVEL_NOT_IDENTIFIED = "CURRENT_LEVEL_NOT_IDENTIFIED"
    BOUNDARY = "BOUNDARY"
    GUARDED = "GUARDED"
    UNSUPPORTED = "UNSUPPORTED"


class LevelResolutionReason(StrEnum):
    NO_SAME_PRESCRIPTION_LEVELS = "NO_SAME_PRESCRIPTION_LEVELS"
    EXACT_CURRENT_LEVEL = "EXACT_CURRENT_LEVEL"
    EXACT_TARGET_MISMATCH = "EXACT_TARGET_MISMATCH"
    IMMEDIATE_NEIGHBOR = "IMMEDIATE_NEIGHBOR"
    MAXIMUM_LEVEL = "MAXIMUM_LEVEL"
    MINIMUM_LEVEL = "MINIMUM_LEVEL"
    UNIT_MISMATCH = "UNIT_MISMATCH"
    UNSUPPORTED_SESSION_TYPE = "UNSUPPORTED_SESSION_TYPE"
    UNSUPPORTED_TARGET_KIND = "UNSUPPORTED_TARGET_KIND"
    STRENGTH_UNSUPPORTED = "STRENGTH_UNSUPPORTED"
    INVALID_CAPABILITY_REFERENCE = "INVALID_CAPABILITY_REFERENCE"
    BOUNDS_UNAVAILABLE = "BOUNDS_UNAVAILABLE"


class PrescriptionLevelAthleteMismatchError(ValueError):
    pass


class PrescriptionLevelContextMismatchError(ValueError):
    pass


class PrescriptionCapabilityReference(FrozenModel):
    athlete_id: UUID
    cutoff_date: date
    context_fingerprint: str
    capability_fingerprint: str
    reference: str
    value: Decimal = Field(gt=0, allow_inf_nan=False)
    unit: str


# Compatibility identities, not intensity ratios or a cross-session ladder.
TARGET_SEMANTICS = {
    "running": ("RUN_PACE", "seconds_per_km", "running_threshold_pace_seconds_per_km", "threshold_pace", "RUN_"),
    "cycling": ("POWER", "watts", "cycling_ftp_watts", "FTP", "BIKE_"),
    "swimming": ("SWIM_PACE", "seconds_per_100m", "swimming_css_seconds_per_100m", "CSS", "SWIM_"),
}


class PrescriptionIntensityLevel(FrozenModel):
    sport: str
    session_type: SessionType
    target_kind: str
    level_id: str = Field(min_length=1)
    index: int = Field(ge=0)
    semantic_role: str = Field(min_length=1)
    target_range: PrescriptionTargetRange
    unit: str
    source: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    capability_reference: PrescriptionCapabilityReference
    prescription_bounds: PrescriptionTargetRange | None = None
    capability_bounds: PrescriptionTargetRange | None = None
    version: str = PRESCRIPTION_INTENSITY_LEVEL_VERSION

    @model_validator(mode="after")
    def consistent_level(self):
        expected = TARGET_SEMANTICS.get(self.sport)
        if expected is None or (self.target_kind, self.unit) != expected[:2]:
            raise ValueError("level sport, kind and unit must agree")
        if not self.session_type.value.startswith(expected[4]):
            raise ValueError("level session type must match sport")
        if self.target_range.unit != self.unit or self.capability_reference.unit != self.unit:
            raise ValueError("level units must agree")
        if self.capability_reference.reference != expected[3]:
            raise ValueError("level capability reference must match sport")
        for bounds in (self.prescription_bounds, self.capability_bounds):
            if bounds is not None and (bounds.unit != self.unit or not (
                bounds.minimum <= self.target_range.minimum <= self.target_range.maximum <= bounds.maximum
            )):
                raise ValueError("level target must be inside its declared bounds")
        return self


class PrescriptionIntensityLadder(FrozenModel):
    """Increasing intensity order; a singleton cannot provide an adjacent step."""
    ladder_id: str = Field(min_length=1)
    athlete_id: UUID
    cutoff_date: date
    context_fingerprint: str
    sport: str
    session_type: SessionType
    target_kind: str
    unit: str
    semantic_role: str
    levels: tuple[PrescriptionIntensityLevel, ...] = Field(min_length=1)
    version: str = PRESCRIPTION_INTENSITY_LEVEL_VERSION

    @model_validator(mode="after")
    def ordered_levels(self):
        if tuple(level.index for level in self.levels) != tuple(range(len(self.levels))):
            raise ValueError("levels must have consecutive indices in declared order")
        if len({level.level_id for level in self.levels}) != len(self.levels):
            raise ValueError("duplicate level identifiers")
        if len({level.target_range for level in self.levels}) != len(self.levels):
            raise ValueError("duplicate level ranges")
        reference = self.levels[0].capability_reference
        for level in self.levels:
            if (level.sport, level.session_type, level.target_kind, level.unit, level.semantic_role, level.version) != (
                self.sport, self.session_type, self.target_kind, self.unit, self.semantic_role, self.version,
            ):
                raise ValueError("ladder must describe one prescription semantic and version")
            if level.capability_reference != reference:
                raise ValueError("ladder must use one capability context")
        if (reference.athlete_id, reference.cutoff_date, reference.context_fingerprint) != (
            self.athlete_id, self.cutoff_date, self.context_fingerprint,
        ):
            raise ValueError("ladder capability scope must agree")
        for lower, higher in zip(self.levels, self.levels[1:]):
            before, after = lower.target_range, higher.target_range
            ordered = (after.minimum > before.minimum and after.maximum > before.maximum) if self.sport == "cycling" else (
                after.minimum < before.minimum and after.maximum < before.maximum
            )
            if not ordered:
                raise ValueError("levels must strictly increase prescription intensity")
        return self


class PrescriptionLevelResolution(FrozenModel):
    athlete_id: UUID
    cutoff_date: date
    context_fingerprint: str
    sport: str
    session_type: str
    target_kind: str
    status: LevelResolutionStatus
    reason_codes: tuple[LevelResolutionReason, ...]
    current_range: PrescriptionTargetRange | None = None
    ladder_id: str | None = None
    level_before: PrescriptionIntensityLevel | None = None
    level_after: PrescriptionIntensityLevel | None = None
    direction: LevelStepDirection | None = None
    version: str = PRESCRIPTION_INTENSITY_LEVEL_VERSION

    @model_validator(mode="after")
    def coherent_result(self):
        if self.status in {LevelResolutionStatus.IDENTIFIED, LevelResolutionStatus.ADJACENT_LEVEL, LevelResolutionStatus.BOUNDARY}:
            if self.level_before is None or self.ladder_id is None or self.current_range != self.level_before.target_range:
                raise ValueError("identified level requires an exact current target")
        if self.status == LevelResolutionStatus.ADJACENT_LEVEL:
            if self.level_after is None or self.direction is None:
                raise ValueError("adjacent resolution requires both levels and direction")
            offset = 1 if self.direction == LevelStepDirection.PROGRESSION else -1
            if self.level_after.index != self.level_before.index + offset:
                raise ValueError("adjacent resolution cannot skip levels")
            before, after = self.level_before, self.level_after
            if before.capability_reference != after.capability_reference or before.semantic_role != after.semantic_role:
                raise ValueError("adjacent levels require the same capability and workout semantics")
            if any(level.prescription_bounds is None or level.capability_bounds is None for level in (before, after)):
                raise ValueError("adjacent levels require explicit prescription and capability bounds")
            a, b = before.target_range, after.target_range
            larger = (self.sport == "cycling") == (self.direction == LevelStepDirection.PROGRESSION)
            correct = (b.minimum > a.minimum and b.maximum > a.maximum) if larger else (b.minimum < a.minimum and b.maximum < a.maximum)
            if not correct:
                raise ValueError("adjacent level target contradicts intensity direction")
        elif self.level_after is not None:
            raise ValueError("unsuccessful resolution cannot expose a candidate level")
        for level in (self.level_before, self.level_after):
            if level is not None and (level.capability_reference.athlete_id, level.capability_reference.cutoff_date,
                                      level.capability_reference.context_fingerprint, level.sport,
                                      level.session_type.value, level.target_kind, level.version) != (
                self.athlete_id, self.cutoff_date, self.context_fingerprint, self.sport,
                self.session_type, self.target_kind, self.version,
            ):
                raise ValueError("resolved level scope must agree")
        return self


class PrescriptionLadderResolution(FrozenModel):
    status: LevelResolutionStatus
    reason_codes: tuple[LevelResolutionReason, ...]
    ladder: PrescriptionIntensityLadder | None = None
    version: str = PRESCRIPTION_INTENSITY_LEVEL_VERSION

    @model_validator(mode="after")
    def coherent_catalog(self):
        if (self.ladder is not None) != (self.status == LevelResolutionStatus.LADDER_AVAILABLE):
            raise ValueError("only an available catalog can expose a ladder")
        if self.ladder is not None and self.ladder.version != self.version:
            raise ValueError("catalog and ladder versions must agree")
        return self


def capability_fingerprint(context: PlanningContext) -> str:
    return context_fingerprint({"athlete_id": context.request.athlete_id,
                                "cutoff_date": context.request.planning_date,
                                "performance": context.performance, "capability": context.adaptive_capability})


def _validate_context(context):
    if context.adaptive_capability and context.adaptive_capability.cutoff_date != context.request.planning_date:
        raise PrescriptionLevelContextMismatchError("capability cutoff does not match planning cutoff")
    if context.planning_adaptation is not None:
        raise PrescriptionLevelContextMismatchError("levels require the unadapted planning context")


def build_prescription_intensity_ladder(*, context: PlanningContext, sport: str,
                                       session_type: str, target_kind: str) -> PrescriptionLadderResolution:
    """No production provider exists; do not fabricate one from zone boundaries."""
    _validate_context(context)
    status = LevelResolutionStatus.NO_SUPPORTED_LADDER
    reason = LevelResolutionReason.NO_SAME_PRESCRIPTION_LEVELS
    expected = TARGET_SEMANTICS.get(sport)
    if sport == "strength":
        status, reason = LevelResolutionStatus.UNSUPPORTED, LevelResolutionReason.STRENGTH_UNSUPPORTED
    elif expected is None or target_kind != expected[0]:
        status, reason = LevelResolutionStatus.UNSUPPORTED, LevelResolutionReason.UNSUPPORTED_TARGET_KIND
    elif session_type not in SessionType._value2member_map_ or not session_type.startswith(expected[4]) or session_type == "SWIM_TECHNIQUE":
        reason = LevelResolutionReason.UNSUPPORTED_SESSION_TYPE
    else:
        value = getattr(context.performance, expected[2])
        if value is None or not Decimal(str(value)).is_finite() or value <= 0:
            status, reason = LevelResolutionStatus.GUARDED, LevelResolutionReason.INVALID_CAPABILITY_REFERENCE
    return PrescriptionLadderResolution(status=status, reason_codes=(reason,))


def _validate_ladder_scope(context, ladder):
    _validate_context(context)
    if ladder.athlete_id != context.request.athlete_id:
        raise PrescriptionLevelAthleteMismatchError("ladder athlete does not match planning athlete")
    if ladder.cutoff_date != context.request.planning_date or ladder.context_fingerprint != context.fingerprint:
        raise PrescriptionLevelContextMismatchError("ladder does not match planning context")
    if ladder.version != PRESCRIPTION_INTENSITY_LEVEL_VERSION:
        raise PrescriptionLevelContextMismatchError("unsupported prescription intensity policy")
    if ladder.levels[0].capability_reference.capability_fingerprint != capability_fingerprint(context):
        raise PrescriptionLevelContextMismatchError("ladder capability reference is stale")
    expected = TARGET_SEMANTICS[ladder.sport]
    if ladder.levels[0].capability_reference.value != getattr(context.performance, expected[2]):
        raise PrescriptionLevelContextMismatchError("ladder reference value does not match planning capability")


def identify_current_level(*, context: PlanningContext, ladder: PrescriptionIntensityLadder,
                           current_range: PrescriptionTargetRange) -> PrescriptionLevelResolution:
    _validate_ladder_scope(context, ladder)
    values = dict(athlete_id=ladder.athlete_id, cutoff_date=ladder.cutoff_date,
                  context_fingerprint=ladder.context_fingerprint, sport=ladder.sport,
                  session_type=ladder.session_type.value, target_kind=ladder.target_kind,
                  current_range=current_range, ladder_id=ladder.ladder_id)
    if current_range.unit != ladder.unit:
        return PrescriptionLevelResolution(**values, status=LevelResolutionStatus.GUARDED,
                                           reason_codes=(LevelResolutionReason.UNIT_MISMATCH,))
    current = next((level for level in ladder.levels if level.target_range == current_range), None)
    return PrescriptionLevelResolution(**values, level_before=current,
        status=LevelResolutionStatus.IDENTIFIED if current else LevelResolutionStatus.CURRENT_LEVEL_NOT_IDENTIFIED,
        reason_codes=(LevelResolutionReason.EXACT_CURRENT_LEVEL if current else LevelResolutionReason.EXACT_TARGET_MISMATCH,))


def resolve_adjacent_level(*, context: PlanningContext, ladder: PrescriptionIntensityLadder,
                           current_range: PrescriptionTargetRange,
                           direction: LevelStepDirection) -> PrescriptionLevelResolution:
    direction = LevelStepDirection(direction)
    identified = identify_current_level(context=context, ladder=ladder, current_range=current_range)
    if identified.status != LevelResolutionStatus.IDENTIFIED:
        return identified
    index = identified.level_before.index + (1 if direction == LevelStepDirection.PROGRESSION else -1)
    values = identified.model_dump(mode="python", exclude={"status", "reason_codes", "direction", "level_after"})
    if index < 0 or index >= len(ladder.levels):
        return PrescriptionLevelResolution(**values, direction=direction, status=LevelResolutionStatus.BOUNDARY,
            reason_codes=(LevelResolutionReason.MINIMUM_LEVEL if index < 0 else LevelResolutionReason.MAXIMUM_LEVEL,))
    adjacent = ladder.levels[index]
    if any(level.prescription_bounds is None or level.capability_bounds is None for level in (identified.level_before, adjacent)):
        return PrescriptionLevelResolution(**values, direction=direction, status=LevelResolutionStatus.GUARDED,
                                           reason_codes=(LevelResolutionReason.BOUNDS_UNAVAILABLE,))
    return PrescriptionLevelResolution(**values, direction=direction, status=LevelResolutionStatus.ADJACENT_LEVEL,
                                       reason_codes=(LevelResolutionReason.IMMEDIATE_NEIGHBOR,), level_after=adjacent)


def resolve_prescription_intensity_step(*, context: PlanningContext, sport: str, session_type: str,
                                        target_kind: str, current_range: PrescriptionTargetRange,
                                        direction: LevelStepDirection) -> PrescriptionLevelResolution:
    catalog = build_prescription_intensity_ladder(context=context, sport=sport, session_type=session_type, target_kind=target_kind)
    if catalog.ladder is not None:
        if (catalog.ladder.sport, catalog.ladder.session_type.value, catalog.ladder.target_kind) != (sport, session_type, target_kind):
            raise PrescriptionLevelContextMismatchError("catalog does not match requested prescription")
        return resolve_adjacent_level(context=context, ladder=catalog.ladder, current_range=current_range, direction=direction)
    expected = TARGET_SEMANTICS.get(sport)
    status, reasons = catalog.status, catalog.reason_codes
    if expected is not None and current_range.unit != expected[1]:
        status, reasons = LevelResolutionStatus.GUARDED, (LevelResolutionReason.UNIT_MISMATCH,)
    return PrescriptionLevelResolution(athlete_id=context.request.athlete_id, cutoff_date=context.request.planning_date,
        context_fingerprint=context.fingerprint, sport=sport, session_type=session_type, target_kind=target_kind,
        current_range=current_range, direction=direction, status=status, reason_codes=reasons)
