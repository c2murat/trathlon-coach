from datetime import date,datetime,timezone
from typing import Literal,Protocol
from pydantic import BaseModel,ConfigDict,Field
from app.domains.planning.models import CompetitionGoalSegmentInput
class CatalogError(RuntimeError):
 def __init__(self,code:str):self.code=code
class CatalogSearch(BaseModel):
 model_config=ConfigDict(extra="forbid");text:str|None=Field(default=None,max_length=200);category:str|None=None;start_date:date|None=None;end_date:date|None=None;location:str|None=Field(default=None,max_length=120);limit:int=Field(default=20,ge=1,le=50)
class CatalogEvidence(BaseModel):
 model_config=ConfigDict(extra="forbid");url:str;title:str|None=None;official:bool=False;source_kind:Literal["official","registration","timing","specialized_calendar","web"]|None=None
class CatalogEvent(BaseModel):
 model_config=ConfigDict(extra="forbid");provider:str;external_id:str;name:str;start_date:date;end_date:date|None=None;category:Literal["triathlon","running","cycling","swimming","duathlon","aquathlon"]|None=None;event_format:str|None=None;city:str|None=None;region:str|None=None;country:str|None=None;latitude:float|None=None;longitude:float|None=None;source_url:str|None=None;segments:list[CompetitionGoalSegmentInput]=Field(default_factory=list);confidence:Literal["high","medium","low"]|None=None;evidence:list[CatalogEvidence]=Field(default_factory=list);retrieved_at:datetime=Field(default_factory=lambda:datetime.now(timezone.utc))
class CatalogProviderInfo(BaseModel):
 provider:str;label:str;configured:bool;supported_categories:list[str]
 search_mode:Literal["structured","web"]="structured"
 supports_structured_detail:bool=True
 supports_structured_import:bool=True
 supports_search_to_manual_goal:bool=False
class WebCompetitionHints(BaseModel):
 model_config=ConfigDict(extra="forbid");possible_date:date|None=None;possible_location:str|None=None;possible_category:str|None=None;possible_distance:str|None=None
class WebCompetitionSearchResult(BaseModel):
 model_config=ConfigDict(extra="forbid");id:str;title:str;url:str;snippet:str;source_domain:str;source_label:str;source_kind:str;result_kind:Literal["event_candidate","event_listing","other_sports_resource"];hints:WebCompetitionHints=Field(default_factory=WebCompetitionHints)
class WebCompetitionSearchResponse(BaseModel):
 results:list[WebCompetitionSearchResult];has_more:bool;phase:Literal["initial","more"]
class CompetitionCatalogProvider(Protocol):
 name:str;label:str;supported_categories:tuple[str,...]
 @property
 def configured(self)->bool:...
 def search(self,query:CatalogSearch)->list[CatalogEvent]:...
 def detail(self,external_id:str)->CatalogEvent:...
