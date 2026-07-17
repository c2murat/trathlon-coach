import pytest
from app.providers.base import InvalidPayloadError
from app.providers.strava.evidence_mapper import StravaEvidenceMapper,shared_sample_indices

def stream(data,**extra):return {"data":data,"resolution":"high","series_type":"time",**extra}
def test_lap_mapping_preserves_units_missing_and_zero():
 laps=StravaEvidenceMapper().map_laps(({"id":1,"lap_index":1,"elapsed_time":60,"moving_time":0,"distance":400.0,"average_heartrate":None,"start_date":"2026-07-15T08:00:00Z"},))
 assert laps[0].distance_metres==400 and laps[0].moving_time_seconds==0 and laps[0].average_heart_rate is None

def test_malformed_lap_is_isolated_but_unusable_sequence_fails():
 mapper=StravaEvidenceMapper();laps=mapper.map_laps(({"lap_index":1},{"lap_index":"bad"}));assert len(laps)==1
 with pytest.raises(InvalidPayloadError):mapper.map_laps(({"lap_index":"bad"},))

def test_shared_indices_preserve_first_last_and_are_deterministic():
 assert shared_sample_indices(10,4)==(0,3,6,9);assert shared_sample_indices(10,4)==shared_sample_indices(10,4)

def test_aligned_streams_share_indices_and_record_counts():
 values=list(range(10));mapped=StravaEvidenceMapper().map_streams({"time":stream(values),"heartrate":stream([100+x for x in values])},("time","heartrate"),4,False)
 assert mapped.downsampled;assert mapped.streams[0].values==[0,3,6,9];assert mapped.streams[1].values==[100,103,106,109]
 assert all(x.original_sample_count==10 and x.sample_count==4 for x in mapped.streams)

def test_misaligned_or_malformed_stream_isolated():
 mapped=StravaEvidenceMapper().map_streams({"time":stream([0,1,2]),"watts":stream([1,2]),"heartrate":stream([100,"bad",120])},("time","watts","heartrate"),10,False)
 assert [x.stream_type for x in mapped.streams]==["time"];assert set(mapped.invalid_streams)=={"watts","heartrate"}

def test_invalid_latlng_rejected_and_location_disabled_not_retained():
 mapper=StravaEvidenceMapper();bad=mapper.map_streams({"time":stream([0,1]),"latlng":stream([[40,-3],[100,-3]])},("time","latlng"),10,True);assert "latlng" in bad.invalid_streams
 disabled=mapper.map_streams({"time":stream([0,1]),"latlng":stream([[40,-3],[41,-3]])},("time","latlng"),10,False);assert all(x.stream_type!="latlng" for x in disabled.streams)

def test_monotonic_time_and_distance_are_enforced():
 mapped=StravaEvidenceMapper().map_streams({"time":stream([0,2,1])},("time",),10,False);assert mapped.invalid_streams==("time",) and not mapped.streams
