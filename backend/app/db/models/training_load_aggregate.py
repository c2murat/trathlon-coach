from datetime import date
from decimal import Decimal
from uuid import UUID
from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, JSON_DOCUMENT, TimestampMixin, UUIDPrimaryKeyMixin, UTCDateTime
class AthleteDailyTrainingLoad(UUIDPrimaryKeyMixin, TimestampMixin, Base):
 __tablename__='athlete_daily_training_loads'
 __table_args__=(UniqueConstraint('athlete_profile_id','local_date','timezone_name','source_load_algorithm_version','manual_strength_algorithm_version','aggregation_algorithm_version',name='uq_daily_load_configuration'),CheckConstraint('endurance_load >= 0',name='daily_endurance_load_nonnegative'),CheckConstraint('strength_load >= 0',name='daily_strength_load_nonnegative'),CheckConstraint('strength_session_count >= 0',name='daily_strength_count_nonnegative'),CheckConstraint('length(trim(manual_strength_algorithm_version)) > 0',name='daily_manual_version_not_empty'),Index('ix_daily_load_athlete_date','athlete_profile_id','local_date'))
 athlete_profile_id:Mapped[UUID]=mapped_column(ForeignKey('athlete_profiles.id',ondelete='CASCADE'),nullable=False);
 local_date:Mapped[date]=mapped_column(Date,nullable=False);
 timezone_name:Mapped[str]=mapped_column(String(64),nullable=False);
 source_load_algorithm_version:Mapped[str]=mapped_column(String(32),nullable=False);
 manual_strength_algorithm_version:Mapped[str]=mapped_column(String(32),nullable=False,default='0.7e.1');
 aggregation_algorithm_version:Mapped[str]=mapped_column(String(32),nullable=False);
 total_load:Mapped[Decimal]=mapped_column(Numeric(14,2),nullable=False);
 endurance_load:Mapped[Decimal]=mapped_column(Numeric(14,2),nullable=False,default=Decimal(0));
 strength_load:Mapped[Decimal]=mapped_column(Numeric(14,2),nullable=False,default=Decimal(0));
 strength_session_count:Mapped[int]=mapped_column(Integer,nullable=False,default=0);
 activity_count:Mapped[int]=mapped_column(Integer,nullable=False);
 loaded_activity_count:Mapped[int]=mapped_column(Integer,nullable=False);
 null_load_activity_count:Mapped[int]=mapped_column(Integer,nullable=False);
 total_duration_seconds:Mapped[Decimal]=mapped_column(Numeric(14,2),nullable=False);
 coverage:Mapped[str]=mapped_column(String(24),nullable=False);
 quality:Mapped[str]=mapped_column(String(24),nullable=False);
 warnings:Mapped[list]=mapped_column(JSON_DOCUMENT,nullable=False,default=list);
 activity_ids:Mapped[list]=mapped_column(JSON_DOCUMENT,nullable=False,default=list);
 calculated_at:Mapped[object]=mapped_column(UTCDateTime(),nullable=False)
class AthleteWeeklyTrainingLoad(UUIDPrimaryKeyMixin, TimestampMixin, Base):
 __tablename__='athlete_weekly_training_loads'
 __table_args__=(UniqueConstraint('athlete_profile_id','iso_year','iso_week','timezone_name','source_load_algorithm_version','manual_strength_algorithm_version','aggregation_algorithm_version',name='uq_weekly_load_configuration'),CheckConstraint('endurance_load >= 0',name='weekly_endurance_load_nonnegative'),CheckConstraint('strength_load >= 0',name='weekly_strength_load_nonnegative'),CheckConstraint('strength_session_count >= 0',name='weekly_strength_count_nonnegative'),CheckConstraint('length(trim(manual_strength_algorithm_version)) > 0',name='weekly_manual_version_not_empty'),Index('ix_weekly_load_athlete_date','athlete_profile_id','week_start_date'))
 athlete_profile_id:Mapped[UUID]=mapped_column(ForeignKey('athlete_profiles.id',ondelete='CASCADE'),nullable=False);
 iso_year:Mapped[int]=mapped_column(Integer,nullable=False);
 iso_week:Mapped[int]=mapped_column(Integer,nullable=False);
 week_start_date:Mapped[date]=mapped_column(Date,nullable=False);
 week_end_date:Mapped[date]=mapped_column(Date,nullable=False);
 timezone_name:Mapped[str]=mapped_column(String(64),nullable=False);
 source_load_algorithm_version:Mapped[str]=mapped_column(String(32),nullable=False);
 manual_strength_algorithm_version:Mapped[str]=mapped_column(String(32),nullable=False,default='0.7e.1');
 aggregation_algorithm_version:Mapped[str]=mapped_column(String(32),nullable=False);
 total_load:Mapped[Decimal]=mapped_column(Numeric(14,2),nullable=False);
 endurance_load:Mapped[Decimal]=mapped_column(Numeric(14,2),nullable=False,default=Decimal(0));
 strength_load:Mapped[Decimal]=mapped_column(Numeric(14,2),nullable=False,default=Decimal(0));
 strength_session_count:Mapped[int]=mapped_column(Integer,nullable=False,default=0);
 activity_count:Mapped[int]=mapped_column(Integer,nullable=False);
 loaded_activity_count:Mapped[int]=mapped_column(Integer,nullable=False);
 null_load_activity_count:Mapped[int]=mapped_column(Integer,nullable=False);
 total_duration_seconds:Mapped[Decimal]=mapped_column(Numeric(14,2),nullable=False);
 coverage:Mapped[str]=mapped_column(String(24),nullable=False);
 quality:Mapped[str]=mapped_column(String(24),nullable=False);
 warnings:Mapped[list]=mapped_column(JSON_DOCUMENT,nullable=False,default=list);
 activity_ids:Mapped[list]=mapped_column(JSON_DOCUMENT,nullable=False,default=list);
 calculated_at:Mapped[object]=mapped_column(UTCDateTime(),nullable=False)
