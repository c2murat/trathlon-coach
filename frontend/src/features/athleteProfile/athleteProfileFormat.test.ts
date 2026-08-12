import {describe,expect,it} from "vitest";
import {centimetersToMeters,feetAndInchesToMeters,kilogramsToPounds,metersToCentimeters,metersToFeetAndInches,poundsToKilograms} from "./athleteProfileFormat";
describe("athlete profile unit conversions",()=>{
 it("round-trips metric values without accumulated drift",()=>{expect(centimetersToMeters(metersToCentimeters(1.78))).toBe(1.78);expect(poundsToKilograms(kilogramsToPounds(73.5))).toBeCloseTo(73.5,1)});
 it("presents imperial height and returns canonical metres",()=>{expect(metersToFeetAndInches(1.78)).toEqual({feet:5,inches:10});expect(feetAndInchesToMeters(5,10)).toBeCloseTo(1.778,3)});
});
