import type {DailyTrainingStatus} from "../../types/trainingStatus";
export type FitnessTrend = "RISING" | "STABLE" | "FALLING" | "INSUFFICIENT_DATA";
export type FatigueTrend = FitnessTrend | "RISING_FAST";
export type FormState = "VERY_FRESH" | "FRESH" | "BALANCED" | "LOADED" | "HIGHLY_LOADED" | "INSUFFICIENT_DATA";
export type OverallState = "RECOVERING" | "FRESH" | "BALANCED" | "BUILDING" | "LOADED" | "HIGH_LOAD" | "REDUCED_LOAD" | "INSUFFICIENT_DATA";
export type NotableTrend = "FATIGUE_RISING_FASTER_THAN_FITNESS" | "RECOVERY_TREND" | "BOTH_STABLE" | "BOTH_FALLING" | "NO_NOTABLE_TREND" | "INSUFFICIENT_HISTORY";
export interface TrendWindow {
  days: number; start_date: string | null;
  fitness_delta: string | number | null; fatigue_delta: string | number | null;
  fitness_trend: FitnessTrend; fatigue_trend: FatigueTrend;
}
export interface RecentMovement {
  delta: string | number | null;
  direction: "RISING" | "STABLE" | "FALLING" | "MIXED" | "INSUFFICIENT_DATA";
  changed_direction: boolean;
}
export interface RecentStatus {
  days: number; start_date: string | null; fitness: RecentMovement; fatigue: RecentMovement;
  form_delta: string | number | null; recovery_turn: boolean;
}
export interface TrainingStatusInterpretation {
  short_term: TrendWindow; broader_context: TrendWindow; recent: RecentStatus;
  athlete_id: string; as_of_date: string; interpretation_version: string;
  data_date: string | null; window_start_date: string | null; trend_days: number;
  fitness: string | number | null; fatigue: string | number | null; form: string | number | null;
  fitness_delta: string | number | null; fatigue_delta: string | number | null;
  fitness_trend: FitnessTrend; fatigue_trend: FatigueTrend; form_state: FormState; overall_state: OverallState;
  headline_key: OverallState; summary_key: OverallState;
  fitness_explanation_key: FitnessTrend; fatigue_explanation_key: FatigueTrend; form_explanation_key: FormState;
  notable_trend_key: NotableTrend; reason_codes: string[];
}
export interface TrainingStatusOverview {
  series: DailyTrainingStatus[]; latest: DailyTrainingStatus | null; interpretation: TrainingStatusInterpretation;
}
