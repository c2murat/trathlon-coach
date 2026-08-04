from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, model_validator
from sqlalchemy.orm import Session
from app.api.dependencies.current_athlete import CurrentAthleteContext, get_current_athlete
from app.application.performance_references import PerformanceReferenceRepository
from app.db.session import get_db_session
from app.domains.performance_profile.zones import *
router = APIRouter(prefix="/athlete/performance-references", tags=["performance-references"])
class RefIn(BaseModel):
    sport: Sport; metric_type: MetricType; value: float; unit: Unit; data_origin: DataOrigin; quality_level: QualityLevel
    effective_from: datetime; measured_at: datetime|None=None; calculation_method: CalculationMethod|None=None; algorithm_version: str|None=None; source_note: str|None=None
    @model_validator(mode="after")
    def valid(self):
        if self.value <= 0: raise ValueError("El valor debe ser positivo")
        validate_reference_compatibility(self.sport, self.metric_type, self.unit)
        if self.data_origin is DataOrigin.DERIVED and (not self.calculation_method or not self.algorithm_version): raise ValueError("Una referencia derivada requiere método y versión")
        if self.data_origin is DataOrigin.MEASURED and self.measured_at is None: raise ValueError("Una referencia medida requiere fecha de medición")
        return self
class RefOut(RefIn):
    id: str; athlete_profile_id: str; created_at: datetime; updated_at: datetime; effective: bool=False
def rowout(r, effective=False): return RefOut(id=str(r.id), athlete_profile_id=str(r.athlete_profile_id), sport=r.sport, metric_type=r.metric_type, value=float(r.value), unit=r.unit, data_origin=r.data_origin, quality_level=r.quality_level, effective_from=r.effective_from, measured_at=r.measured_at, calculation_method=r.calculation_method, algorithm_version=r.algorithm_version, source_note=r.source_note, created_at=r.created_at, updated_at=r.updated_at, effective=effective)
def filters(sport, metric_type, effective_at): return sport, metric_type, effective_at or datetime.now(timezone.utc)
@router.get("/history", response_model=list[RefOut])
def history(sport: Sport|None=None, metric_type: MetricType|None=None, effective_at: datetime|None=None, current_athlete: CurrentAthleteContext=Depends(get_current_athlete), session: Session=Depends(get_db_session)):
    return [rowout(x) for x in PerformanceReferenceRepository(session).list_history(current_athlete.athlete_id,sport,metric_type,effective_at)]
@router.get("", response_model=list[RefOut])
def current(sport: Sport|None=None, metric_type: MetricType|None=None, effective_at: datetime|None=None, current_athlete: CurrentAthleteContext=Depends(get_current_athlete), session: Session=Depends(get_db_session)):
    at=effective_at or datetime.now(timezone.utc); repo=PerformanceReferenceRepository(session)
    if sport and metric_type: rows=[repo.best_effective_reference(current_athlete.athlete_id,sport,metric_type,at)]
    else: rows=repo.list_current_references(current_athlete.athlete_id,at)
    rows=[r for r in rows if r and (not sport or r.sport==sport.value) and (not metric_type or r.metric_type==metric_type.value)]
    return [rowout(x,True) for x in rows]
@router.get("/{reference_id}", response_model=RefOut)
def detail(reference_id: str, current_athlete: CurrentAthleteContext=Depends(get_current_athlete), session: Session=Depends(get_db_session)):
    r=PerformanceReferenceRepository(session).get_reference(current_athlete.athlete_id,reference_id)
    if not r: raise HTTPException(404,"reference_not_found")
    return rowout(r)
@router.post("", response_model=RefOut, status_code=201)
def create(data: RefIn, current_athlete: CurrentAthleteContext=Depends(get_current_athlete), session: Session=Depends(get_db_session)):
    try:
        ref=PerformanceReference(data.sport,data.metric_type,data.value,data.unit,data.data_origin,data.algorithm_version or ALGORITHM_VERSION,data.effective_from,data.calculation_method,data.source_note,data.quality_level,data.measured_at)
        r=PerformanceReferenceRepository(session).add_reference(current_athlete.athlete_id,ref); session.commit(); session.refresh(r); return rowout(r)
    except ValueError as e: session.rollback(); raise HTTPException(422,str(e))

