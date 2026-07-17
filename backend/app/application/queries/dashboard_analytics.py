from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utc_now
from app.db.models import AthleteProfile, CompletedActivity

SPORTS = ("running", "cycling", "swimming", "other")


def normalize_sport(value: str) -> str:
    return value if value in {"running", "cycling", "swimming"} else "other"


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def local_midnight(day: date, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, time.min, tzinfo=tz)


@dataclass(frozen=True)
class AnalyticsContext:
    timezone: ZoneInfo
    now: datetime
    activities: tuple[CompletedActivity, ...]


class DashboardAnalyticsQuery:
    def __init__(self, session: Session, now: datetime | None = None) -> None:
        self.session = session
        self.now = now or utc_now()

    def context(self, user_id: UUID) -> AnalyticsContext:
        athlete = self.session.scalar(select(AthleteProfile).where(AthleteProfile.user_id == user_id, AthleteProfile.deleted_at.is_(None)))
        tz = ZoneInfo(athlete.timezone if athlete else "UTC")
        rows = () if athlete is None else tuple(self.session.scalars(select(CompletedActivity).where(CompletedActivity.athlete_id == athlete.id, CompletedActivity.deleted_at.is_(None), CompletedActivity.provider_deleted_at.is_(None), CompletedActivity.start_at <= self.now).order_by(CompletedActivity.start_at)).all())
        return AnalyticsContext(tz, self.now, rows)

    def summary(self, user_id: UUID, period: str) -> dict:
        c = self.context(user_id); today = c.now.astimezone(c.timezone).date()
        if period == "week": start_day, end_day = week_start(today), week_start(today) + timedelta(days=7)
        elif period == "month": start_day = today.replace(day=1); end_day = (start_day.replace(day=28) + timedelta(days=4)).replace(day=1)
        elif period == "year": start_day, end_day = date(today.year, 1, 1), date(today.year + 1, 1, 1)
        else: start_day, end_day = today - timedelta(days=29), today + timedelta(days=1)
        start, end = local_midnight(start_day, c.timezone), local_midnight(end_day, c.timezone)
        items = [a for a in c.activities if start <= a.start_at.astimezone(c.timezone) < end]
        total = self._aggregate(items, c.timezone)
        breakdown = []
        for sport in SPORTS:
            values = self._aggregate([a for a in items if normalize_sport(a.sport) == sport], c.timezone)
            breakdown.append({"sport_type": sport, "activity_count": values["activity_count"], "moving_time_seconds": values["total_moving_time_seconds"], "distance_metres": values["total_distance_metres"], "elevation_metres": values["total_elevation_metres"]})
        return {"period": period, "period_start": start, "period_end": end, **total, "sport_breakdown": breakdown}

    def trends(self, user_id: UUID, weeks: int) -> list[dict]:
        c = self.context(user_id); current = week_start(c.now.astimezone(c.timezone).date()); first = current - timedelta(weeks=weeks - 1)
        result = []
        for index in range(weeks):
            start_day = first + timedelta(weeks=index); end_day = start_day + timedelta(days=7)
            start, end = local_midnight(start_day, c.timezone), local_midnight(end_day, c.timezone)
            values = self._aggregate([a for a in c.activities if start <= a.start_at.astimezone(c.timezone) < end], c.timezone)
            result.append({"week_start": start, "week_end": end, "activity_count": values["activity_count"], "moving_time_seconds": values["total_moving_time_seconds"], "distance_metres": values["total_distance_metres"], "elevation_metres": values["total_elevation_metres"], "active_days": values["active_days"]})
        return result

    def consistency(self, user_id: UUID, weeks: int) -> dict:
        c = self.context(user_id); trends = self.trends(user_id, weeks); flags = [x["activity_count"] > 0 for x in trends]
        longest = run = 0
        for active in flags:
            run = run + 1 if active else 0; longest = max(longest, run)
        current = 0
        for active in reversed(flags):
            if not active: break
            current += 1
        last = max((a.start_at for a in c.activities), default=None)
        return {"weeks": weeks, "active_weeks": sum(flags), "current_training_streak_weeks": current, "longest_training_streak_weeks": longest, "average_active_days_per_week": sum(x["active_days"] for x in trends) / weeks, "average_moving_time_seconds_per_week": sum(x["moving_time_seconds"] for x in trends) / weeks, "last_activity_at": last}

    @staticmethod
    def _aggregate(items: list[CompletedActivity], tz: ZoneInfo) -> dict:
        moving = [a.moving_time_s or 0 for a in items]; distances = [a.distance_m or 0 for a in items]
        return {"activity_count": len(items), "total_moving_time_seconds": int(sum(moving)), "total_distance_metres": float(sum(distances)), "total_elevation_metres": float(sum(a.elevation_gain_m or 0 for a in items)), "active_days": len({a.start_at.astimezone(tz).date() for a in items}), "longest_activity_seconds": max(moving, default=0), "longest_activity_distance_metres": float(max(distances, default=0))}
