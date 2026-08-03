export type BodyRegion = "full_body"|"chest"|"back"|"shoulders"|"arms"|"core"|"quadriceps"|"hamstrings"|"glutes"|"calves";
export interface ManualStrengthTrainingLoad {load_value:number;method:"strength_rpe"|"strength_duration";unit:"points";quality:"low"|"medium";warnings:string[];algorithm_version:string;calculated_at:string}
export interface ManualStrengthSession {id:string;started_at:string;timezone_name:string;duration_minutes:number;body_regions:BodyRegion[];perceived_exertion:number|null;notes:string|null;created_at:string;updated_at:string;training_load:ManualStrengthTrainingLoad}
export interface ManualStrengthSessionCreate {started_at:string;timezone_name:string;duration_minutes:number;body_regions:BodyRegion[];perceived_exertion:number|null;notes:string|null}
export type ManualStrengthSessionUpdate=Partial<ManualStrengthSessionCreate>;
