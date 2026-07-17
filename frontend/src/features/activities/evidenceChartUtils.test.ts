import {describe,expect,it} from "vitest";
import type {ActivityEvidence,EvidenceStream} from "../../types/api";
import {formatAxisDistance,formatSeriesValue,formatTime,prepareSeries,selectXAxis,stableTicks} from "./evidenceChartUtils";
const stream=(values:(number|null)[]):EvidenceStream=>({stream_type:"test",values,sample_count:values.length,original_sample_count:values.length,downsampled:false,series_type:"time"});
const base=(streams:ActivityEvidence["streams"]):ActivityEvidence=>({activity_id:"a",sport_type:"running",laps:[],streams,route:{available:false,retention_enabled:false,sample_count:0,polyline:null},fetched_at:null,partial:false,missing_streams:[],location_status:"privacy_disabled"});
describe("evidence chart utilities",()=>{
 it("formats elapsed time below and above one hour",()=>{expect(formatTime(65)).toBe("01:05");expect(formatTime(3661)).toBe("1:01:01")});
 it("formats metres and Spanish kilometres",()=>{expect(formatAxisDistance(850)).toBe("850 m");expect(formatAxisDistance(1250)).toBe("1,3 km")});
 it("converts smoothed velocity only for presentation",()=>{const original=stream([10]);expect(prepareSeries("velocity_smooth",original).values).toEqual([36]);expect(original.values).toEqual([10])});
 it("uses literal factual units",()=>{expect(prepareSeries("heartrate",stream([145])).unit).toBe("ppm");expect(prepareSeries("watts",stream([200])).unit).toBe("W");expect(prepareSeries("cadence",stream([90])).unit).toBe("rpm")});
 it("creates deterministic ticks including bounds",()=>{expect(stableTicks(0,100)).toEqual([0,25,50,75,100])});
 it("handles constant series with one stable tick",()=>{expect(stableTicks(12,12)).toEqual([12])});
 it("selects aligned time first",()=>{expect(selectXAxis(base({time:stream([0,30])}),2).kind).toBe("time")});
 it("falls back to aligned distance",()=>{expect(selectXAxis(base({time:stream([0]),distance:stream([0,500])}),2).kind).toBe("distance")});
 it("falls back to sample index without inventing points",()=>{const axis=selectXAxis(base({time:stream([0])}),3);expect(axis.kind).toBe("sample");expect(axis.values).toEqual([1,2,3]);expect(axis.warning).not.toBeNull()});
 it("formats factual values without unwanted decimals",()=>{expect(formatSeriesValue("watts",174)).toBe("174");expect(formatSeriesValue("altitude",12.5)).toBe("12,5")});
});
