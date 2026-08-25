from datetime import date,datetime,time
from typing import Literal
from uuid import UUID
from pydantic import AnyHttpUrl,BaseModel,ConfigDict,Field,model_validator
Category=Literal["triathlon","running","cycling","swimming","duathlon","aquathlon"]
class CompetitionGoalSegmentRequest(BaseModel):
 model_config=ConfigDict(extra="forbid");sport:Literal["swim","bike","run"];distance_m:int=Field(gt=0);label:str|None=Field(default=None,max_length=100);elevation_gain_m:int|None=Field(default=None,ge=0)
class CompetitionGoalSegmentResponse(CompetitionGoalSegmentRequest):
 model_config=ConfigDict(from_attributes=True);position:int
class CompetitionGoalCreateRequest(BaseModel):
 model_config=ConfigDict(extra="forbid");name:str=Field(min_length=1,max_length=200);event_date:date;event_start_time:time|None=None;event_category:Category;event_format:str=Field(min_length=1,max_length=32);priority:Literal["A","B","C"];segments:list[CompetitionGoalSegmentRequest]|None=None;distance_m:int|None=Field(default=None,ge=0);swim_distance_m:int|None=Field(default=None,ge=0);bike_distance_m:int|None=Field(default=None,ge=0);run_distance_m:int|None=Field(default=None,ge=0);target_finish_time_seconds:int|None=Field(default=None,gt=0);notes:str|None=Field(default=None,max_length=4000);city:str|None=Field(default=None,max_length=120);region:str|None=Field(default=None,max_length=120);country:str|None=Field(default=None,max_length=120);source_provider:Literal["tavily"]|None=None;source_url:AnyHttpUrl|None=None
 @model_validator(mode="after")
 def source_pair(self):
  if bool(self.source_provider)!=bool(self.source_url):raise ValueError("source_provider and source_url must be supplied together")
  return self
class CompetitionGoalUpdateRequest(CompetitionGoalCreateRequest):
 name:str|None=Field(default=None,min_length=1,max_length=200);event_date:date|None=None;event_category:Category|None=None;event_format:str|None=Field(default=None,min_length=1,max_length=32);priority:Literal["A","B","C"]|None=None;status:Literal["active","completed","cancelled"]|None=None
class CompetitionGoalResponse(BaseModel):
 id:UUID;athlete_profile_id:UUID;name:str;event_date:date;event_start_time:time|None;timezone:str;event_category:str;event_format:str;priority:str;segments:list[CompetitionGoalSegmentResponse];distance_m:int|None;swim_distance_m:int|None;bike_distance_m:int|None;run_distance_m:int|None;target_finish_time_seconds:int|None;notes:str|None;city:str|None;region:str|None;country:str|None;status:str;created_by_user_id:UUID;source_provider:str|None;source_external_id:str|None;source_url:str|None;source_retrieved_at:datetime|None;created_at:datetime;updated_at:datetime
