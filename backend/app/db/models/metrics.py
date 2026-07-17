from __future__ import annotations
from uuid import UUID
from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, JSON_DOCUMENT, TimestampMixin, UTCDateTime, UUIDPrimaryKeyMixin
from typing import TYPE_CHECKING
if TYPE_CHECKING:
 from app.db.models.activity import CompletedActivity
class ActivityMetric(UUIDPrimaryKeyMixin, TimestampMixin, Base):
 __tablename__="activity_metrics"
 __table_args__=(UniqueConstraint("completed_activity_id","metric_key","algorithm_version",name="uq_activity_metric_activity_key_version"),)
 completed_activity_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),ForeignKey("completed_activities.id",ondelete="CASCADE"),nullable=False,index=True)
 metric_key:Mapped[str]=mapped_column(String(64),nullable=False)
 algorithm_version:Mapped[str]=mapped_column(String(32),nullable=False)
 status:Mapped[str]=mapped_column(String(24),nullable=False)
 value:Mapped[float|None]=mapped_column(Float)
 unit:Mapped[str|None]=mapped_column(String(24))
 source:Mapped[str|None]=mapped_column(String(64))
 sample_count:Mapped[int|None]=mapped_column(Integer)
 coverage_ratio:Mapped[float|None]=mapped_column(Float)
 quality_notes:Mapped[list[str]]=mapped_column(JSON_DOCUMENT,nullable=False,default=list)
 unavailable_reason:Mapped[str|None]=mapped_column(String(64))
 calculated_at:Mapped[object]=mapped_column(UTCDateTime(),nullable=False)
 completed_activity:Mapped["CompletedActivity"]=relationship()