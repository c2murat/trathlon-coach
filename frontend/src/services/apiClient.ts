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
  StravaStatus,
} from "../types/api";

const configuredBaseUrl =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export interface ApiClient {
  health(): Promise<HealthResponse>;
  stravaStatus(): Promise<StravaStatus>;
  activities(): Promise<ActivityPage>;
  browseActivities(query: string): Promise<ActivityPage>;
  activityDetail(id: string): Promise<ActivityDetail>;
  activityFilterOptions(): Promise<ActivityFilterOptions>;
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
  connectUrl(): string;
  performanceProfile?():Promise<{profile:any|null;derived:Record<string,number>}>;
  performanceProfileHistory?():Promise<any[]>;
  createPerformanceProfile?(input:Record<string,unknown>):Promise<any>;
  performanceReferences?(query?:string):Promise<import("../types/api").PerformanceReference[]>;
  performanceReferenceHistory?(query?:string):Promise<import("../types/api").PerformanceReference[]>;
  createPerformanceReference?(input:Record<string,unknown>):Promise<import("../types/api").PerformanceReference>;
  performanceReference?(id:string):Promise<import("../types/api").PerformanceReference>;
  performanceZones?(query?:string):Promise<any[]>;
}

export class FetchApiClient implements ApiClient {
  private readonly baseUrl: string;

  constructor(baseUrl = configuredBaseUrl) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

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

  connectUrl() {
    return this.baseUrl + "/integrations/strava/connect";
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const headers = new Headers(init?.headers);
    headers.set("Accept", "application/json");
    const response = await fetch(this.baseUrl + path, {
      ...init,
      headers,
    });
    if (!response.ok) {
      let detail = "";
      try { const body = await response.json(); detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body); } catch { detail = response.statusText; }
      throw new Error(`TriCoach API request failed (${response.status}): ${detail}`);
    }
    return (await response.json()) as T;
  }
}

export const apiClient = new FetchApiClient();






