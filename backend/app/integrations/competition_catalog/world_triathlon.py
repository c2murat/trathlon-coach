from datetime import datetime,timezone
import httpx
from pydantic import ValidationError
from app.domains.competition_catalog.models import CatalogError,CatalogEvent,CatalogSearch
class WorldTriathlonProvider:
 name="world_triathlon";label="World Triathlon";supported_categories=("triathlon","duathlon","aquathlon")
 def __init__(self,api_key:str|None,base_url:str="https://api.triathlon.org/v1",timeout:float=10,transport=None):self.api_key=api_key;self.base_url=base_url.rstrip("/");self.timeout=timeout;self.transport=transport
 @property
 def configured(self):return bool(self.api_key)
 def search(self,query:CatalogSearch):
  params={"per_page":query.limit,"order":"asc"};
  if query.text:params["name"]=query.text
  if query.start_date:params["start_date"]=query.start_date.isoformat()
  if query.end_date:params["end_date"]=query.end_date.isoformat()
  items=self._get("/events",params);rows=items if isinstance(items,list) else items.get("events",[]) if isinstance(items,dict) else None
  if not isinstance(rows,list):raise CatalogError("provider_invalid_response")
  result=[self._normalize(x) for x in rows]
  if query.category:result=[x for x in result if x.category==query.category]
  if query.location:
   term=query.location.casefold();result=[x for x in result if term in " ".join(filter(None,[x.city,x.region,x.country])).casefold()]
  return result
 def detail(self,external_id:str):
  if not external_id.isdigit():raise CatalogError("competition_not_found")
  value=self._get(f"/events/{external_id}",{});row=value.get("event",value) if isinstance(value,dict) else value
  if not isinstance(row,dict):raise CatalogError("provider_invalid_response")
  return self._normalize(row)
 def _get(self,path,params):
  if not self.configured:raise CatalogError("provider_not_configured")
  try:
   with httpx.Client(timeout=self.timeout,transport=self.transport) as client:r=client.get(self.base_url+path,params=params,headers={"apikey":self.api_key,"Accept":"application/json"})
  except httpx.TimeoutException:raise CatalogError("provider_timeout") from None
  except httpx.HTTPError:raise CatalogError("provider_temporarily_unavailable") from None
  if r.status_code==404:raise CatalogError("competition_not_found")
  if r.status_code>=500:raise CatalogError("provider_temporarily_unavailable")
  if r.status_code>=400:raise CatalogError("provider_request_rejected")
  try:payload=r.json()
  except ValueError:raise CatalogError("provider_invalid_response") from None
  if not isinstance(payload,dict):raise CatalogError("provider_invalid_response")
  return payload.get("data",payload)
 def _normalize(self,row):
  try:
   specs=row.get("event_specifications") or [];names=[str(x.get("cat_name","")).casefold() for x in specs if isinstance(x,dict)];category="duathlon" if any("duathlon" in x for x in names) else "aquathlon" if any("aquathlon" in x for x in names) else "triathlon" if any("triathlon" in x for x in names) else None;fmt=next((str(x.get("cat_name")) for x in specs if isinstance(x,dict) and str(x.get("cat_name","")).casefold() not in {"triathlon","duathlon","aquathlon"}),None);segments=[]
   for i,item in enumerate(row.get("segments") or []):
    sport={"swimming":"swim","cycling":"bike","running":"run"}.get(str(item.get("sport","")).casefold(),str(item.get("sport","")).casefold());distance=item.get("distance_m")
    if sport in {"swim","bike","run"} and isinstance(distance,(int,float)) and distance>0:segments.append({"position":i+1,"sport":sport,"distance_m":round(distance),"label":item.get("label"),"elevation_gain_m":item.get("elevation_gain_m")})
   return CatalogEvent(provider=self.name,external_id=str(row["event_id"]),name=row["event_title"],start_date=row["event_date"],end_date=row.get("event_finish_date"),category=category,event_format=fmt,city=row.get("event_venue"),region=row.get("event_region_name"),country=row.get("event_country"),latitude=row.get("event_latitude"),longitude=row.get("event_longitude"),source_url=row.get("event_listing"),segments=segments,retrieved_at=datetime.now(timezone.utc))
  except (KeyError,TypeError,ValidationError,ValueError):raise CatalogError("provider_invalid_response") from None
