import { describe, expect, it } from "vitest";
import { formatTrainingLoad, formatTrainingDuration, formatTrainingLoadDate, formatIsoWeekLabel, getTrainingLoadCoverageLabel, getTrainingLoadQualityLabel } from "./trainingLoadFormat";

describe("training load formatters", () => {
  it("formats values and reliability labels", () => {
    expect(formatTrainingLoad(144.9)).toBe("144,9");
    expect(formatTrainingLoad(144)).toBe("144");
    expect(formatTrainingDuration(2481)).toBe("41 min");
    expect(formatTrainingDuration(3900)).toBe("1 h 5 min");
    expect(formatTrainingDuration(0)).toBe("0 min");
    expect(formatTrainingLoadDate("2026-07-19")).toBe("19 de julio de 2026");
    expect(formatIsoWeekLabel(2026, 29)).toBe("Semana 29 · 2026");
    expect(getTrainingLoadCoverageLabel("partial")).toBe("Parcial");
    expect(getTrainingLoadQualityLabel("high")).toBe("Fiabilidad alta");
    expect(getTrainingLoadQualityLabel("medium")).toBe("Fiabilidad media");
    expect(getTrainingLoadQualityLabel("low")).toBe("Fiabilidad baja");
    expect(getTrainingLoadQualityLabel("none")).toBe("No evaluable");
    expect(getTrainingLoadQualityLabel(null)).toBe("No evaluable");
  });
});
