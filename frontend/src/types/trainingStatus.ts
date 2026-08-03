export const TRAINING_STATUS_PERIODS = [4, 8, 12] as const;
export type TrainingStatusPeriodWeeks = (typeof TRAINING_STATUS_PERIODS)[number];

export interface DailyTrainingStatus {
  date: string;
  timezone_name: string;
  total_load: number;
  fitness: number;
  fatigue: number;
  form: number;
  history_day_number: number;
  is_warmup: boolean;
  training_load_algorithm_version: string;
  manual_strength_algorithm_version: string;
  training_status_algorithm_version: string;
  calculated_at: string;
}

export interface TrainingStatusQuery {
  startDate: string;
  endDate: string;
  timezoneName: string;
  trainingLoadAlgorithmVersion?: string;
  manualStrengthAlgorithmVersion?: string;
  trainingStatusAlgorithmVersion?: string;
}

export type LatestTrainingStatusQuery = Omit<
  TrainingStatusQuery,
  "startDate" | "endDate"
>;
