from uuid import UUID
from decimal import Decimal
from sqlalchemy import ForeignKey,Numeric,String,Uuid,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from app.db.base import Base,TimestampMixin,UTCDateTime,UUIDPrimaryKeyMixin
class AthletePerformanceReference(UUIDPrimaryKeyMixin,TimestampMixin,Base):
 __tablename__="athlete_performance_references"
 __table_args__=(UniqueConstraint("athlete_profile_id","sport","metric_type","effective_from",name="uq_performance_reference_effective"),)
 athlete_profile_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),ForeignKey("athlete_profiles.id",ondelete="CASCADE"),nullable=False,index=True)
 sport:Mapped[str]=mapped_column(String(32),nullable=False,index=True);metric_type:Mapped[str]=mapped_column(String(32),nullable=False,index=True);value:Mapped[Decimal]=mapped_column(Numeric(10,3),nullable=False);unit:Mapped[str]=mapped_column(String(24),nullable=False);data_origin:Mapped[str]=mapped_column(String(16),nullable=False);quality_level:Mapped[str]=mapped_column(String(16),nullable=False);effective_from:Mapped[object]=mapped_column(UTCDateTime(),nullable=False,index=True);measured_at:Mapped[object|None]=mapped_column(UTCDateTime());calculation_method:Mapped[str|None]=mapped_column(String(64));algorithm_version:Mapped[str|None]=mapped_column(String(32));source_note:Mapped[str|None]=mapped_column(String(500))