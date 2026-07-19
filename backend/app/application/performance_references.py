from datetime import datetime
from uuid import UUID
from sqlalchemy import select
from app.db.models import AthletePerformanceReference
from app.domains.performance_profile.zones import CalculationMethod, DataOrigin, MetricType, PerformanceReference, QualityLevel, Sport, validate_reference_compatibility

class PerformanceReferenceRepository:
    def __init__(self, session): self.session = session
    def add_reference(self, athlete_id, reference: PerformanceReference):
        validate_reference_compatibility(reference.sport, reference.metric, reference.unit)
        if reference.value <= 0: raise ValueError("El valor debe ser positivo")
        if reference.origin is DataOrigin.DERIVED and (not reference.calculation_method or not reference.algorithm_version): raise ValueError("Una referencia derivada requiere método y versión")
        if reference.origin is DataOrigin.MEASURED and reference.measured_at is None: raise ValueError("Una referencia medida requiere fecha de medición")
        row = AthletePerformanceReference(athlete_profile_id=athlete_id, sport=reference.sport.value, metric_type=reference.metric.value, value=reference.value, unit=reference.unit.value, data_origin=reference.origin.value, quality_level=(reference.quality_level or QualityLevel.MEDIUM).value, effective_from=reference.effective_from, measured_at=reference.measured_at, calculation_method=reference.calculation_method.value if reference.calculation_method else None, algorithm_version=reference.algorithm_version, source_note=reference.source_note)
        self.session.add(row); return row
    def get_reference(self, athlete_id, reference_id):
        try: reference_id=UUID(str(reference_id))
        except ValueError: return None
        return self.session.scalar(select(AthletePerformanceReference).where(AthletePerformanceReference.id == reference_id, AthletePerformanceReference.athlete_profile_id == athlete_id))
    def history_for_metric(self, athlete_id, sport, metric): return list(self.session.scalars(select(AthletePerformanceReference).where(AthletePerformanceReference.athlete_profile_id == athlete_id, AthletePerformanceReference.sport == sport.value, AthletePerformanceReference.metric_type == metric.value).order_by(AthletePerformanceReference.effective_from.desc(), AthletePerformanceReference.id.desc())))
    def effective_reference(self, athlete_id, sport, metric, effective_at): return self.session.scalar(select(AthletePerformanceReference).where(AthletePerformanceReference.athlete_profile_id == athlete_id, AthletePerformanceReference.sport == sport.value, AthletePerformanceReference.metric_type == metric.value, AthletePerformanceReference.effective_from <= effective_at).order_by(AthletePerformanceReference.effective_from.desc(), AthletePerformanceReference.id.desc()).limit(1))
    def best_effective_reference(self, athlete_id, sport, metric, effective_at):
        rows = [r for r in self.history_for_metric(athlete_id, sport, metric) if r.effective_from <= effective_at]
        quality = {"confirmed": 4, "high": 3, "medium": 2, "low": 1}; origin = {"measured": 5, "manual": 4, "imported": 3, "derived": 2, "estimated": 1}
        return max(rows, key=lambda r: (quality.get(r.quality_level, 0), origin.get(r.data_origin, 0), r.measured_at or datetime.min, r.effective_from, r.created_at, str(r.id)), default=None)
    def list_history(self, athlete_id, sport=None, metric=None, effective_at=None):
        q = select(AthletePerformanceReference).where(AthletePerformanceReference.athlete_profile_id == athlete_id)
        if sport: q = q.where(AthletePerformanceReference.sport == sport.value)
        if metric: q = q.where(AthletePerformanceReference.metric_type == metric.value)
        if effective_at: q = q.where(AthletePerformanceReference.effective_from <= effective_at)
        return list(self.session.scalars(q.order_by(AthletePerformanceReference.effective_from.desc(), AthletePerformanceReference.id.desc())))
    def list_current_references(self, athlete_id, effective_at):
        rows = self.list_history(athlete_id, effective_at=effective_at); keys = sorted({(r.sport, r.metric_type) for r in rows})
        return [self.best_effective_reference(athlete_id, Sport(s), MetricType(m), effective_at) for s, m in keys]

