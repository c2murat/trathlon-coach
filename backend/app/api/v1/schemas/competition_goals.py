from datetime import date, datetime, time
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class CompetitionGoalCreateRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    name:str=Field(min_length=1,max_length=200);event_date:date;event_start_time:time|None=None
    event_category:Literal["triathlon","running","cycling","swimming"];event_format:str=Field(min_length=1,max_length=32);priority:Literal["A","B","C"]
    distance_m:int|None=Field(default=None,ge=0);swim_distance_m:int|None=Field(default=None,ge=0);bike_distance_m:int|None=Field(default=None,ge=0);run_distance_m:int|None=Field(default=None,ge=0)
    target_finish_time_seconds:int|None=Field(default=None,gt=0);notes:str|None=Field(default=None,max_length=4000)
class CompetitionGoalUpdateRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    name:str|None=Field(default=None,min_length=1,max_length=200);event_date:date|None=None;event_start_time:time|None=None
    event_category:Literal["triathlon","running","cycling","swimming"]|None=None;event_format:str|None=Field(default=None,min_length=1,max_length=32);priority:Literal["A","B","C"]|None=None
    distance_m:int|None=Field(default=None,ge=0);swim_distance_m:int|None=Field(default=None,ge=0);bike_distance_m:int|None=Field(default=None,ge=0);run_distance_m:int|None=Field(default=None,ge=0)
    target_finish_time_seconds:int|None=Field(default=None,gt=0);notes:str|None=Field(default=None,max_length=4000);status:Literal["active","completed","cancelled"]|None=None
class CompetitionGoalResponse(BaseModel):
    id:UUID;athlete_profile_id:UUID;name:str;event_date:date;event_start_time:time|None;timezone:str;event_category:str;event_format:str;priority:str;distance_m:int|None;swim_distance_m:int|None;bike_distance_m:int|None;run_distance_m:int|None;target_finish_time_seconds:int|None;notes:str|None;status:str;created_by_user_id:UUID;created_at:datetime;updated_at:datetime
