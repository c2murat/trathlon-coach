export type ReassessmentStatus = "REASSESSMENT_CANDIDATE" | "NO_REASSESSMENT_NEEDED" | "INSUFFICIENT_EVIDENCE" | "INCONSISTENT_EVIDENCE" | "REFERENCE_UNAVAILABLE";
export type CapabilityKind = "CYCLING_FTP" | "RUNNING_THRESHOLD_PACE" | "SWIMMING_CSS";
export interface ReassessmentCandidate {
  capability_kind: CapabilityKind;
  status: ReassessmentStatus;
  confidence: "HIGH" | "MEDIUM" | "LOW" | "INSUFFICIENT";
  current_reference: {value: string | number; unit: string; effective_from: string | null; source: string | null; quality: string | null} | null;
  evidence: {eligible_comparisons: number; recent: number; background: number; contradicting: number};
  reason_codes: string[];
}
export interface CapabilityReassessmentResponse {
  api_version: string;
  athlete_profile_id: string;
  as_of_date: string;
  window_start_date: string;
  algorithm_version: string;
  candidates: ReassessmentCandidate[];
  summary: {session_count: number; candidate_count: number; insufficient_count: number; inconsistent_count: number; unavailable_count: number};
}
