import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Consistency, DashboardSummary, WeeklyTrend } from "../../types/api";
import { AthleteOverview } from "./AthleteOverview";
const summary:DashboardSummary={period:"week",period_start:"2026-07-13T00:00:00Z",period_end:"2026-07-20T00:00:00Z",activity_count:3,total_moving_time_seconds:5400,total_distance_metres:12000,total_elevation_metres:200,active_days:2,longest_activity_seconds:3000,longest_activity_distance_metres:8000,sport_breakdown:[{sport_type:"running",activity_count:2,moving_time_seconds:3600,distance_metres:10000,elevation_metres:150},{sport_type:"swimming",activity_count:1,moving_time_seconds:1800,distance_metres:2000,elevation_metres:0}]};
const trends:WeeklyTrend[]=Array.from({length:8},(_,i)=>({week_start:`2026-06-${String(i+1).padStart(2,"0")}T00:00:00Z`,week_end:`2026-06-${String(i+8).padStart(2,"0")}T00:00:00Z`,activity_count:i,moving_time_seconds:i*600,distance_metres:i*1000,elevation_metres:i*10,active_days:i?1:0}));
const consistency:Consistency={weeks:12,active_weeks:9,current_training_streak_weeks:3,longest_training_streak_weeks:5,average_active_days_per_week:2.5,average_moving_time_seconds_per_week:3000,last_activity_at:"2026-07-14T06:00:00Z"};
const props={summary,trends,consistency,loading:false,error:null,onRetry:vi.fn()};
describe("AthleteOverview",()=>{
 it("renders weekly totals, sports, trend and consistency in Spanish",()=>{render(<AthleteOverview {...props}/>);expect(screen.getByRole("heading",{name:"Esta semana"})).toBeInTheDocument();expect(screen.getByText("3")).toBeInTheDocument();expect(screen.getByRole("heading",{name:"Natación"})).toBeInTheDocument();expect(screen.getByRole("img",{name:/tiempo de entrenamiento por semana/i})).toBeInTheDocument();expect(screen.getByText("9 de 12")).toBeInTheDocument();expect(screen.getAllByText("30:00").length).toBeGreaterThan(0);expect(screen.getByText("4,0 km")).toBeInTheDocument();});
 it("renders a zero-safe empty summary",()=>{render(<AthleteOverview {...props} summary={{...summary,activity_count:0,total_moving_time_seconds:0,total_distance_metres:0,total_elevation_metres:0,active_days:0,sport_breakdown:[]}}/>);expect(screen.getAllByText("0").length).toBeGreaterThan(0);expect(screen.getAllByText("0,0 km").length).toBeGreaterThan(0);});
 it("has an independent loading state",()=>{render(<AthleteOverview {...props} loading/>);expect(screen.getByText(/cargando resumen/i)).toBeInTheDocument();});
 it("shows a safe retry on analytics error",async()=>{const retry=vi.fn();render(<AthleteOverview {...props} error="No se ha podido cargar el resumen de entrenamiento." onRetry={retry}/>);await userEvent.click(screen.getByRole("button",{name:"Reintentar resumen"}));expect(retry).toHaveBeenCalledOnce();});
});


