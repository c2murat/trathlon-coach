from uuid import UUID
from sqlalchemy import CheckConstraint, ForeignKey, String, Uuid, Float, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, JSON_DOCUMENT, TimestampMixin, UTCDateTime, UUIDPrimaryKeyMixin
class ActivityTrainingLoad(UUIDPrimaryKeyMixin,TimestampMixin,Base):
 __tablename__="activity_training_loads"
 __table_args__=(CheckConstraint("load_value IS NULL OR load_value >= 0",name="ck_training_load_nonnegative"),__import__('sqlalchemy').UniqueConstraint("completed_activity_id","algorithm_version",name="uq_training_load_activity_algorithm"),Index("ix_training_load_activity","completed_activity_id"),Index("ix_training_load_algorithm","algorithm_version"))
 completed_activity_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),ForeignKey("completed_activities.id",ondelete="CASCADE"),nullable=False)
 load_value:Mapped[float|None]=mapped_column(Float)
 method:Mapped[str]=mapped_column(String(32),nullable=False); unit:Mapped[str]=mapped_column(String(32),nullable=False); coverage:Mapped[str]=mapped_column(String(24),nullable=False); quality:Mapped[str|None]=mapped_column(String(24)); reason:Mapped[str|None]=mapped_column(String(32)); algorithm_version:Mapped[str]=mapped_column(String(32),nullable=False); duration_seconds:Mapped[float|None]=mapped_column(Float); effective_intensity:Mapped[float|None]=mapped_column(Float); reference_value:Mapped[float|None]=mapped_column(Float); reference_metric:Mapped[str|None]=mapped_column(String(32)); source_metrics:Mapped[dict]=mapped_column(JSON_DOCUMENT,nullable=False,default=dict); warnings:Mapped[list]=mapped_column(JSON_DOCUMENT,nullable=False,default=list); calculated_at:Mapped[object]=mapped_column(UTCDateTime(),nullable=False)
