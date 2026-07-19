from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from sqlalchemy import CheckConstraint,ForeignKey,Numeric,Integer,String,Uuid,DateTime,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column,relationship
from app.db.base import Base,TimestampMixin,UTCDateTime,UUIDPrimaryKeyMixin
class AthletePerformanceProfileVersion(UUIDPrimaryKeyMixin,TimestampMixin,Base):
 __tablename__="athlete_performance_profile_versions"
 __table_args__=(UniqueConstraint("athlete_profile_id","effective_from",name="uq_performance_profile_athlete_effective"),CheckConstraint("resting_heart_rate_bpm IS NULL OR resting_heart_rate_bpm > 0",name="ck_profile_resting_hr_positive"),CheckConstraint("maximum_heart_rate_bpm IS NULL OR maximum_heart_rate_bpm > 0",name="ck_profile_max_hr_positive"),CheckConstraint("weight_kg IS NULL OR weight_kg > 0",name="ck_profile_weight_positive"),CheckConstraint("preferred_pool_length_metres IS NULL OR preferred_pool_length_metres IN (25,50)",name="ck_profile_pool_length"))
 athlete_profile_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),ForeignKey("athlete_profiles.id",ondelete="CASCADE"),nullable=False,index=True)
 effective_from:Mapped[datetime]=mapped_column(UTCDateTime(),nullable=False,index=True)
 data_origin:Mapped[str]=mapped_column(String(32),nullable=False)
 algorithm_version:Mapped[str]=mapped_column(String(32),nullable=False)
 source_note:Mapped[str|None]=mapped_column(String(500))
 resting_heart_rate_bpm:Mapped[int|None]=mapped_column(Integer); maximum_heart_rate_bpm:Mapped[int|None]=mapped_column(Integer); weight_kg:Mapped[Decimal|None]=mapped_column(Numeric(6,3))
 cycling_ftp_watts:Mapped[Decimal|None]=mapped_column(Numeric(7,2)); cycling_threshold_heart_rate_bpm:Mapped[int|None]=mapped_column(Integer)
 running_threshold_heart_rate_bpm:Mapped[int|None]=mapped_column(Integer); running_threshold_pace_seconds_per_km:Mapped[Decimal|None]=mapped_column(Numeric(8,2))
 swimming_css_seconds_per_100m:Mapped[Decimal|None]=mapped_column(Numeric(8,2)); preferred_pool_length_metres:Mapped[int|None]=mapped_column(Integer)