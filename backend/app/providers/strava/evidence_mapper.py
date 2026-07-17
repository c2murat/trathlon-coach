from __future__ import annotations
import hashlib,json,math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime,timezone
from app.providers.base import InvalidPayloadError
SUPPORTED_STREAMS=("time","distance","heartrate","watts","cadence","altitude","velocity_smooth","latlng")
@dataclass(frozen=True,slots=True)
class MappedLap:
 provider_lap_id:str|None;provider_index:int;lap_index:int;name:str|None;start_date:datetime|None;elapsed_time_seconds:int|None;moving_time_seconds:int|None;distance_metres:float|None;elevation_metres:float|None;average_speed_metres_per_second:float|None;maximum_speed_metres_per_second:float|None;average_heart_rate:float|None;maximum_heart_rate:float|None;average_cadence:float|None;average_watts:float|None;lap_type:str|None;pace_zone:int|None
 def fields(self):return self.__dict__ if hasattr(self,"__dict__") else {name:getattr(self,name) for name in self.__dataclass_fields__}
@dataclass(frozen=True,slots=True)
class MappedStream:
 stream_type:str;original_resolution:str|None;original_series_type:str|None;original_sample_count:int;sample_count:int;values:list[object];retention_class:str;checksum:str;version:int=1
@dataclass(frozen=True,slots=True)
class MappedStreams:
 streams:tuple[MappedStream,...];invalid_streams:tuple[str,...];downsampled:bool
class StravaEvidenceMapper:
 def map_laps(self,payloads:tuple[object,...])->tuple[MappedLap,...]:
  result=[]
  for provider_index,payload in enumerate(payloads):
   if not isinstance(payload,Mapping):continue
   try:
    lap_index=_int(payload.get("lap_index"),required=True)
    result.append(MappedLap(_id(payload.get("id")),provider_index,lap_index,_text(payload.get("name"),300),_date(payload.get("start_date")),_int(payload.get("elapsed_time")),_int(payload.get("moving_time")),_number(payload.get("distance")),_number(payload.get("total_elevation_gain")),_number(payload.get("average_speed")),_number(payload.get("max_speed")),_number(payload.get("average_heartrate")),_number(payload.get("max_heartrate")),_number(payload.get("average_cadence")),_number(payload.get("average_watts")),_text(payload.get("type"),64),_int(payload.get("pace_zone"))))
   except InvalidPayloadError:continue
  if payloads and not result:raise InvalidPayloadError("Strava lap sequence is unusable")
  if len({x.lap_index for x in result})!=len(result):raise InvalidPayloadError("Strava lap sequence is unusable")
  return tuple(result)
 def map_streams(self,payloads:Mapping[str,object],requested:tuple[str,...],max_samples:int,location_enabled:bool)->MappedStreams:
  parsed:dict[str,tuple[list[object],str|None,str|None]]={};invalid=[]
  for kind in requested:
   if kind=="latlng" and not location_enabled:continue
   raw=payloads.get(kind)
   try:
    if raw is None:continue
    if not isinstance(raw,Mapping) or not isinstance(raw.get("data"),list):raise InvalidPayloadError("Invalid stream")
    values=list(raw["data"]);_validate_values(kind,values);parsed[kind]=(values,_text(raw.get("resolution"),32),_text(raw.get("series_type"),32))
   except InvalidPayloadError:invalid.append(kind)
  basis=next((kind for kind in ("time","distance",*requested) if kind in parsed),None)
  if not basis:return MappedStreams((),tuple(invalid),False)
  original=len(parsed[basis][0]);aligned={k:v for k,v in parsed.items() if len(v[0])==original}
  invalid.extend(k for k in parsed if k not in aligned)
  indices=shared_sample_indices(original,max_samples);down=len(indices)<original;streams=[]
  for kind,(values,resolution,series_type) in aligned.items():
   retained=[values[i] for i in indices];encoded=json.dumps(retained,separators=(",",":"),ensure_ascii=False)
   streams.append(MappedStream(kind,resolution,series_type,original,len(retained),retained,"location" if kind=="latlng" else "standard",hashlib.sha256(encoded.encode()).hexdigest()))
  return MappedStreams(tuple(streams),tuple(dict.fromkeys(invalid)),down)
def shared_sample_indices(count:int,maximum:int)->tuple[int,...]:
 if count<=0:return ()
 if count<=maximum:return tuple(range(count))
 if maximum<2:raise ValueError("Stream maximum must preserve endpoints")
 return tuple(round(i*(count-1)/(maximum-1)) for i in range(maximum))
def route_polyline(detail:Mapping[str,object])->str|None:
 value=detail.get("map")
 if not isinstance(value,Mapping):return None
 poly=value.get("summary_polyline")
 return poly if isinstance(poly,str) and poly.strip() else None
def _validate_values(kind:str,values:list[object])->None:
 last=None
 for value in values:
  if kind=="latlng":
   if not isinstance(value,list) or len(value)!=2 or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(float(x)) for x in value):raise InvalidPayloadError("Invalid location stream")
   lat,lon=map(float,value)
   if not -90<=lat<=90 or not -180<=lon<=180:raise InvalidPayloadError("Invalid location stream")
  else:
   if value is not None and (isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(float(value))):raise InvalidPayloadError("Invalid numeric stream")
   if kind in {"time","distance"} and value is not None:
    current=float(value)
    if current<0 or last is not None and current<last:raise InvalidPayloadError("Non-monotonic stream")
    last=current
def _id(v):return None if v is None else str(v)
def _text(v,n):
 if v is None:return None
 if not isinstance(v,str):raise InvalidPayloadError("Invalid text")
 return v.strip()[:n] or None
def _int(v,required=False):
 if v is None:
  if required:raise InvalidPayloadError("Missing integer")
  return None
 if isinstance(v,float) and v>=0 and v.is_integer():return int(v)
 if isinstance(v,bool) or not isinstance(v,int) or v<0:raise InvalidPayloadError("Invalid integer")
 return v
def _number(v):
 if v is None:return None
 if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(float(v)) or v<0:raise InvalidPayloadError("Invalid number")
 return float(v)
def _date(v):
 if v is None:return None
 if not isinstance(v,str):raise InvalidPayloadError("Invalid date")
 try:d=datetime.fromisoformat(v.replace("Z","+00:00"))
 except ValueError:raise InvalidPayloadError("Invalid date") from None
 if d.tzinfo is None:raise InvalidPayloadError("Invalid date")
 return d.astimezone(timezone.utc)
