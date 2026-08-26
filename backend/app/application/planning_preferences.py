from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models import AthleteAvailabilitySlot, AthletePlanningPreferenceVersion, AthleteProfile
from app.domains.planning.contracts import AvailabilitySlot, PlanningPreferences


class PlanningPreferencesError(ValueError):
    pass


class PlanningPreferencesNotFoundError(PlanningPreferencesError):
    pass


class PlanningPreferencesApplication:
    def __init__(self, session):
        self.session = session

    def latest(self, athlete_id):
        return self.session.scalar(
            select(AthletePlanningPreferenceVersion)
            .where(AthletePlanningPreferenceVersion.athlete_profile_id == athlete_id)
            .options(selectinload(AthletePlanningPreferenceVersion.slots))
            .order_by(AthletePlanningPreferenceVersion.version_number.desc())
            .limit(1)
        )

    def require_latest(self, athlete_id):
        row = self.latest(athlete_id)
        if row is None:
            raise PlanningPreferencesNotFoundError("planning_preferences_not_found")
        return row

    def replace(self, athlete_id, user_id, preferences: PlanningPreferences):
        # PostgreSQL row locks serialize all preference writers for one athlete.
        # The semantic comparison must happen after acquiring that lock.
        if self.session.scalar(
            select(AthleteProfile.id)
            .where(AthleteProfile.id == athlete_id, AthleteProfile.deleted_at.is_(None))
            .with_for_update()
        ) is None:
            raise PlanningPreferencesNotFoundError("athlete_not_found")
        latest = self.session.scalar(
            select(AthletePlanningPreferenceVersion)
            .where(AthletePlanningPreferenceVersion.athlete_profile_id == athlete_id)
            .options(selectinload(AthletePlanningPreferenceVersion.slots))
            .order_by(AthletePlanningPreferenceVersion.version_number.desc())
            .limit(1)
        )
        if latest is not None and preferences_from_row(latest) == preferences:
            return latest
        latest_number = latest.version_number if latest is not None else 0
        row = AthletePlanningPreferenceVersion(
            athlete_profile_id=athlete_id,
            version_number=latest_number + 1,
            max_sessions_per_day=preferences.max_sessions_per_day,
            max_sessions_per_week=preferences.max_sessions_per_week,
            preferred_rest_days=list(preferences.preferred_rest_days),
            preferred_long_run_day=preferences.preferred_long_run_day,
            preferred_long_bike_day=preferences.preferred_long_bike_day,
            strength_sessions_per_week=preferences.strength_sessions_per_week,
            created_by_user_id=user_id,
            slots=[AthleteAvailabilitySlot(
                weekday=slot.weekday, position=1,
                available_minutes=slot.available_minutes, max_sessions=slot.max_sessions,
                earliest_time=slot.earliest_time, latest_time=slot.latest_time,
            ) for slot in preferences.availability_slots],
        )
        self.session.add(row)
        self.session.flush()
        return row


def preferences_from_row(row: AthletePlanningPreferenceVersion) -> PlanningPreferences:
    return PlanningPreferences(
        availability_slots=tuple(AvailabilitySlot(
            weekday=slot.weekday, available_minutes=slot.available_minutes,
            max_sessions=slot.max_sessions, earliest_time=slot.earliest_time,
            latest_time=slot.latest_time,
        ) for slot in sorted(row.slots, key=lambda item: (item.weekday, item.position))),
        max_sessions_per_day=row.max_sessions_per_day,
        max_sessions_per_week=row.max_sessions_per_week,
        preferred_rest_days=tuple(row.preferred_rest_days),
        preferred_long_run_day=row.preferred_long_run_day,
        preferred_long_bike_day=row.preferred_long_bike_day,
        strength_sessions_per_week=row.strength_sessions_per_week,
    )
