import type {
  ActivityPage,
  ActivityDetail,
  ActivityFilterOptions,
  DashboardSummary,
  WeeklyTrend,
  Consistency,
  HealthResponse,
  ImportStart,
  ImportStatus,
  EnrichmentStart,
  EnrichmentStatus,
  ActivityEvidence,
  ActivityMetrics,
  EvidenceStart,
  EvidenceJob,
  StravaStatus
} from "../types/api";
import type { DailyTrainingLoadAggregate, WeeklyTrainingLoadAggregate, TrainingLoadDateRange } from "../types/trainingLoad";
import type {ManualStrengthSession,ManualStrengthSessionCreate,ManualStrengthSessionUpdate,ManualStrengthTrainingLoad} from "../types/manualStrength";
import type {DailyTrainingStatus,LatestTrainingStatusQuery,TrainingStatusQuery} from "../types/trainingStatus";
import {ATHLETE_HEADER,type SessionContext} from "../types/sessionContext";
import type {AuthenticatedUser,LoginCredentials,RegistrationInput} from "../types/auth";
import type {Account,AccountUpdateRequest,PasswordChangeRequest} from "../features/account/accountTypes";
import type {AthleteCreateRequest,AthleteCreateResponse} from "../types/athlete";
import type {AthleteProfile,AthleteProfileUpdateRequest} from "../features/athleteProfile/athleteProfileTypes";
import type {CompetitionGoal,CompetitionGoalCreate,CompetitionGoalUpdate} from "../types/planning";

export const CSRF_COOKIE_NAME="tricoach_csrf";
export const CSRF_HEADER_NAME="X-CSRF-Token";
const UNSAFE_METHODS=new Set(["POST","PUT","PATCH","DELETE"]);
export function readCookie(name:string,source=typeof document==="undefined"?"":document.cookie){
 const prefix=encodeURIComponent(name)+"=";
 const part=source.split(";").map(value=>value.trim()).find(value=>value.startsWith(prefix));
 return part?decodeURIComponent(part.slice(prefix.length)):null;
}

const configuredBaseUrl =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export interface CoachAssignment {membership_id:string;coach_user_id:string;coach_display_name:string;coach_email:string;athlete_profile_id:string;athlete_display_name:string;is_active:boolean;is_default:boolean}
export interface CoachAssignmentCandidates {coaches:{user_id:string;display_name:string;email:string}[];athletes:{athlete_profile_id:string;display_name:string}[]}
export interface ApiClient {
  authMe(): Promise<AuthenticatedUser>;
  login(credentials: LoginCredentials): Promise<AuthenticatedUser>;
  register?(input:RegistrationInput):Promise<AuthenticatedUser>;
  logout(): Promise<void>;
  getAccount?():Promise<Account>;
  updateAccount?(input:AccountUpdateRequest):Promise<Account>;
  changePassword?(input:PasswordChangeRequest):Promise<void>;
  sessionContext?():Promise<SessionContext>;
  createAthlete?(input:AthleteCreateRequest):Promise<AthleteCreateResponse>;
  coachAssignmentCandidates?():Promise<CoachAssignmentCandidates>;
  coachAssignments?():Promise<CoachAssignment[]>;
  createCoachAssignment?(input:{coach_user_id:string;athlete_profile_id:string}):Promise<CoachAssignment>;
  revokeCoachAssignment?(membershipId:string):Promise<CoachAssignment>;
  competitionGoals?():Promise<CompetitionGoal[]>;
  createCompetitionGoal?(input:CompetitionGoalCreate):Promise<CompetitionGoal>;
  updateCompetitionGoal?(id:string,input:CompetitionGoalUpdate):Promise<CompetitionGoal>;
  deleteCompetitionGoal?(id:string):Promise<void>;
  getAthleteProfile?():Promise<AthleteProfile>;
  updateAthleteProfile?(input:AthleteProfileUpdateRequest):Promise<AthleteProfile>;
  health(): Promise<HealthResponse>;
  stravaStatus(): Promise<StravaStatus>;
  activities(): Promise<ActivityPage>;
  browseActivities(query: string): Promise<ActivityPage>;
  activityDetail(id: string): Promise<ActivityDetail>;
  activityFilterOptions(): Promise<ActivityFilterOptions>;
  trainingLoad?(activityId:string,algorithmVersion?:string):Promise<import("../types/api").TrainingLoadResponse>;
  recalculateTrainingLoad?(activityId:string):Promise<import("../types/api").TrainingLoadResponse>;
  startEnrichment?(activityIds:string[],limit?:number):Promise<EnrichmentStart>;
  enrichmentStatus?(jobId:string):Promise<EnrichmentStatus>;
  activityEvidence?(activityId:string):Promise<ActivityEvidence>;
  activityMetrics?(activityId:string):Promise<ActivityMetrics>;
  recalculateMetrics?(activityId:string):Promise<ActivityMetrics>;
  startEvidence?(activityIds:string[],includeLocation:boolean):Promise<EvidenceStart>;
  evidenceStatus?(jobId:string):Promise<EvidenceJob>;
  latestImport(): Promise<ImportStatus>;
  startImport(): Promise<ImportStart>;
  importStatus(jobId: string): Promise<ImportStatus>;
  dashboardSummary(): Promise<DashboardSummary>;
  dashboardTrends(): Promise<WeeklyTrend[]>;
  dashboardConsistency(): Promise<Consistency>;
  startStravaConnection():Promise<{authorization_url:string}>;
  disconnectStrava():Promise<{provider:"strava";status:string}>;
  performanceProfile?():Promise<{profile:any|null;derived:Record<string,number>}>;
  performanceProfileHistory?():Promise<any[]>;
  createPerformanceProfile?(input:Record<string,unknown>):Promise<any>;
  performanceReferences?(query?:string):Promise<import("../types/api").PerformanceReference[]>;
  performanceReferenceHistory?(query?:string):Promise<import("../types/api").PerformanceReference[]>;
  createPerformanceReference?(input:Record<string,unknown>):Promise<import("../types/api").PerformanceReference>;
  performanceReference?(id:string):Promise<import("../types/api").PerformanceReference>;
  performanceZones?(query?:string):Promise<any[]>;
  getDailyTrainingLoad?(range: TrainingLoadDateRange): Promise<DailyTrainingLoadAggregate[]>;
  getWeeklyTrainingLoad?(range: TrainingLoadDateRange): Promise<WeeklyTrainingLoadAggregate[]>;
  listManualStrengthSessions?():Promise<ManualStrengthSession[]>;
  createManualStrengthSession?(input:ManualStrengthSessionCreate):Promise<ManualStrengthSession>;
  updateManualStrengthSession?(id:string,input:ManualStrengthSessionUpdate):Promise<ManualStrengthSession>;
  deleteManualStrengthSession?(id:string):Promise<void>;
  recalculateManualStrengthLoad?(id:string):Promise<ManualStrengthTrainingLoad>;
  listTrainingStatus?(query:TrainingStatusQuery):Promise<DailyTrainingStatus[]>;
  getLatestTrainingStatus?(query:LatestTrainingStatusQuery):Promise<DailyTrainingStatus|null>;
  recalculateTrainingStatus?(query:TrainingStatusQuery):Promise<DailyTrainingStatus[]>;
}

