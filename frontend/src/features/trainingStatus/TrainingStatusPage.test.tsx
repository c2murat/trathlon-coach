import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { DailyTrainingStatus } from "../../types/trainingStatus";
import { TrainingStatusPage } from "./TrainingStatusPage";

const latest:DailyTrainingStatus={date:"2026-08-03",timezone_name:"Europe/Madrid",total_load:72.5,fitness:46.31,fatigue:61.42,form:-15.11,history_day_number:84,is_warmup:true,training_load_algorithm_version:"0.7b.1",manual_strength_algorithm_version:"0.7e.1",training_status_algorithm_version:"0.7f.1",calculated_at:"2026-08-03T08:00:00Z"};
function client(overrides:Record<string,unknown>={}):any{return {listTrainingStatus:vi.fn().mockResolvedValue([latest]),getLatestTrainingStatus:vi.fn().mockResolvedValue(latest),recalculateTrainingStatus:vi.fn().mockResolvedValue([latest]),...overrides}}
function card(label:string){const summary=screen.getByLabelText("Estado más reciente");const value=within(summary).getByText(label).closest(".status-summary-card");expect(value).not.toBeNull();return within(value as HTMLElement)}

describe("TrainingStatusPage",()=>{
  it("shows loading and the legitimate global empty state without an error",async()=>{
    let resolve!: (value:DailyTrainingStatus[])=>void;
    const api=client({listTrainingStatus:vi.fn(()=>new Promise(r=>{resolve=r})),getLatestTrainingStatus:vi.fn().mockResolvedValue(null)});
    render(<TrainingStatusPage client={api}/>);
    expect(screen.getByRole("status")).toHaveTextContent("Cargando");
    resolve([]);
    expect(await screen.findByRole("heading",{name:"Todavía no hay un estado de entrenamiento calculado"})).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(api.recalculateTrainingStatus).not.toHaveBeenCalled();
  });
  it("renders four latest-value cards without summing the series",async()=>{
    render(<TrainingStatusPage client={client({listTrainingStatus:vi.fn().mockResolvedValue([latest,{...latest,date:"2026-08-02",fitness:100}])})}/>);
    await screen.findByRole("heading",{name:"Estado de entrenamiento"});
    await waitFor(()=>expect(screen.getByLabelText("Estado más reciente")).toBeInTheDocument());
    expect(card("Fitness").getByText("46,31")).toBeInTheDocument();
    expect(card("Fatiga").getByText("61,42")).toBeInTheDocument();
    expect(card("Forma").getByText("−15,11")).toBeInTheDocument();
    expect(card("Carga del día").getByText("72,50 puntos")).toBeInTheDocument();
    expect(screen.queryByText("146,31")).not.toBeInTheDocument();
  });
  it.each([[1,true],[84,true],[85,false]] as const)("handles warm-up on historical day %i",async(day,isWarmup)=>{
    const value={...latest,history_day_number:day,is_warmup:isWarmup};
    render(<TrainingStatusPage client={client({listTrainingStatus:vi.fn().mockResolvedValue([value]),getLatestTrainingStatus:vi.fn().mockResolvedValue(value)})}/>);
    if(isWarmup)expect(await screen.findByText(`Día histórico ${day} de 84`)).toBeInTheDocument();
    else expect(await screen.findByText("Historial consolidado")).toBeInTheDocument();
  });
  it("offers 4, 8 and 12 weeks and changing it only performs GET",async()=>{
    const api=client();const user=userEvent.setup();
    render(<TrainingStatusPage client={api}/>);
    const selector=await screen.findByLabelText("Periodo");
    expect(selector).toHaveValue("4");
    expect(screen.getByRole("option",{name:"Últimas 8 semanas"})).toBeInTheDocument();
    expect(screen.getByRole("option",{name:"Últimas 12 semanas"})).toBeInTheDocument();
    await user.selectOptions(selector,"8");
    await waitFor(()=>expect(api.listTrainingStatus).toHaveBeenCalledTimes(2));
    expect(api.recalculateTrainingStatus).not.toHaveBeenCalled();
  });
  it("recalculates explicitly, updates data and announces success",async()=>{
    const updated={...latest,fitness:50,form:4.2,is_warmup:false,history_day_number:93};
    const api=client({recalculateTrainingStatus:vi.fn().mockResolvedValue([updated]),getLatestTrainingStatus:vi.fn().mockResolvedValueOnce(latest).mockResolvedValueOnce(updated)});
    const user=userEvent.setup();render(<TrainingStatusPage client={api}/>);
    await user.click(await screen.findByRole("button",{name:"Recalcular estado"}));
    expect(await screen.findByText("Estado de entrenamiento recalculado correctamente.")).toBeInTheDocument();
    expect(card("Fitness").getByText("50,00")).toBeInTheDocument();
    expect(card("Forma").getByText("+4,20")).toBeInTheDocument();
    expect(api.recalculateTrainingStatus).toHaveBeenCalledTimes(1);
  });
  it("prevents duplicate recalculation submissions",async()=>{
    let resolve!: (value:DailyTrainingStatus[])=>void;
    const api=client({recalculateTrainingStatus:vi.fn(()=>new Promise(r=>{resolve=r}))});
    const user=userEvent.setup();render(<TrainingStatusPage client={api}/>);
    const button=await screen.findByRole("button",{name:"Recalcular estado"});
    await user.dblClick(button);
    expect(api.recalculateTrainingStatus).toHaveBeenCalledTimes(1);
    expect(button).toBeDisabled();resolve([latest]);
  });
  it("treats empty recalculation as missing source loads",async()=>{
    const api=client({listTrainingStatus:vi.fn().mockResolvedValue([]),getLatestTrainingStatus:vi.fn().mockResolvedValue(null),recalculateTrainingStatus:vi.fn().mockResolvedValue([])});
    const user=userEvent.setup();render(<TrainingStatusPage client={api}/>);
    await user.click(await screen.findByRole("button",{name:"Calcular estado de entrenamiento"}));
    expect(await screen.findByRole("heading",{name:"No hay carga de entrenamiento disponible"})).toBeInTheDocument();
  });
  it("keeps existing data on recalculation error and shows neutral interpretation",async()=>{
    const api=client({recalculateTrainingStatus:vi.fn().mockRejectedValue(new Error("failed"))});
    const user=userEvent.setup();render(<TrainingStatusPage client={api}/>);
    await user.click(await screen.findByRole("button",{name:"Recalcular estado"}));
    expect(await screen.findByRole("alert")).toHaveTextContent("No se ha podido recalcular");
    expect(card("Fitness").getByText("46,31")).toBeInTheDocument();
    expect(screen.getByText("Cómo interpretar estos datos")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/diagnóstico|recomendación automática|sobreentrenamiento/i);
    expect(screen.getByText(/Última actualización:/)).toBeInTheDocument();
  });
  it("shows a query error without rendering invalid numbers",async()=>{
    render(<TrainingStatusPage client={client({listTrainingStatus:vi.fn().mockRejectedValue(new Error("failed"))})}/>);
    expect(await screen.findByRole("alert")).toHaveTextContent("No se ha podido consultar");
    expect(document.body.textContent).not.toContain("NaN");
    expect(document.body.textContent).not.toContain("Infinity");
  });
});
