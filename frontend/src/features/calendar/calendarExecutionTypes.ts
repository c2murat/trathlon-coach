import type {ExecutionSessionView} from "../dashboard/executionOverviewTypes";
export interface CalendarExecution {
  athlete_id:string;as_of_date:string;timezone:string;start_date:string;end_date:string;
  evidence_version:string;sessions:ExecutionSessionView[];
}
