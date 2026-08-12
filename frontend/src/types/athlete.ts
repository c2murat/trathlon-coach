export type AthleteUnitSystem="metric"|"imperial";
export interface AthleteCreateRequest{display_name:string;timezone:string;unit_system:AthleteUnitSystem}
export interface AthleteCreateResponse{id:string;display_name:string;timezone:string;unit_system:AthleteUnitSystem;role:string;is_default:boolean;capabilities:string[]}
