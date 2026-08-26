from __future__ import annotations

from datetime import date, timedelta
from enum import Enum
from math import ceil
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.domains.planning.contracts import FrozenModel, PlanningContext, PlanningGoal, PlanningWarning


SEASON_STRUCTURE_SCHEMA_VERSION = 1


class SeasonPhase(str, Enum):
    PREPARATION = "PREPARATION"
    BASE = "BASE"
    BUILD = "BUILD"
    SPECIFIC = "SPECIFIC"
    MAINTENANCE = "MAINTENANCE"
    TAPER = "TAPER"
    COMPETITION = "COMPETITION"
    RECOVERY = "RECOVERY"


class SeasonStructureConfig(FrozenModel):
    version: str = Field(min_length=1)
    algorithm_version: str = Field(min_length=1)
    close_primary_goal_days: int = Field(default=21, ge=1)
    short_horizon_days: int = Field(default=21, ge=1)
    taper_days_a: int = Field(default=14, ge=0)
    taper_days_b: int = Field(default=7, ge=0)
    taper_days_c: int = Field(default=0, ge=0)
    recovery_days_a: int = Field(default=7, ge=0)
    recovery_days_b: int = Field(default=3, ge=0)
    recovery_days_c: int = Field(default=1, ge=0)
    low_weekly_minutes: int = Field(default=180, ge=0)
    multisport_min_available_days: int = Field(default=2, ge=1, le=7)

    def taper_days(self, priority: str) -> int:
        return {"A": self.taper_days_a, "B": self.taper_days_b, "C": self.taper_days_c}[priority]

    def recovery_days(self, priority: str) -> int:
        return {"A": self.recovery_days_a, "B": self.recovery_days_b, "C": self.recovery_days_c}[priority]


class SeasonGoal(FrozenModel):
    goal_id: UUID
    date: date
    priority: Literal["A", "B", "C"]
    role: Literal["primary", "supporting", "training"]
    disciplines: tuple[Literal["running", "cycling", "swimming"], ...]


class CompetitionMarker(FrozenModel):
    goal_id: UUID
    date: date
    priority: Literal["A", "B", "C"]
    role: Literal["primary", "supporting", "training"]
    taper_days: int = Field(ge=0)
    recovery_days: int = Field(ge=0)
    conflict_codes: tuple[str, ...] = ()


class SeasonBlock(FrozenModel):
    start_date: date
    end_date: date
    phase: SeasonPhase
    target_goal_ids: tuple[UUID, ...]
    disciplines: tuple[Literal["running", "cycling", "swimming"], ...]
    priority: Literal["A", "B", "C"] | None
    rationale_code: str
    week_count: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("season block dates are invalid")
        return self


class SeasonStructure(FrozenModel):
    schema_version: int = SEASON_STRUCTURE_SCHEMA_VERSION
    planning_start_date: date
    planning_end_date: date
    goals: tuple[SeasonGoal, ...]
    blocks: tuple[SeasonBlock, ...]
    competition_markers: tuple[CompetitionMarker, ...]
    warnings: tuple[PlanningWarning, ...]
    algorithm_version: str
    configuration_version: str


class SeasonStructureError(ValueError):
    pass


