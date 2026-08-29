from __future__ import annotations

from datetime import date, datetime, time, timezone
from uuid import UUID
from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Integer, String, Text, Time, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates
from app.db.base import Base, JSON_DOCUMENT, TimestampMixin, UTCDateTime, UUIDPrimaryKeyMixin
from app.domains.planning.models import StructuredWorkoutDefinition

class CompetitionGoal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__="competition_goals"
    __table_args__=(
      CheckConstraint("priority IN ('A','B','C')",name="competition_goal_priority_valid"),
      CheckConstraint("status IN ('active','completed','cancelled')",name="competition_goal_status_valid"),
      CheckConstraint("event_category IN ('triathlon','running','cycling','swimming','duathlon','aquathlon')",name="competition_goal_category_valid"),
      CheckConstraint("target_finish_time_seconds IS NULL OR target_finish_time_seconds > 0",name="competition_goal_target_time_positive"),
      CheckConstraint("distance_m IS NULL OR distance_m >= 0",name="competition_goal_distance_nonnegative"),
      CheckConstraint("swim_distance_m IS NULL OR swim_distance_m >= 0",name="competition_goal_swim_nonnegative"),
      CheckConstraint("bike_distance_m IS NULL OR bike_distance_m >= 0",name="competition_goal_bike_nonnegative"),
      CheckConstraint("run_distance_m IS NULL OR run_distance_m >= 0",name="competition_goal_run_nonnegative"),
      Index("ix_competition_goals_athlete_date","athlete_profile_id","event_date"),
      Index("ix_competition_goals_creator","created_by_user_id"),
      Index("uq_competition_goals_athlete_source","athlete_profile_id","source_provider","source_external_id",unique=True),)
    athlete_profile_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),ForeignKey("athlete_profiles.id",ondelete="CASCADE"),nullable=False)
    name:Mapped[str]=mapped_column(String(200),nullable=False);event_date:Mapped[date]=mapped_column(Date,nullable=False);event_start_time:Mapped[time|None]=mapped_column(Time);timezone:Mapped[str]=mapped_column(String(64),nullable=False)
    event_category:Mapped[str]=mapped_column(String(24),nullable=False);event_format:Mapped[str]=mapped_column(String(32),nullable=False);priority:Mapped[str]=mapped_column(String(1),nullable=False)
    distance_m:Mapped[int|None]=mapped_column(Integer);swim_distance_m:Mapped[int|None]=mapped_column(Integer);bike_distance_m:Mapped[int|None]=mapped_column(Integer);run_distance_m:Mapped[int|None]=mapped_column(Integer)
    target_finish_time_seconds:Mapped[int|None]=mapped_column(Integer);notes:Mapped[str|None]=mapped_column(Text);status:Mapped[str]=mapped_column(String(16),nullable=False,default="active")
    created_by_user_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),ForeignKey("users.id",ondelete="RESTRICT"),nullable=False)
    city:Mapped[str|None]=mapped_column(String(120));region:Mapped[str|None]=mapped_column(String(120));country:Mapped[str|None]=mapped_column(String(120))
    source_provider:Mapped[str|None]=mapped_column(String(64));source_external_id:Mapped[str|None]=mapped_column(String(200));source_url:Mapped[str|None]=mapped_column(String(1000));source_retrieved_at:Mapped[datetime|None]=mapped_column(UTCDateTime());source_snapshot:Mapped[dict|None]=mapped_column(JSON_DOCUMENT)
    segments:Mapped[list[CompetitionGoalSegment]]=relationship(back_populates="goal",cascade="all, delete-orphan",order_by="CompetitionGoalSegment.position")

class CompetitionGoalSegment(UUIDPrimaryKeyMixin,Base):
    __tablename__="competition_goal_segments"
    __table_args__=(CheckConstraint("position >= 1",name="competition_goal_segment_position_positive"),CheckConstraint("sport IN ('swim','bike','run')",name="competition_goal_segment_sport_valid"),CheckConstraint("distance_m > 0",name="competition_goal_segment_distance_positive"),CheckConstraint("elevation_gain_m IS NULL OR elevation_gain_m >= 0",name="competition_goal_segment_elevation_nonnegative"),UniqueConstraint("competition_goal_id","position",name="uq_competition_goal_segment_position"),Index("ix_competition_goal_segments_goal","competition_goal_id"))
    competition_goal_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),ForeignKey("competition_goals.id",ondelete="CASCADE"),nullable=False);position:Mapped[int]=mapped_column(Integer,nullable=False);sport:Mapped[str]=mapped_column(String(16),nullable=False);distance_m:Mapped[int]=mapped_column(Integer,nullable=False);label:Mapped[str|None]=mapped_column(String(100));elevation_gain_m:Mapped[int|None]=mapped_column(Integer);goal:Mapped[CompetitionGoal]=relationship(back_populates="segments")

