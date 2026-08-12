export type UnitSystem="metric"|"imperial";
export type AthleteProfileField="birth_year"|"sex_for_training_context"|"height_m"|"weight_kg";
export interface AthleteProfileCompleteness{status:"minimal"|"contextual";missing_recommended_fields:AthleteProfileField[]}
export interface AthleteProfile{id:string;display_name:string;timezone:string;unit_system:UnitSystem;birth_year:number|null;sex_for_training_context:string|null;height_m:number|null;weight_kg:number|null;updated_at:string;completeness:AthleteProfileCompleteness}
export type AthleteProfileUpdateRequest=Partial<Pick<AthleteProfile,"display_name"|"timezone"|"unit_system"|"birth_year"|"sex_for_training_context"|"height_m"|"weight_kg">>;
