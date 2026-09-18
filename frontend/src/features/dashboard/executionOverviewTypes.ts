import type {StructuredWorkoutDefinition} from "../../types/planning";

export type CompletionStatus = "COMPLETED" | "PARTIAL" | "OVER_DURATION" | "UNKNOWN" | "UNMATCHED";
export interface TargetAdherenceEvidence {
  planned_repetitions:number; matched_repetitions:number; target_hit_fraction:string|number;
  execution_relation:string; confidence:"HIGH"|"MEDIUM"|"LOW"|"INSUFFICIENT";
}
export interface SessionExecutionEvidence {
  planned_session_id:string; completion_status:CompletionStatus;
  actual_duration_seconds:number|null; actual_distance_m:string|number|null;
  comparison_confidence:string; sport_match:boolean|null; target_comparison:TargetAdherenceEvidence|null;
  source_activity_ids:string[];
  link_provenance:Array<{activity_id:string;match_source:string;match_confidence:string;matching_algorithm_version:string|null}>;
}
export interface ActivityFacts {
  id:string;name:string;sport:string;started_at:string;timezone:string;duration_seconds:number;
  distance_meters:number|null;average_heart_rate_bpm:number|null;average_power_w:number|null;
}
export interface ExecutionSessionView {
  id:string;date:string;sport:string;title:string;planned_duration_seconds:number|null;
  planned_distance_meters:number|null;workout:StructuredWorkoutDefinition|null;
  evidence:SessionExecutionEvidence|null;activities:ActivityFacts[];
}
export interface ExecutionOverview {
  athlete_id:string;as_of_date:string;window_start_date:string;evidence_version:string;
  latest_activity:ActivityFacts|null;latest_activity_sessions:ExecutionSessionView[];recent_sessions:ExecutionSessionView[];
}
