from app.domains.training_load import *
def test_power():
 r=calculate(TrainingLoadInput(Sport.CYCLING,moving_time_seconds=3600,normalized_power_watts=200,ftp_watts=250)); assert r.load==64 and r.quality is TrainingLoadQuality.HIGH
def test_duration_fallback():
 r=calculate(TrainingLoadInput(Sport.RUNNING,moving_time_seconds=3600)); assert r.load==50 and r.coverage is TrainingLoadCoverage.PARTIAL
def test_pace_direction():
 a=calculate(TrainingLoadInput(Sport.RUNNING,moving_time_seconds=3600,average_pace_seconds_per_km=240,running_threshold_pace_seconds_per_km=300)); b=calculate(TrainingLoadInput(Sport.RUNNING,moving_time_seconds=3600,average_pace_seconds_per_km=300,running_threshold_pace_seconds_per_km=300)); assert a.load>b.load
def test_missing_duration(): assert calculate(TrainingLoadInput(Sport.CYCLING)).load is None
def test_hr_reserve():
 r=calculate(TrainingLoadInput(Sport.CYCLING,moving_time_seconds=3600,average_heart_rate_bpm=150,resting_heart_rate_bpm=50,reference_max_heart_rate_bpm=200)); assert r.load==44.44

