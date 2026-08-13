from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.athlete import AthleteProfile
    from app.db.models.user import User


class UserAthleteMembership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_athlete_memberships"
    __table_args__ = (
        CheckConstraint("role IN ('owner', 'athlete', 'coach', 'editor', 'viewer')", name="role_valid"),
        UniqueConstraint("user_id", "athlete_profile_id", name="uq_user_athlete_memberships_user_athlete"),
        Index("uq_user_athlete_memberships_active_default_user", "user_id", unique=True, postgresql_where=text("is_active IS TRUE AND is_default IS TRUE"), sqlite_where=text("is_active IS 1 AND is_default IS 1")),
    )

    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    athlete_profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("athlete_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user: Mapped[User] = relationship(back_populates="athlete_memberships")
    athlete_profile: Mapped[AthleteProfile] = relationship(back_populates="user_memberships")
