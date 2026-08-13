export const ATHLETE_HEADER="X-TriCoach-Athlete-Id";
export const ATHLETE_CAPABILITIES={READ:"read_athlete_data",EDIT_PROFILE:"edit_athlete_profile",RECALCULATE:"recalculate_athlete_data",CREATE_STRENGTH:"create_manual_strength",UPDATE_STRENGTH:"update_manual_strength",DELETE_STRENGTH:"delete_manual_strength",CREATE_PROFILE:"create_performance_profile",CREATE_REFERENCE:"create_performance_reference",READ_STRAVA:"read_strava_integration",MANAGE_STRAVA:"manage_strava_connection",IMPORT_STRAVA:"run_strava_import",ENRICH_STRAVA:"run_strava_enrichment",EVIDENCE_STRAVA:"run_strava_evidence",DELETE_LOCATION:"delete_strava_location_evidence"} as const;
export type AthleteCapability=typeof ATHLETE_CAPABILITIES[keyof typeof ATHLETE_CAPABILITIES];
export interface CurrentUser{id:string;display_name:string;email:string|null}
export type AthleteRole="owner"|"athlete"|"editor"|"coach"|"viewer";
export interface AthleteMembershipView{athlete_id:string;label:string;role:AthleteRole;is_default:boolean;capabilities:AthleteCapability[]}
export interface SessionContext{user:CurrentUser;athletes:AthleteMembershipView[];selected_athlete_id:string|null;selection_required:boolean}
export const athleteStorageKey=(id:string)=>`tricoach.activeAthlete.${id}`;
export const roleLabel=(role:string)=>({owner:"Propietario",athlete:"Deportista",editor:"Editor",coach:"Entrenador",viewer:"Solo lectura"}[role]??"Acceso limitado");
