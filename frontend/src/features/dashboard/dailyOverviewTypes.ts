import type {Consistency, DashboardSummary, WeeklyTrend} from "../../types/api";
import type {TrainingStatusInterpretation} from "../trainingStatus/interpretationTypes";
import type {ExecutionOverview} from "./executionOverviewTypes";

export interface DailySession {
  id:string; scheduled_date:string; scheduled_start_time:string|null; sport:string; title:string;
  planned_duration_seconds:number|null; planned_distance_meters:number|null;
  status:"planned"|"completed"|"skipped"|"cancelled";
}
export interface DailyGoal {
  id:string;name:string;event_date:string;event_category:string;event_format:string;
  priority:string;city:string|null;days_remaining:number;
}
export interface DailyOverview {
  athlete_id:string;as_of_date:string;timezone:string;interpretation:TrainingStatusInterpretation;
  today_sessions:DailySession[];next_session:DailySession|null;next_goal:DailyGoal|null;
  execution:ExecutionOverview;summary:DashboardSummary;trends:WeeklyTrend[];consistency:Consistency;
}
