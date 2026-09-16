from datetime import timedelta

from app.application.training_status import TrainingStatusApplication
from app.domains.training_status.interpretation import (
    MAX_CURRENT_AGE_DAYS, BROADER_CONTEXT_DAYS, TrainingStatusInterpreter, TrainingStatusObservation,
)


def observation(row):
    return TrainingStatusObservation(athlete_id=row.athlete_profile_id, date=row.local_date,
        fitness=row.fitness, fatigue=row.fatigue, form=row.form, is_warmup=row.is_warmup,
        timezone_name=row.timezone_name, training_load_algorithm_version=row.training_load_algorithm_version,
        manual_strength_algorithm_version=row.manual_strength_algorithm_version,
        training_status_algorithm_version=row.training_status_algorithm_version)


class TrainingStatusOverviewAssembler:
    def __init__(self, session):
        self.session = session

    def assemble(self, *, athlete_id, start_date, as_of_date, **configuration):
        application = TrainingStatusApplication(self.session)
        application._validate_range(start_date, as_of_date)
        with self.session.no_autoflush:
            rows = application.list_training_status(athlete_id,
                start_date=min(start_date, as_of_date-timedelta(days=BROADER_CONTEXT_DAYS+MAX_CURRENT_AGE_DAYS)),
                end_date=as_of_date, **configuration)
            latest = application.get_latest_training_status(athlete_id, as_of_date=as_of_date, **configuration)
        facts = tuple(observation(row) for row in rows)
        if latest is not None and all(row.local_date != latest.local_date for row in rows):
            facts += (observation(latest),)
        interpretation = TrainingStatusInterpreter().interpret(
            athlete_id=athlete_id, as_of_date=as_of_date, observations=facts)
        return tuple(row for row in rows if row.local_date >= start_date), latest, interpretation
