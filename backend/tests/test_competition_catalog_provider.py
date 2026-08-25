from datetime import date
import httpx
import pytest
from app.domains.competition_catalog.models import CatalogError,CatalogSearch
from app.integrations.competition_catalog.world_triathlon import WorldTriathlonProvider

PAYLOAD={"data":{"events":[{"event_id":123,"event_title":"Madrid Multisport","event_date":"2027-05-01","event_finish_date":"2027-05-02","event_venue":"Madrid","event_region_name":"Madrid","event_country":"Spain","event_latitude":40.4,"event_longitude":-3.7,"event_listing":"https://triathlon.org/events/123","event_specifications":[{"cat_name":"Triathlon"}],"segments":[{"sport":"Swimming","distance_m":1500},{"sport":"Cycling","distance_m":40000},{"sport":"Running","distance_m":10000}]}]}}
def transport(payload=PAYLOAD,status=200):return httpx.MockTransport(lambda request:httpx.Response(status,json=payload))
def test_world_triathlon_search_normalizes_fixture_and_preserves_order():
 provider=WorldTriathlonProvider("secret",transport=transport());events=provider.search(CatalogSearch(text="Madrid",start_date=date(2027,1,1)));event=events[0];assert event.external_id=="123" and event.category=="triathlon";assert [x.sport for x in event.segments]==["swim","bike","run"]
def test_world_triathlon_detail_and_invalid_payload():
 detail={"data":{"event":PAYLOAD["data"]["events"][0]}};assert WorldTriathlonProvider("secret",transport=transport(detail)).detail("123").city=="Madrid"
 with pytest.raises(CatalogError,match="") as exc:WorldTriathlonProvider("secret",transport=transport({"data":{"events":"bad"}})).search(CatalogSearch())
 assert exc.value.code=="provider_invalid_response"
def test_world_triathlon_not_configured_timeout_and_remote_errors():
 with pytest.raises(CatalogError) as exc:WorldTriathlonProvider(None).search(CatalogSearch())
 assert exc.value.code=="provider_not_configured"
 timeout=httpx.MockTransport(lambda request:(_ for _ in ()).throw(httpx.ReadTimeout("late",request=request)))
 with pytest.raises(CatalogError) as exc:WorldTriathlonProvider("secret",transport=timeout).search(CatalogSearch())
 assert exc.value.code=="provider_timeout"
 for status,code in [(404,"competition_not_found"),(503,"provider_temporarily_unavailable"),(401,"provider_request_rejected")]:
  with pytest.raises(CatalogError) as exc:WorldTriathlonProvider("secret",transport=transport({},status)).detail("123")
  assert exc.value.code==code