class SeasonStructureBuilder:
    def __init__(self, config: SeasonStructureConfig):
        self.config = config

    def build(self, context: PlanningContext) -> SeasonStructure:
        start = context.request.start_date
        if any(goal.event_date < start for goal in context.goals):
            raise SeasonStructureError("requested goal is before planning start")
        last_goal = max(goal.event_date for goal in context.goals)
        end = context.request.horizon_end_date or last_goal
        if end < last_goal:
            raise SeasonStructureError("planning horizon excludes a requested goal")
        goals = tuple(self._season_goal(goal) for goal in context.goals)
        warnings, conflicts = self._warnings(context, goals, start)
        markers = tuple(CompetitionMarker(
            goal_id=goal.goal_id, date=goal.date, priority=goal.priority, role=goal.role,
            taper_days=self.config.taper_days(goal.priority),
            recovery_days=self.config.recovery_days(goal.priority),
            conflict_codes=tuple(sorted(conflicts.get(goal.goal_id, set()))),
        ) for goal in goals)
        blocks = self._blocks(start, end, goals, markers)
        return SeasonStructure(
            planning_start_date=start, planning_end_date=end, goals=goals, blocks=blocks,
            competition_markers=markers,
            warnings=tuple(sorted(warnings, key=lambda item: (item.severity, item.code, str(item.context)))),
            algorithm_version=self.config.algorithm_version,
            configuration_version=self.config.version,
        )

    @staticmethod
    def _disciplines(goal: PlanningGoal):
        mapped = {"run": "running", "bike": "cycling", "swim": "swimming"}
        disciplines = {mapped[item.sport] for item in goal.segments}
        if not disciplines:
            disciplines = {
                "running": {"running"}, "cycling": {"cycling"},
                "swimming": {"swimming"},
                "triathlon": {"running", "cycling", "swimming"},
                "duathlon": {"running", "cycling"},
                "aquathlon": {"running", "swimming"},
            }.get(goal.category, set())
        return tuple(sorted(disciplines))

    def _season_goal(self, goal: PlanningGoal) -> SeasonGoal:
        role = {"A": "primary", "B": "supporting", "C": "training"}[goal.priority]
        return SeasonGoal(goal_id=goal.competition_goal_id, date=goal.event_date,
                          priority=goal.priority, role=role, disciplines=self._disciplines(goal))

    def _warnings(self, context, goals, start):
        warnings = []
        conflicts = {goal.goal_id: set() for goal in goals}
        primary = [goal for goal in goals if goal.priority == "A"]
        for left, right in zip(primary, primary[1:]):
            if (right.date - left.date).days < self.config.close_primary_goal_days:
                warnings.append(PlanningWarning(code="MULTIPLE_PRIMARY_GOALS_CLOSE", context={"first_goal_id": str(left.goal_id), "second_goal_id": str(right.goal_id)}))
                conflicts[left.goal_id].add("MULTIPLE_PRIMARY_GOALS_CLOSE")
                conflicts[right.goal_id].add("MULTIPLE_PRIMARY_GOALS_CLOSE")
        dates = {}
        for goal in goals:
            dates.setdefault(goal.date, []).append(goal)
        for same_date in dates.values():
            if len(same_date) > 1:
                warnings.append(PlanningWarning(code="GOALS_OVERLAP", context={"date": same_date[0].date.isoformat()}))
                for goal in same_date:
                    conflicts[goal.goal_id].add("GOALS_OVERLAP")
        for goal in goals:
            if (goal.date - start).days < self.config.short_horizon_days:
                warnings.append(PlanningWarning(code="SHORT_PREPARATION_HORIZON", context={"goal_id": str(goal.goal_id), "days": (goal.date - start).days}))
            for target in primary:
                if goal.goal_id != target.goal_id and target.date - timedelta(days=self.config.taper_days_a) <= goal.date < target.date:
                    warnings.append(PlanningWarning(code="GOAL_DURING_TAPER", context={"goal_id": str(goal.goal_id), "primary_goal_id": str(target.goal_id)}))
                    conflicts[goal.goal_id].add("GOAL_DURING_TAPER")
                    conflicts[target.goal_id].add("GOAL_DURING_TAPER")
        available = tuple(slot for slot in context.preferences.availability_slots if slot.available_minutes > 0 and slot.max_sessions > 0)
        minutes = sum(slot.available_minutes for slot in available)
        if not available or context.preferences.max_sessions_per_week == 0:
            warnings.append(PlanningWarning(code="NO_TRAINING_AVAILABILITY", severity="ERROR", blocking=True))
        elif minutes < self.config.low_weekly_minutes:
            warnings.append(PlanningWarning(code="LOW_WEEKLY_AVAILABILITY", context={"available_minutes": minutes}))
        if any(len(goal.disciplines) > 1 for goal in goals) and len({slot.weekday for slot in available}) < self.config.multisport_min_available_days:
            warnings.append(PlanningWarning(code="MULTISPORT_AVAILABILITY_CONSTRAINT", context={"available_days": len({slot.weekday for slot in available})}))
        return warnings, conflicts

    def _blocks(self, start, end, goals, markers):
        descriptors = []
        day = start
        while day <= end:
            descriptors.append((day, *self._descriptor(day, goals, markers)))
            day += timedelta(days=1)
        groups = []
        group_start, phase, ids, disciplines, priority, rationale = descriptors[0]
        previous_day = group_start
        previous_key = (phase, ids, disciplines, priority, rationale)
        for current in descriptors[1:]:
            current_day, *key_parts = current
            key = tuple(key_parts)
            if key != previous_key:
                groups.append((group_start, previous_day, *previous_key))
                group_start = current_day
                previous_key = key
            previous_day = current_day
        groups.append((group_start, previous_day, *previous_key))
        return tuple(SeasonBlock(
            start_date=left, end_date=right, phase=phase, target_goal_ids=ids,
            disciplines=disciplines, priority=priority, rationale_code=rationale,
            week_count=ceil(((right - left).days + 1) / 7),
        ) for left, right, phase, ids, disciplines, priority, rationale in groups)

    def _descriptor(self, day, goals, markers):
        same = tuple(goal for goal in goals if goal.date == day)
        if same:
            return SeasonPhase.COMPETITION, tuple(goal.goal_id for goal in same), self._union_disciplines(same), self._highest_priority(same), "COMPETITION_DAY"
        recovering = tuple(goal for goal, marker in zip(goals, markers) if marker.date < day <= marker.date + timedelta(days=marker.recovery_days))
        if recovering:
            return SeasonPhase.RECOVERY, tuple(goal.goal_id for goal in recovering), self._union_disciplines(recovering), self._highest_priority(recovering), "POST_COMPETITION_RECOVERY"
        tapering = tuple(goal for goal, marker in zip(goals, markers) if marker.taper_days and marker.date - timedelta(days=marker.taper_days) <= day < marker.date)
        if tapering:
            return SeasonPhase.TAPER, tuple(goal.goal_id for goal in tapering), self._union_disciplines(tapering), self._highest_priority(tapering), "PRE_COMPETITION_TAPER"
        upcoming = next((goal for goal in goals if goal.date > day), goals[-1])
        remaining = (upcoming.date - day).days
        if remaining < self.config.short_horizon_days:
            phase, rationale = SeasonPhase.MAINTENANCE, "SHORT_HORIZON_MAINTENANCE"
        elif remaining <= 28:
            phase, rationale = SeasonPhase.SPECIFIC, "GOAL_SPECIFIC_PREPARATION"
        elif remaining <= 56:
            phase, rationale = SeasonPhase.BUILD, "GENERAL_BUILD"
        else:
            phase, rationale = SeasonPhase.BASE, "GENERAL_BASE"
        return phase, (upcoming.goal_id,), upcoming.disciplines, upcoming.priority, rationale

    @staticmethod
    def _union_disciplines(goals):
        return tuple(sorted({discipline for goal in goals for discipline in goal.disciplines}))

    @staticmethod
    def _highest_priority(goals):
        return min((goal.priority for goal in goals), key=lambda item: {"A": 0, "B": 1, "C": 2}[item])