class TrainingPlan(UUIDPrimaryKeyMixin,TimestampMixin,Base):
    __tablename__="training_plans";__table_args__=(CheckConstraint("start_date <= end_date",name="training_plan_dates_valid"),CheckConstraint("status IN ('draft','active','completed','archived')",name="training_plan_status_valid"),CheckConstraint("origin IN ('human','ai')",name="training_plan_origin_valid"),CheckConstraint("created_via_role IS NULL OR created_via_role IN ('owner','athlete','coach')",name="training_plan_role_valid"),UniqueConstraint("source_preview_id",name="uq_training_plans_source_preview"),Index("ix_training_plans_athlete_dates","athlete_profile_id","start_date","end_date"),Index("ix_training_plans_creator","created_by_user_id"))
    athlete_profile_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),ForeignKey("athlete_profiles.id",ondelete="CASCADE"),nullable=False);title:Mapped[str]=mapped_column(String(200),nullable=False);start_date:Mapped[date]=mapped_column(Date,nullable=False);end_date:Mapped[date]=mapped_column(Date,nullable=False);status:Mapped[str]=mapped_column(String(16),nullable=False,default="draft");origin:Mapped[str]=mapped_column(String(16),nullable=False);created_by_user_id:Mapped[UUID|None]=mapped_column(Uuid(as_uuid=True),ForeignKey("users.id",ondelete="SET NULL"));created_via_role:Mapped[str|None]=mapped_column(String(16));algorithm_version:Mapped[str|None]=mapped_column(String(64));source_preview_id:Mapped[UUID|None]=mapped_column(Uuid(as_uuid=True),ForeignKey("training_plan_previews.id",ondelete="RESTRICT",name="fk_training_plans_source_preview_id_training_plan_previews"));source_preview:Mapped[TrainingPlanPreview|None]=relationship(back_populates="accepted_training_plan",foreign_keys=[source_preview_id])

class TrainingPlanGoal(Base):
    __tablename__="training_plan_goals";__table_args__=(CheckConstraint("relationship IN ('primary','supporting')",name="training_plan_goal_relationship_valid"),UniqueConstraint("training_plan_id","competition_goal_id",name="uq_training_plan_goal_pair"),)
    training_plan_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),ForeignKey("training_plans.id",ondelete="CASCADE"),primary_key=True);competition_goal_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),ForeignKey("competition_goals.id",ondelete="RESTRICT"),primary_key=True);relationship:Mapped[str]=mapped_column(String(16),nullable=False)

class PlannedTrainingSession(UUIDPrimaryKeyMixin,TimestampMixin,Base):
    __tablename__="planned_training_sessions";__table_args__=(CheckConstraint("status IN ('planned','completed','skipped','cancelled')",name="planned_session_status_valid"),CheckConstraint("origin IN ('human','ai')",name="planned_session_origin_valid"),CheckConstraint("created_via_role IS NULL OR created_via_role IN ('owner','athlete','coach')",name="planned_session_role_valid"),CheckConstraint("planned_duration_seconds IS NULL OR planned_duration_seconds >= 0",name="planned_session_duration_nonnegative"),CheckConstraint("planned_distance_meters IS NULL OR planned_distance_meters >= 0",name="planned_session_distance_nonnegative"),Index("ix_planned_sessions_athlete_date","athlete_profile_id","scheduled_date"),Index("ix_planned_sessions_plan","training_plan_id"),Index("ix_planned_sessions_creator","created_by_user_id"))
    athlete_profile_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),ForeignKey("athlete_profiles.id",ondelete="CASCADE"),nullable=False);training_plan_id:Mapped[UUID|None]=mapped_column(Uuid(as_uuid=True),ForeignKey("training_plans.id",ondelete="SET NULL"));scheduled_date:Mapped[date]=mapped_column(Date,nullable=False);scheduled_start_time:Mapped[time|None]=mapped_column(Time);timezone:Mapped[str]=mapped_column(String(64),nullable=False);sport:Mapped[str]=mapped_column(String(24),nullable=False);title:Mapped[str]=mapped_column(String(200),nullable=False);description:Mapped[str|None]=mapped_column(Text);planned_duration_seconds:Mapped[int|None]=mapped_column(Integer);planned_distance_meters:Mapped[int|None]=mapped_column(Integer);status:Mapped[str]=mapped_column(String(16),nullable=False,default="planned");origin:Mapped[str]=mapped_column(String(16),nullable=False);created_by_user_id:Mapped[UUID|None]=mapped_column(Uuid(as_uuid=True),ForeignKey("users.id",ondelete="SET NULL"));created_via_role:Mapped[str|None]=mapped_column(String(16));algorithm_version:Mapped[str|None]=mapped_column(String(64))

