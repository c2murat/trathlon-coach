import { describe, expect, it } from "vitest";
import { formatDailyLoad, formatForm, formatHistoryDay, formatStatusDate, formatStatusValue, getTrainingStatusRange } from "./trainingStatusFormat";

describe("training status formatting", () => {
  it("formats fitness and fatigue with two decimals", () => {
    expect(formatStatusValue(46.3)).toBe("46,30");
    expect(formatStatusValue(61.42)).toBe("61,42");
  });
  it("formats positive, negative and zero form", () => {
    expect(formatForm(4.2)).toBe("+4,20");
    expect(formatForm(-15.1)).toBe("−15,10");
    expect(formatForm(0)).toBe("0,00");
  });
  it("formats load, date and historical day", () => {
    expect(formatDailyLoad(72.5)).toBe("72,50 puntos");
    expect(formatStatusDate("2026-08-03")).toBe("3 de agosto de 2026");
    expect(formatHistoryDay(93)).toBe("Día del historial: 93");
  });
  it.each([[4,"2026-07-07"],[8,"2026-06-09"],[12,"2026-05-12"]] as const)("creates an inclusive %i-week local range", (weeks,startDate) => {
    expect(getTrainingStatusRange(weeks,new Date(2026,7,3,12))).toEqual({startDate,endDate:"2026-08-03"});
  });
  it("uses exactly 28 inclusive calendar days for four weeks", () => {
    const range=getTrainingStatusRange(4,new Date(2026,7,3,23,59));
    const days=(Date.parse(range.endDate)-Date.parse(range.startDate))/86400000+1;
    expect(days).toBe(28);
  });
});
