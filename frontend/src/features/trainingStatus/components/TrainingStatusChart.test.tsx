import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { DailyTrainingStatus } from "../../../types/trainingStatus";
import { TrainingStatusChart } from "./TrainingStatusChart";

const row:DailyTrainingStatus={date:"2026-08-03",timezone_name:"Europe/Madrid",total_load:72.5,fitness:46.31,fatigue:61.42,form:-15.11,history_day_number:93,is_warmup:false,training_load_algorithm_version:"0.7b.1",manual_strength_algorithm_version:"0.7e.1",training_status_algorithm_version:"0.7f.1",calculated_at:"2026-08-03T08:00:00Z"};

describe("TrainingStatusChart",()=>{
  it("renders three independent labelled series, axes and zero line",()=>{
    const {container}=render(<TrainingStatusChart rows={[row]}/>);
    expect(screen.getByRole("img",{name:"Gráfico diario de Fitness, Fatiga y Forma"})).toBeInTheDocument();
    expect(screen.getByText("Fitness")).toBeInTheDocument();
    expect(screen.getByText("Fatiga")).toBeInTheDocument();
    expect(screen.getByText("Forma")).toBeInTheDocument();
    expect(screen.getByText("Valor")).toBeInTheDocument();
    expect(screen.getByText("Fecha")).toBeInTheDocument();
    expect(container.querySelector(".status-chart__zero")).toBeInTheDocument();
    expect(container.querySelectorAll(".status-chart__line")).toHaveLength(3);
  });
  it("exposes the complete negative-form tooltip to keyboard and screen readers",()=>{
    render(<TrainingStatusChart rows={[row]}/>);
    const point=screen.getByRole("img",{name:/Carga: 72,50 puntos; Fitness: 46,31; Fatiga: 61,42; Forma: −15,11/});
    expect(point).toHaveAttribute("tabindex","0");
    expect(point).toHaveAccessibleName(/Historial consolidado/);
  });
  it("supports warm-up, one point and all-zero values",()=>{
    const zero={...row,total_load:0,fitness:0,fatigue:0,form:0,is_warmup:true,history_day_number:1};
    const {container}=render(<TrainingStatusChart rows={[zero]}/>);
    expect(screen.getByRole("img",{name:/En adaptación/})).toBeInTheDocument();
    expect(container.querySelectorAll(".status-chart__point")).toHaveLength(3);
    expect(container.innerHTML).not.toContain("NaN");
    expect(container.innerHTML).not.toContain("Infinity");
  });
  it("renders discontinuous dates in chronological order",()=>{
    render(<TrainingStatusChart rows={[{...row,date:"2026-08-05"},{...row,date:"2026-08-01"}]}/>);
    const points=screen.getAllByRole("img",{name:/de agosto de 2026; Carga:/});
    expect(points[0]).toHaveAccessibleName(/1 de agosto/);
    expect(points[1]).toHaveAccessibleName(/5 de agosto/);
  });
});