class PlannedSessionActivityLink(UUIDPrimaryKeyMixin,Base):
    __tablename__="planned_session_activity_links"
    __table_args__=(
      CheckConstraint("match_source IN ('automatic','manual')",name="planned_session_activity_link_source_valid"),
      CheckConstraint("match_confidence IN ('high','medium','low')",name="planned_session_activity_link_confidence_valid"),
      CheckConstraint("(match_source = 'automatic' AND algorithm_version IS NOT NULL) OR (match_source = 'manual' AND algorithm_version IS NULL)",name="planned_session_activity_link_algorithm_valid"),
      UniqueConstraint("planned_training_session_id","completed_activity_id",name="uq_planned_session_activity_link_pair"),
      Index("ix_planned_session_activity_links_athlete","athlete_profile_id"),
      Index("ix_planned_session_activity_links_session","planned_training_session_id"),
      Index("ix_planned_session_activity_links_activity","completed_activity_id"),)
    athlete_profile_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),ForeignKey("athlete_profiles.id",ondelete="CASCADE"),nullable=False)
    planned_training_session_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),ForeignKey("planned_training_sessions.id",ondelete="CASCADE"),nullable=False)
    completed_activity_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),ForeignKey("completed_activities.id",ondelete="CASCADE"),nullable=False)
    match_source:Mapped[str]=mapped_column(String(16),nullable=False)
    match_confidence:Mapped[str]=mapped_column(String(16),nullable=False)
    algorithm_version:Mapped[str|None]=mapped_column(String(32))
    created_at:Mapped[datetime]=mapped_column(UTCDateTime(),nullable=False,default=lambda:datetime.now(timezone.utc))

class StructuredWorkout(UUIDPrimaryKeyMixin,TimestampMixin,Base):
    __tablename__="structured_workouts";__table_args__=(CheckConstraint("schema_version = 1",name="structured_workout_schema_version_valid"),UniqueConstraint("planned_training_session_id",name="uq_structured_workout_session"),)
    planned_training_session_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),ForeignKey("planned_training_sessions.id",ondelete="CASCADE"),nullable=False);schema_version:Mapped[int]=mapped_column(Integer,nullable=False);definition:Mapped[dict]=mapped_column(JSON_DOCUMENT,nullable=False)
    @validates("definition")
    def validate_definition(self,key,value): return StructuredWorkoutDefinition.model_validate(value).model_dump(mode="json")
    def parsed_definition(self): return StructuredWorkoutDefinition.model_validate(self.definition)

class TrainingPlanPreview(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "training_plan_previews"
    __table_args__ = (
        CheckConstraint("status IN ('pending','accepted')", name="training_plan_preview_status_valid"),
        Index("ix_training_plan_previews_athlete_created", "athlete_profile_id", "created_at"),
        Index("ix_training_plan_previews_fingerprint", "artifact_fingerprint"),
    )
    athlete_profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("athlete_profiles.id", ondelete="CASCADE"), nullable=False)
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    accepted_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    artifact: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False)
    artifact_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_version: Mapped[str] = mapped_column(String(64), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    accepted_training_plan: Mapped[TrainingPlan | None] = relationship(back_populates="source_preview", foreign_keys=[TrainingPlan.source_preview_id], uselist=False)
