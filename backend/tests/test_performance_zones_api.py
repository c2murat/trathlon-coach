from tests.test_performance_references_api import performance_client,payload

def test_performance_zones_endpoint_is_available(performance_client):
 c,_=performance_client; c.post("/athlete/performance-references",json=payload()); r=c.get("/athlete/performance-zones"); assert r.status_code==200; assert r.json()[0]["source_type"]=="granular_reference"

def test_all_granular_sport_families(performance_client):
 c,_=performance_client
 cases=[payload(value=250),payload(metric_type="heart_rate",unit="bpm",value=160),payload(sport="running",metric_type="pace",unit="s/km",value=270),payload(sport="running",metric_type="heart_rate",unit="bpm",value=165),payload(sport="swimming",metric_type="swim_pace",unit="s/100m",value=120)]
 for p in cases: assert c.post("/athlete/performance-references",json=p).status_code==201
 z=c.get("/athlete/performance-zones").json(); assert {(x["sport"],x["metric_type"]) for x in z}=={("cycling","power"),("cycling","heart_rate"),("running","pace"),("running","heart_rate"),("swimming","swim_pace")}; assert all(x["source_type"]=="granular_reference" and x["reference"]["reference_id"] for x in z)

def test_no_data_returns_empty(performance_client):
 c,_=performance_client; assert c.get("/athlete/performance-zones").json()==[]
