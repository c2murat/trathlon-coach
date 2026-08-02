from datetime import datetime, timezone
from sqlalchemy import select

from app.application.training_load_aggregation import AGGREGATION_ALGORITHM_VERSION, InvalidAggregationRangeError, TrainingLoadAggregationApplication as LegacyApplication
from app.db.models.manual_strength import ManualStrengthSession, ManualStrengthTrainingLoad
from app.db.models.training_load_aggregate import AthleteDailyTrainingLoad, AthleteWeeklyTrainingLoad
from app.domains.manual_strength import ALGORITHM_VERSION
from app.domains.training_load_aggregation import aggregate_daily_training_load, aggregate_weekly_training_load
from app.domains.training_load_aggregation.manual_strength import ManualStrengthLoadEntry, combine_daily_training_load, combine_weekly_training_load


class TrainingLoadAggregationApplication(LegacyApplication):
    def _manual_entries(self, athlete, start, end, tz, version):
        _, _, lower, upper = self._bounds(start, end, tz)
        rows = self.session.execute(
            select(ManualStrengthTrainingLoad, ManualStrengthSession)
            .join(ManualStrengthSession, ManualStrengthSession.id == ManualStrengthTrainingLoad.session_id)
            .where(ManualStrengthSession.athlete_id == athlete, ManualStrengthTrainingLoad.algorithm_version == version, ManualStrengthSession.started_at >= lower, ManualStrengthSession.started_at < upper)
            .order_by(ManualStrengthSession.started_at, ManualStrengthSession.id)
        ).all()
        return tuple(ManualStrengthLoadEntry(row.id, source.started_at, row.load_value, row.algorithm_version) for row, source in rows)

    def _combined_daily(self, athlete, start, end, tz, source_version, manual_version):
        endurance = aggregate_daily_training_load(self._entries(athlete, start, end, tz, source_version), timezone_name=tz, source_algorithm_version=source_version)
        return combine_daily_training_load(endurance, self._manual_entries(athlete, start, end, tz, manual_version), timezone_name=tz, source_algorithm_version=source_version, manual_strength_algorithm_version=manual_version)

    def recalculate_daily(self, athlete_profile_id, *, start_date, end_date, timezone_name, source_load_algorithm_version='0.7b.1', manual_strength_algorithm_version=ALGORITHM_VERSION):
        start, end, _, _ = self._bounds(start_date, end_date, timezone_name)
        results = self._combined_daily(athlete_profile_id, start, end, timezone_name, source_load_algorithm_version, manual_strength_algorithm_version)
        existing = self.session.scalars(select(AthleteDailyTrainingLoad).where(AthleteDailyTrainingLoad.athlete_profile_id == athlete_profile_id, AthleteDailyTrainingLoad.local_date.between(start, end), AthleteDailyTrainingLoad.timezone_name == timezone_name, AthleteDailyTrainingLoad.source_load_algorithm_version == source_load_algorithm_version, AthleteDailyTrainingLoad.manual_strength_algorithm_version == manual_strength_algorithm_version, AthleteDailyTrainingLoad.aggregation_algorithm_version == AGGREGATION_ALGORITHM_VERSION)).all()
        keys = {item.local_date for item in results}
        for row in existing:
            if row.local_date not in keys: self.session.delete(row)
        now = self.clock()
        for item in results:
            row = self.session.scalar(select(AthleteDailyTrainingLoad).where(AthleteDailyTrainingLoad.athlete_profile_id == athlete_profile_id, AthleteDailyTrainingLoad.local_date == item.local_date, AthleteDailyTrainingLoad.timezone_name == timezone_name, AthleteDailyTrainingLoad.source_load_algorithm_version == source_load_algorithm_version, AthleteDailyTrainingLoad.manual_strength_algorithm_version == manual_strength_algorithm_version, AthleteDailyTrainingLoad.aggregation_algorithm_version == AGGREGATION_ALGORITHM_VERSION))
            values = dict(total_load=item.total_load, endurance_load=item.endurance_load, strength_load=item.strength_load, strength_session_count=item.strength_session_count, activity_count=item.activity_count, loaded_activity_count=item.loaded_activity_count, null_load_activity_count=item.null_load_activity_count, total_duration_seconds=item.total_duration_seconds, coverage=item.coverage.value, quality=item.quality.value, warnings=list(item.warnings), activity_ids=list(item.activity_ids), calculated_at=now)
            if row:
                for key, value in values.items(): setattr(row, key, value)
            else: self.session.add(AthleteDailyTrainingLoad(athlete_profile_id=athlete_profile_id, local_date=item.local_date, timezone_name=timezone_name, source_load_algorithm_version=source_load_algorithm_version, manual_strength_algorithm_version=manual_strength_algorithm_version, aggregation_algorithm_version=AGGREGATION_ALGORITHM_VERSION, **values))
        self.session.flush(); return results

    def recalculate_weekly(self, athlete_profile_id, *, start_date, end_date, timezone_name, source_load_algorithm_version='0.7b.1', manual_strength_algorithm_version=ALGORITHM_VERSION):
        start, end, _, _ = self._bounds(start_date, end_date, timezone_name, True)
        endurance = aggregate_weekly_training_load(self._entries(athlete_profile_id, start, end, timezone_name, source_load_algorithm_version), timezone_name=timezone_name, source_algorithm_version=source_load_algorithm_version)
        daily = self._combined_daily(athlete_profile_id, start, end, timezone_name, source_load_algorithm_version, manual_strength_algorithm_version)
        results = combine_weekly_training_load(endurance, daily, timezone_name=timezone_name, source_algorithm_version=source_load_algorithm_version, manual_strength_algorithm_version=manual_strength_algorithm_version)
        existing = self.session.scalars(select(AthleteWeeklyTrainingLoad).where(AthleteWeeklyTrainingLoad.athlete_profile_id == athlete_profile_id, AthleteWeeklyTrainingLoad.week_start_date.between(start, end), AthleteWeeklyTrainingLoad.timezone_name == timezone_name, AthleteWeeklyTrainingLoad.source_load_algorithm_version == source_load_algorithm_version, AthleteWeeklyTrainingLoad.manual_strength_algorithm_version == manual_strength_algorithm_version, AthleteWeeklyTrainingLoad.aggregation_algorithm_version == AGGREGATION_ALGORITHM_VERSION)).all()
        keys = {(item.iso_year, item.iso_week) for item in results}
        for row in existing:
            if (row.iso_year, row.iso_week) not in keys: self.session.delete(row)
        now = self.clock()
        for item in results:
            row = self.session.scalar(select(AthleteWeeklyTrainingLoad).where(AthleteWeeklyTrainingLoad.athlete_profile_id == athlete_profile_id, AthleteWeeklyTrainingLoad.iso_year == item.iso_year, AthleteWeeklyTrainingLoad.iso_week == item.iso_week, AthleteWeeklyTrainingLoad.timezone_name == timezone_name, AthleteWeeklyTrainingLoad.source_load_algorithm_version == source_load_algorithm_version, AthleteWeeklyTrainingLoad.manual_strength_algorithm_version == manual_strength_algorithm_version, AthleteWeeklyTrainingLoad.aggregation_algorithm_version == AGGREGATION_ALGORITHM_VERSION))
            values = dict(week_end_date=item.week_end_date, total_load=item.total_load, endurance_load=item.endurance_load, strength_load=item.strength_load, strength_session_count=item.strength_session_count, activity_count=item.activity_count, loaded_activity_count=item.loaded_activity_count, null_load_activity_count=item.null_load_activity_count, total_duration_seconds=item.total_duration_seconds, coverage=item.coverage.value, quality=item.quality.value, warnings=list(item.warnings), activity_ids=list(item.activity_ids), calculated_at=now)
            if row:
                for key, value in values.items(): setattr(row, key, value)
            else: self.session.add(AthleteWeeklyTrainingLoad(athlete_profile_id=athlete_profile_id, iso_year=item.iso_year, iso_week=item.iso_week, week_start_date=item.week_start_date, timezone_name=timezone_name, source_load_algorithm_version=source_load_algorithm_version, manual_strength_algorithm_version=manual_strength_algorithm_version, aggregation_algorithm_version=AGGREGATION_ALGORITHM_VERSION, **values))
        self.session.flush(); return results

    def get_daily_aggregates(self, athlete_profile_id, *, start_date, end_date, timezone_name, source_load_algorithm_version='0.7b.1', manual_strength_algorithm_version=ALGORITHM_VERSION):
        return tuple(self.session.scalars(select(AthleteDailyTrainingLoad).where(AthleteDailyTrainingLoad.athlete_profile_id == athlete_profile_id, AthleteDailyTrainingLoad.local_date.between(start_date, end_date), AthleteDailyTrainingLoad.timezone_name == timezone_name, AthleteDailyTrainingLoad.source_load_algorithm_version == source_load_algorithm_version, AthleteDailyTrainingLoad.manual_strength_algorithm_version == manual_strength_algorithm_version, AthleteDailyTrainingLoad.aggregation_algorithm_version == AGGREGATION_ALGORITHM_VERSION).order_by(AthleteDailyTrainingLoad.local_date)).all())

    def get_weekly_aggregates(self, athlete_profile_id, *, start_date, end_date, timezone_name, source_load_algorithm_version='0.7b.1', manual_strength_algorithm_version=ALGORITHM_VERSION):
        return tuple(self.session.scalars(select(AthleteWeeklyTrainingLoad).where(AthleteWeeklyTrainingLoad.athlete_profile_id == athlete_profile_id, AthleteWeeklyTrainingLoad.week_start_date.between(start_date, end_date), AthleteWeeklyTrainingLoad.timezone_name == timezone_name, AthleteWeeklyTrainingLoad.source_load_algorithm_version == source_load_algorithm_version, AthleteWeeklyTrainingLoad.manual_strength_algorithm_version == manual_strength_algorithm_version, AthleteWeeklyTrainingLoad.aggregation_algorithm_version == AGGREGATION_ALGORITHM_VERSION).order_by(AthleteWeeklyTrainingLoad.week_start_date)).all())
