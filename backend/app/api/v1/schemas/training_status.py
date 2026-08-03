from datetime import date, datetime

from pydantic import BaseModel, Field


class DailyTrainingStatusResponse(BaseModel):
    date: date
    timezone_name: str
    total_load: float
    fitness: float = Field(
        description="Carga crónica suavizada con constante temporal de 42 días."
    )
    fatigue: float = Field(
        description="Carga aguda suavizada con constante temporal de 7 días."
    )
    form: float = Field(description="Fitness menos fatigue.")
    history_day_number: int
    is_warmup: bool = Field(
        description="Indica que todavía no existen 85 días completos de historia."
    )
    training_load_algorithm_version: str
    manual_strength_algorithm_version: str
    training_status_algorithm_version: str
    calculated_at: datetime