export class FetchApiClient implements ApiClient {
  private readonly baseUrl: string;
  private activeAthleteId:string|null=null;
  private generation=0;
  private controllers=new Set<AbortController>();
  private authorizationHandler:((code:string)=>void)|null=null;

  constructor(baseUrl = configuredBaseUrl) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }
  setActiveAthlete(athleteId:string|null){if(this.activeAthleteId===athleteId)return;this.activeAthleteId=athleteId;this.generation++;for(const controller of this.controllers)controller.abort();this.controllers.clear()}
  setAuthorizationErrorHandler(handler:((code:string)=>void)|null){this.authorizationHandler=handler}
  authMe(){return this.request<AuthenticatedUser>("/auth/me",undefined,true)}
  login(credentials:LoginCredentials){return this.request<AuthenticatedUser>("/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(credentials)},true)}
  register(input:RegistrationInput){return this.request<AuthenticatedUser>("/auth/register",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(input)},true)}
  logout(){return this.request<void>("/auth/logout",{method:"POST"},true)}
  sessionContext(){return this.request<SessionContext>("/session/context",undefined,true)}
  createAthlete(input:AthleteCreateRequest){return this.request<AthleteCreateResponse>("/athletes",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(input)},true)}
  coachAssignmentCandidates(){return this.request<CoachAssignmentCandidates>("/coach-assignments/candidates",undefined,true)}
  coachAssignments(){return this.request<CoachAssignment[]>("/coach-assignments",undefined,true)}
  createCoachAssignment(input:{coach_user_id:string;athlete_profile_id:string}){return this.request<CoachAssignment>("/coach-assignments",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(input)},true)}
  revokeCoachAssignment(id:string){const membershipId=id?.trim();if(!membershipId)return Promise.reject(new Error("invalid_membership_id"));return this.request<CoachAssignment>(`/coach-assignments/${encodeURIComponent(membershipId)}`,{method:"DELETE"},true)}
  competitionGoals(){return this.request<CompetitionGoal[]>("/competition-goals")}
  createCompetitionGoal(input:CompetitionGoalCreate){return this.request<CompetitionGoal>("/competition-goals",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(input)})}
  updateCompetitionGoal(id:string,input:CompetitionGoalUpdate){return this.request<CompetitionGoal>(`/competition-goals/${encodeURIComponent(id)}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(input)})}
  deleteCompetitionGoal(id:string){return this.request<void>(`/competition-goals/${encodeURIComponent(id)}`,{method:"DELETE"})}
  getAthleteProfile(){return this.request<AthleteProfile>("/athlete/profile")}
  updateAthleteProfile(input:AthleteProfileUpdateRequest){return this.request<AthleteProfile>("/athlete/profile",{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(input)})}
  getAccount(){return this.request<Account>("/account",undefined,true)}
  updateAccount(input:AccountUpdateRequest){return this.request<Account>("/account",{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(input)},true)}
  changePassword(input:PasswordChangeRequest){return this.request<void>("/account/password",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(input)},true)}

  health() {
    return this.request<HealthResponse>("/health");
  }

  stravaStatus() {
    return this.request<StravaStatus>("/integrations/strava/status");
  }

  activities() {
    return this.request<ActivityPage>("/activities?limit=10&offset=0");
  }

  browseActivities(query: string) { return this.request<ActivityPage>("/activities" + (query ? "?" + query : "")); }

  activityDetail(id: string) { return this.request<ActivityDetail>("/activities/" + encodeURIComponent(id)); }

  activityFilterOptions() { return this.request<ActivityFilterOptions>("/activities/filter-options"); }
  trainingLoad(activityId:string,algorithmVersion="0.7b.1"){return this.request<import("../types/api").TrainingLoadResponse>(`/activities/${encodeURIComponent(activityId)}/training-load?algorithm_version=${encodeURIComponent(algorithmVersion)}`)}
  recalculateTrainingLoad(activityId:string){return this.request<import("../types/api").TrainingLoadResponse>(`/activities/${encodeURIComponent(activityId)}/training-load/recalculate`,{method:"POST"})}

  startEnrichment(activityIds:string[],limit=activityIds.length) { return this.request<EnrichmentStart>("/integrations/strava/enrichments", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({activity_ids:activityIds,limit}) }); }

  enrichmentStatus(jobId:string) { return this.request<EnrichmentStatus>("/integrations/strava/enrichments/" + encodeURIComponent(jobId)); }

  activityMetrics(activityId:string) { return this.request<ActivityMetrics>("/activities/" + encodeURIComponent(activityId) + "/metrics"); }

  recalculateMetrics(activityId:string) { return this.request<ActivityMetrics>("/activities/" + encodeURIComponent(activityId) + "/metrics/recalculate", {method:"POST"}); }

  activityEvidence(activityId:string) { return this.request<ActivityEvidence>("/activities/" + encodeURIComponent(activityId) + "/evidence"); }

  startEvidence(activityIds:string[],includeLocation:boolean) { return this.request<EvidenceStart>("/integrations/strava/evidence", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({activity_ids:activityIds,include_laps:true,include_streams:true,include_location:includeLocation})}); }

  evidenceStatus(jobId:string) { return this.request<EvidenceJob>("/integrations/strava/evidence/" + encodeURIComponent(jobId)); }

  latestImport() {
    return this.request<ImportStatus>("/integrations/strava/imports/latest");
  }

  startImport() {
    return this.request<ImportStart>("/integrations/strava/imports", {
      method: "POST",
    });
  }

  importStatus(jobId: string) {
    return this.request<ImportStatus>(
      `/integrations/strava/imports/` + encodeURIComponent(jobId),
    );
  }

  dashboardSummary() { return this.request<DashboardSummary>("/dashboard/summary?period=week"); }

  dashboardTrends() { return this.request<WeeklyTrend[]>("/dashboard/trends?weeks=8"); }

  dashboardConsistency() { return this.request<Consistency>("/dashboard/consistency?weeks=12"); }

  performanceProfile(){return this.request<any>("/athlete/performance-profile")}
  performanceProfileHistory(){return this.request<any[]>("/athlete/performance-profile/history")} 
  createPerformanceProfile?(input:Record<string,unknown>){return this.request<any>("/athlete/performance-profile/versions",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(input)})}

  performanceReferences(query=""){return this.request<any[]>("/athlete/performance-references"+(query?"?"+query:""))}
  performanceReferenceHistory(query=""){return this.request<any[]>("/athlete/performance-references/history"+(query?"?"+query:""))}
  createPerformanceReference(input:Record<string,unknown>){return this.request<any>("/athlete/performance-references",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(input)})}
  performanceReference(id:string){return this.request<any>("/athlete/performance-references/"+encodeURIComponent(id))}

  performanceZones(query=""){return this.request<any[]>("/athlete/performance-zones"+(query?"?"+query:""))}

  getDailyTrainingLoad(range: TrainingLoadDateRange) { return this.request<unknown[]>("/training-load/daily?" + new URLSearchParams({start_date:range.startDate,end_date:range.endDate,timezone_name:range.timezoneName}).toString()).then(this.requireArray<DailyTrainingLoadAggregate>); }
  getWeeklyTrainingLoad(range: TrainingLoadDateRange) { return this.request<unknown[]>("/training-load/weekly?" + new URLSearchParams({start_date:range.startDate,end_date:range.endDate,timezone_name:range.timezoneName}).toString()).then(this.requireArray<WeeklyTrainingLoadAggregate>); }
  listManualStrengthSessions(){return this.request<ManualStrengthSession[]>("/manual-strength-sessions?limit=100&offset=0")}
  createManualStrengthSession(input:ManualStrengthSessionCreate){return this.request<ManualStrengthSession>("/manual-strength-sessions",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(input)})}
  updateManualStrengthSession(id:string,input:ManualStrengthSessionUpdate){return this.request<ManualStrengthSession>(`/manual-strength-sessions/${encodeURIComponent(id)}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(input)})}
  deleteManualStrengthSession(id:string){return this.request<void>(`/manual-strength-sessions/${encodeURIComponent(id)}`,{method:"DELETE"})}
  recalculateManualStrengthLoad(id:string){return this.request<ManualStrengthTrainingLoad>(`/manual-strength-sessions/${encodeURIComponent(id)}/training-load/recalculate`,{method:"POST"})}
  listTrainingStatus(query:TrainingStatusQuery){return this.request<DailyTrainingStatus[]>("/training-status?"+this.trainingStatusParams(query))}
  async getLatestTrainingStatus(query:LatestTrainingStatusQuery){try{return await this.request<DailyTrainingStatus>("/training-status/latest?"+this.trainingStatusParams(query))}catch(error){if(error instanceof Error&&error.message.includes("(404)")&&error.message.includes("training_status_not_found"))return null;throw error}}
  recalculateTrainingStatus(query:TrainingStatusQuery){return this.request<DailyTrainingStatus[]>("/training-status/recalculate?"+this.trainingStatusParams(query),{method:"POST"})}

  startStravaConnection(){return this.request<{authorization_url:string}>("/integrations/strava/connect/start",{method:"POST"})}
  disconnectStrava(){return this.request<{provider:"strava";status:string}>("/integrations/strava/disconnect",{method:"DELETE"})}

  private requireArray<T>(value: unknown[]): T[] { if (!Array.isArray(value)) throw new Error("Invalid training load response"); return value as T[]; }
  private trainingStatusParams(query:TrainingStatusQuery|LatestTrainingStatusQuery){const values:Record<string,string>={timezone_name:query.timezoneName,training_load_algorithm_version:query.trainingLoadAlgorithmVersion??"0.7b.1",manual_strength_algorithm_version:query.manualStrengthAlgorithmVersion??"0.7e.1",training_status_algorithm_version:query.trainingStatusAlgorithmVersion??"0.7f.1"};if("startDate" in query){values.start_date=query.startDate;values.end_date=query.endDate}return new URLSearchParams(values).toString()}

  private async request<T>(path: string, init?: RequestInit, withoutAthlete=false): Promise<T> {
    const headers = new Headers(init?.headers);
    headers.set("Accept", "application/json");
    const method=(init?.method??"GET").toUpperCase();
    if(UNSAFE_METHODS.has(method)&&path!=="/auth/login"&&path!=="/auth/register"){const csrfToken=readCookie(CSRF_COOKIE_NAME);if(csrfToken)headers.set(CSRF_HEADER_NAME,csrfToken)}
    if(!withoutAthlete&&path!=="/health"){
      if(!this.activeAthleteId)throw new Error("athlete_selection_required");
      headers.set(ATHLETE_HEADER,this.activeAthleteId);
    }
    const controller=new AbortController(),generation=this.generation;
    this.controllers.add(controller);
    init?.signal?.addEventListener("abort",()=>controller.abort(),{once:true});
    let response:Response;
    try{response=await fetch(this.baseUrl+path,{...init,headers,credentials:"include",signal:controller.signal})}
    finally{this.controllers.delete(controller)}
    if(generation!==this.generation)throw new DOMException("Stale athlete response","AbortError");
    if (!response.ok) {
      let detail = "",code="";
      try { const body = await response.json();const payload=body.detail??body;code=typeof payload==="object"&&payload&&typeof payload.code==="string"?payload.code:"";detail=typeof payload==="string"?payload:JSON.stringify(payload); } catch { detail = response.statusText; }
      if(response.status===403&&(code==="athlete_not_authorized"||code==="athlete_permission_denied"))this.authorizationHandler?.(code);
      throw new Error(`TriCoach API request failed (${response.status}): ${detail}`);
    }
    if(response.status===204)return undefined as T;
    return (await response.json()) as T;
  }
}

export const apiClient = new FetchApiClient();










