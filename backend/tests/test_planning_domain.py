from datetime import date,timedelta
import pytest
from pydantic import ValidationError
from app.domains.planning.models import CompetitionGoalInput,StructuredWorkoutDefinition

def goal(**values):
 base={"name":"Objetivo","event_date":date.today()+timedelta(days=30),"timezone":"Europe/Madrid","event_category":"running","event_format":"10k","priority":"A","distance_m":10000}
 return CompetitionGoalInput.model_validate({**base,**values})
@pytest.mark.parametrize("priority",["A","B","C"])
def test_goal_priorities_and_single_sport(priority):assert goal(priority=priority).distance_m==10000
@pytest.mark.parametrize("values",[{"priority":"D"},{"target_finish_time_seconds":0},{"distance_m":-1},{"timezone":"Invalid/Zone"},{"event_category":"triathlon"}])
def test_goal_rejects_invalid_values(values):
 with pytest.raises(ValidationError):goal(**values)
def test_triathlon_has_structured_distances():
 item=goal(event_category="triathlon",event_format="70.3",distance_m=None,swim_distance_m=1900,bike_distance_m=90000,run_distance_m=21100);assert item.bike_distance_m==90000

def definition():return {"schema_version":1,"sport":"cycling","steps":[{"kind":"step","phase":"warmup","duration":{"mode":"time","seconds":900},"target":{"metric":"heart_rate","mode":"zone","zone_min":1,"zone_max":2}},{"kind":"repeat","repetitions":3,"steps":[{"kind":"step","phase":"work","duration":{"mode":"time","seconds":720},"target":{"metric":"power","mode":"percent_reference","reference":"FTP","minimum":.9,"maximum":.95}},{"kind":"step","phase":"recovery","duration":{"mode":"distance","meters":1000},"target":{"metric":"none","mode":"none"}}]},{"kind":"step","phase":"cooldown","duration":{"mode":"open"}}]}
def test_structured_workout_roundtrip_time_distance_open_percent_and_repeat():
 parsed=StructuredWorkoutDefinition.model_validate(definition());assert parsed.model_dump(mode="json",exclude_none=True)==definition();assert parsed.steps[1].steps[0].target.reference=="FTP"
@pytest.mark.parametrize("change",[("schema_version",2),("steps",[]),])
def test_workout_rejects_invalid_root(change):
 value=definition();value[change[0]]=change[1]
 with pytest.raises(ValidationError):StructuredWorkoutDefinition.model_validate(value)
@pytest.mark.parametrize("reference",["threshold_hr","threshold_pace","CSS"])
def test_percent_references(reference):
 value=definition();value["steps"][1]["steps"][0]["target"].update(reference=reference);assert StructuredWorkoutDefinition.model_validate(value)
def test_invalid_ranges_and_negative_duration():
 value=definition();value["steps"][0]["target"].update(zone_min=4,zone_max=2)
 with pytest.raises(ValidationError):StructuredWorkoutDefinition.model_validate(value)
 value=definition();value["steps"][0]["duration"]["seconds"]=-1
 with pytest.raises(ValidationError):StructuredWorkoutDefinition.model_validate(value)
