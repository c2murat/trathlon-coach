from __future__ import annotations
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID
from sqlalchemy import Float,ForeignKey,Integer,String,Text,UniqueConstraint,Uuid
from sqlalchemy.orm import Mapped,mapped_column,relationship
from app.db.base import Base,JSON_DOCUMENT,TimestampMixin,UTCDateTime,UUIDPrimaryKeyMixin
if TYPE_CHECKING:
 from app.db.models.activity import CompletedActivity
class ActivityLap(UUIDPrimaryKeyMixin,TimestampMixin,Base):
 __tablename__="activity_laps";__table_args__=(UniqueConstraint("completed_activity_id","provider_index",name="uq_activity_lap_activity_provider_index"),)
 completed_activity_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),ForeignKey("completed_activities.id",ondelete="CASCADE"),nullable=False,index=True)
 provider_lap_id:Mapped[str|None]=mapped_column(String(255));provider_index:Mapped[int]=mapped_column(Integer,nullable=False);lap_index:Mapped[int]=mapped_column(Integer,nullable=False);name:Mapped[str|None]=mapped_column(String(300));start_date:Mapped[datetime|None]=mapped_column(UTCDateTime());elapsed_time_seconds:Mapped[int|None]=mapped_column(Integer);moving_time_seconds:Mapped[int|None]=mapped_column(Integer);distance_metres:Mapped[float|None]=mapped_column(Float);elevation_metres:Mapped[float|None]=mapped_column(Float);average_speed_metres_per_second:Mapped[float|None]=mapped_column(Float);maximum_speed_metres_per_second:Mapped[float|None]=mapped_column(Float);average_heart_rate:Mapped[float|None]=mapped_column(Float);maximum_heart_rate:Mapped[float|None]=mapped_column(Float);average_cadence:Mapped[float|None]=mapped_column(Float);average_watts:Mapped[float|None]=mapped_column(Float);lap_type:Mapped[str|None]=mapped_column(String(64));pace_zone:Mapped[int|None]=mapped_column(Integer)
 completed_activity:Mapped[CompletedActivity]=relationship(back_populates="laps")
class ActivityStream(UUIDPrimaryKeyMixin,TimestampMixin,Base):
 __tablename__="activity_streams";__table_args__=(UniqueConstraint("completed_activity_id","stream_type",name="uq_activity_stream_activity_type"),)
 completed_activity_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),ForeignKey("completed_activities.id",ondelete="CASCADE"),nullable=False,index=True);stream_type:Mapped[str]=mapped_column(String(32),nullable=False);original_resolution:Mapped[str|None]=mapped_column(String(32));original_series_type:Mapped[str|None]=mapped_column(String(32));original_sample_count:Mapped[int]=mapped_column(Integer,nullable=False);sample_count:Mapped[int]=mapped_column(Integer,nullable=False);values:Mapped[list[object]]=mapped_column(JSON_DOCUMENT,nullable=False);fetched_at:Mapped[datetime]=mapped_column(UTCDateTime(),nullable=False,index=True);source_updated_at:Mapped[datetime|None]=mapped_column(UTCDateTime());retention_class:Mapped[str]=mapped_column(String(32),nullable=False);checksum:Mapped[str]=mapped_column(String(64),nullable=False);version:Mapped[int]=mapped_column(Integer,nullable=False,default=1)
 completed_activity:Mapped[CompletedActivity]=relationship(back_populates="streams")
class ActivityRouteEvidence(UUIDPrimaryKeyMixin,TimestampMixin,Base):
 __tablename__="activity_route_evidence";__table_args__=(UniqueConstraint("completed_activity_id",name="uq_activity_route_activity"),)
 completed_activity_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),ForeignKey("completed_activities.id",ondelete="CASCADE"),nullable=False,index=True);available:Mapped[bool]=mapped_column(nullable=False,default=False);summary_polyline:Mapped[str|None]=mapped_column(Text);sample_count:Mapped[int]=mapped_column(Integer,nullable=False,default=0);fetched_at:Mapped[datetime]=mapped_column(UTCDateTime(),nullable=False);source_updated_at:Mapped[datetime|None]=mapped_column(UTCDateTime());retention_class:Mapped[str]=mapped_column(String(32),nullable=False,default="location");checksum:Mapped[str|None]=mapped_column(String(64));version:Mapped[int]=mapped_column(Integer,nullable=False,default=1)
 completed_activity:Mapped[CompletedActivity]=relationship(back_populates="route_evidence")

class ActivityEvidenceState(UUIDPrimaryKeyMixin,TimestampMixin,Base):
 __tablename__="activity_evidence_states";__table_args__=(UniqueConstraint("completed_activity_id",name="uq_activity_evidence_state_activity"),)
 completed_activity_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),ForeignKey("completed_activities.id",ondelete="CASCADE"),nullable=False,index=True);laps_fetched_at:Mapped[datetime|None]=mapped_column(UTCDateTime());streams_fetched_at:Mapped[datetime|None]=mapped_column(UTCDateTime());source_updated_at:Mapped[datetime|None]=mapped_column(UTCDateTime());status:Mapped[str|None]=mapped_column(String(32));error_category:Mapped[str|None]=mapped_column(String(100));location_retained:Mapped[bool]=mapped_column(nullable=False,default=False)
 completed_activity:Mapped[CompletedActivity]=relationship(back_populates="evidence_state")