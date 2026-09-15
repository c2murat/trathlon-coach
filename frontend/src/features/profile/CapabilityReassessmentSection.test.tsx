import {act, fireEvent, render, screen, cleanup} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {afterEach, describe, expect, it, vi} from "vitest";
import type {ApiClient} from "../../services/apiClient";
import {FetchApiClient} from "../../services/apiClient";
import {CapabilityReassessmentSection} from "./CapabilityReassessmentSection";
import type {CapabilityReassessmentResponse, ReassessmentStatus} from "./reassessmentTypes";
import {statusPresentation} from "./reassessmentPresentation";
import {PerformanceProfilePage} from "./PerformanceProfilePage";

afterEach(() => {cleanup(); vi.restoreAllMocks();});
function response(status: ReassessmentStatus = "REASSESSMENT_CANDIDATE", athlete = "a"): CapabilityReassessmentResponse {
  return {api_version: "0.8G.2C.8", algorithm_version: "0.8G.2C.7", athlete_profile_id: athlete,
    as_of_date: "2026-09-14", window_start_date: "2026-06-22",
    summary: {session_count: 3, candidate_count: 1, insufficient_count: 0, inconsistent_count: 0, unavailable_count: 0},
    candidates: [{capability_kind: "CYCLING_FTP", status, confidence: "MEDIUM",
      current_reference: status === "REFERENCE_UNAVAILABLE" ? null : {value: "200", unit: "watts", effective_from: "2026-01-01T00:00:00Z", source: "manual", quality: null},
      reason_codes: ["STRUCTURED_EVIDENCE_INSUFFICIENT"], evidence: {eligible_comparisons: 3, recent: 2, background: 1, contradicting: 0}}]};
}
const clientFor = (data: CapabilityReassessmentResponse) => ({capabilityReassessment: vi.fn().mockResolvedValue(data)} as unknown as ApiClient);
describe("Capability reassessment", () => {
  it.each(Object.keys(statusPresentation) as ReassessmentStatus[])("presents %s without raw codes", async status => {
    render(<CapabilityReassessmentSection client={clientFor(response(status))} athleteId="a" canEdit={false} onReview={vi.fn()}/>);
    expect(await screen.findByText(statusPresentation[status].label)).toBeInTheDocument();
    expect(screen.getByText("No hay suficientes sesiones estructuradas comparables.")).toBeInTheDocument();
    expect(screen.queryByText("STRUCTURED_EVIDENCE_INSUFFICIENT")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("Media")).toBeInTheDocument();
    expect(screen.queryByRole("button", {name: /Revisar referencia:/})).not.toBeInTheDocument();
  });
  it("formats all references and invokes only the manual editor", async () => {
    const data = response();
    data.candidates.push({...data.candidates[0], capability_kind: "RUNNING_THRESHOLD_PACE", current_reference: {...data.candidates[0].current_reference!, value: 250, unit: "seconds_per_km"}},
      {...data.candidates[0], capability_kind: "SWIMMING_CSS", current_reference: {...data.candidates[0].current_reference!, value: 110, unit: "seconds_per_100m"}});
    const review = vi.fn();
    render(<CapabilityReassessmentSection client={clientFor(data)} athleteId="a" canEdit onReview={review}/>);
    expect(await screen.findByText("200 W")).toBeInTheDocument();
    expect(screen.getByText("4:10 min/km")).toBeInTheDocument();
    expect(screen.getByText("1:50 min/100 m")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", {name: "Revisar referencia: Ciclismo / FTP"}));
    expect(review).toHaveBeenCalledOnce();
  });
  it.each([401, 403, 404, 500, 0])("distinguishes error %s from no evidence", async status => {
    const client = {capabilityReassessment: vi.fn().mockRejectedValue(new Error(status ? `API (${status}): secret traceback` : "network"))} as unknown as ApiClient;
    render(<CapabilityReassessmentSection client={client} athleteId="a" canEdit={false} onReview={vi.fn()}/>);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(status === 401 ? /sesión ha caducado/ : status === 403 ? /No tienes permiso/ : status === 404 ? /No se ha encontrado/ : status === 500 ? /servidor/ : /conectar/);
    expect(alert.textContent).not.toContain("traceback");
    expect(screen.queryByText("Aún no hay evidencia suficiente")).not.toBeInTheDocument();
  });
  it("clears old athlete immediately and ignores late responses", async () => {
    let finish!: (value: CapabilityReassessmentResponse) => void;
    const client = {capabilityReassessment: vi.fn().mockResolvedValueOnce(response()).mockImplementationOnce(() => new Promise(resolve => {finish = resolve;})).mockResolvedValueOnce(response("REFERENCE_UNAVAILABLE", "c"))} as unknown as ApiClient;
    const props = {client, canEdit: false, onReview: vi.fn()};
    const view = render(<CapabilityReassessmentSection {...props} athleteId="a"/>);
    await screen.findByText("200 W");
    view.rerender(<CapabilityReassessmentSection {...props} athleteId="b"/>);
    expect(screen.queryByText("200 W")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Cargando");
    view.rerender(<CapabilityReassessmentSection {...props} athleteId="c"/>);
    await screen.findByText("Referencia no disponible");
    await act(async () => {finish(response("REASSESSMENT_CANDIDATE", "b"));});
    expect(screen.queryByText("200 W")).not.toBeInTheDocument();
  });
  it("handles empty responses", async () => {
    const data = response(); data.candidates = [];
    render(<CapabilityReassessmentSection client={clientFor(data)} athleteId="a" canEdit={false} onReview={vi.fn()}/>);
    expect(await screen.findByText("No hay valoraciones de referencias disponibles.")).toBeInTheDocument();
  });
  it("opens the existing editor by keyboard without saving or suggesting a value", async () => {
    const client = {...clientFor(response()), performanceProfile: vi.fn().mockResolvedValue({profile: null, derived: {}}),
      performanceProfileHistory: vi.fn().mockResolvedValue([]), createPerformanceProfile: vi.fn()};
    render(<PerformanceProfilePage client={client} athleteId="a" canEdit/>);
    const review = await screen.findByRole("button", {name: "Revisar referencia: Ciclismo / FTP"});
    review.focus();
    await userEvent.keyboard("{Enter}");
    expect(screen.getByRole("heading", {name: "Crear nueva versión"})).toBeInTheDocument();
    expect(document.activeElement).toHaveClass("profile-editor");
    expect(screen.getByLabelText("FTP")).toHaveValue("");
    expect(client.createPerformanceProfile).not.toHaveBeenCalled();
  });
  it("shows an error if the transport does not support the advisory", async () => {
    render(<CapabilityReassessmentSection client={{} as ApiClient} athleteId="a" canEdit={false} onReview={vi.fn()}/>);
    expect(await screen.findByRole("alert")).toHaveTextContent("no está disponible");
  });
  it("rejects a mismatched response", async () => {
    render(<CapabilityReassessmentSection client={clientFor(response("REASSESSMENT_CANDIDATE", "other"))} athleteId="a" canEdit={false} onReview={vi.fn()}/>);
    await screen.findByRole("alert");
    expect(screen.queryByText("200 W")).not.toBeInTheDocument();
  });
  it("uses central GET, credentials, athlete scope and cutoff", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(response()), {status: 200, headers: {"Content-Type": "application/json"}}));
    const client = new FetchApiClient("http://api"); client.setActiveAthlete("a");
    await client.capabilityReassessment("2026-09-14");
    const [url, init] = fetch.mock.calls[0];
    expect(String(url)).toBe("http://api/athlete/performance-profile/reassessment?as_of_date=2026-09-14");
    expect(init?.credentials).toBe("include");
    expect(new Headers(init?.headers).get("X-TriCoach-Athlete-Id")).toBe("a");
    expect(init?.method ?? "GET").toBe("GET");
    expect(init?.body).toBeUndefined();
  });
});
