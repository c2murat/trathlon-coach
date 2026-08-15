import {render,screen,waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {describe,expect,it,vi} from "vitest";
import type {ApiClient} from "../../services/apiClient";
import type {StravaStatus} from "../../types/api";
import {StravaConnectionPanel} from "./ConnectionsPage";

const state=(connected:boolean,message=connected?"Conexión activa.":"Sin conexión."):StravaStatus=>({provider:"strava",connection_status:connected?"connected":"not_connected",connected,external_athlete_id:connected?"external":null,granted_scopes:[],connected_at:connected?"2026-08-01T10:00:00Z":null,updated_at:null,token_expires_at:null,requires_reconnect:false,last_sync_at:connected?"2026-08-10T10:00:00Z":null,message});
const client=(overrides:Partial<ApiClient>={}):ApiClient=>({stravaStatus:vi.fn().mockResolvedValue(state(false)),startStravaConnection:vi.fn().mockResolvedValue({authorization_url:"https://www.strava.com/oauth/authorize?state=opaque"}),disconnectStrava:vi.fn().mockResolvedValue({provider:"strava",status:"disconnected"}),latestImport:vi.fn().mockResolvedValue({job_id:null,status:"not_started"}),startImport:vi.fn(),importStatus:vi.fn(),...overrides} as ApiClient);

describe("StravaConnectionPanel athlete scope",()=>{
 it("shows independent connected and disconnected states in both A/B directions without stale content",async()=>{const c=client({stravaStatus:vi.fn().mockResolvedValueOnce(state(true)).mockResolvedValueOnce(state(false)).mockResolvedValueOnce(state(true))});const view=render(<StravaConnectionPanel client={c} athleteId="carlos" athleteName="Carlos Murat" canManage/>);expect(await screen.findByText("Conectado")).toBeInTheDocument();view.rerender(<StravaConnectionPanel client={c} athleteId="jenny" athleteName="Jenny Ruiz" canManage/>);expect(screen.getByText(/Cargando el estado de Strava para Jenny Ruiz/)).toBeInTheDocument();expect(screen.queryByText("Conectado")).not.toBeInTheDocument();expect(await screen.findByText("Sin conectar")).toBeInTheDocument();expect(screen.queryByRole("button",{name:"Sincronizar actividades"})).not.toBeInTheDocument();view.rerender(<StravaConnectionPanel client={c} athleteId="carlos" athleteName="Carlos Murat" canManage/>);expect(await screen.findByText("Conectado")).toBeInTheDocument()});
 it("does not let a late Carlos response overwrite Jenny",async()=>{let release!:(value:StravaStatus)=>void;const slow=new Promise<StravaStatus>(resolve=>{release=resolve}),c=client({stravaStatus:vi.fn().mockReturnValueOnce(slow).mockResolvedValueOnce(state(false))});const view=render(<StravaConnectionPanel client={c} athleteId="carlos" athleteName="Carlos Murat"/>);view.rerender(<StravaConnectionPanel client={c} athleteId="jenny" athleteName="Jenny Ruiz"/>);expect(await screen.findByText("Sin conectar")).toBeInTheDocument();release(state(true));await Promise.resolve();expect(screen.queryByText("Conectado")).not.toBeInTheDocument();expect(screen.getByRole("heading",{name:"Jenny Ruiz"})).toBeInTheDocument()});
 it("starts one contextual OAuth request on double click",async()=>{let release!:(value:{authorization_url:string})=>void;const pending=new Promise<{authorization_url:string}>(resolve=>{release=resolve}),c=client({startStravaConnection:vi.fn().mockReturnValue(pending)}),navigate=vi.fn();render(<StravaConnectionPanel client={c} athleteId="jenny" athleteName="Jenny Ruiz" canManage onExternalNavigate={navigate}/>);const button=await screen.findByRole("button",{name:"Conectar Strava para Jenny Ruiz"});await userEvent.dblClick(button);expect(c.startStravaConnection).toHaveBeenCalledTimes(1);release({authorization_url:"https://www.strava.com/oauth/authorize?state=opaque"});await waitFor(()=>expect(navigate).toHaveBeenCalledTimes(1))});
 it("keeps status visible but hides management without capability",async()=>{render(<StravaConnectionPanel client={client({stravaStatus:vi.fn().mockResolvedValue(state(true))})} athleteId="carlos" athleteName="Carlos Murat"/>);expect(await screen.findByText("Conectado")).toBeInTheDocument();expect(screen.getByText(/no gestionarla/)).toBeInTheDocument();expect(screen.queryByRole("button",{name:/Desconectar/})).not.toBeInTheDocument()});
 it("reports a status load failure instead of claiming disconnected",async()=>{const c=client({stravaStatus:vi.fn().mockRejectedValue(new Error("network"))});render(<StravaConnectionPanel client={c} athleteId="jenny" athleteName="Jenny Ruiz"/>);expect(await screen.findByRole("alert")).toHaveTextContent("No se ha podido cargar el estado de Strava.");expect(screen.queryByText("Sin conectar")).not.toBeInTheDocument()});
});
describe("Strava operation capabilities",()=>{
 it("lets a coach sync and disconnect without showing connect or reconnect",async()=>{
  render(<StravaConnectionPanel client={client({stravaStatus:vi.fn().mockResolvedValue(state(true))})} athleteId="athlete-a" athleteName="Atleta A" canDisconnect canSync/>);
  expect(await screen.findByText("Conectado")).toBeInTheDocument();
  expect(screen.getByRole("button",{name:"Sincronizar actividades"})).toBeVisible();
  expect(screen.getByRole("button",{name:"Desconectar Strava"})).toBeVisible();
  expect(screen.queryByRole("button",{name:/Conectar Strava para/})).not.toBeInTheDocument();
 });
 it("does not show reconnect when connect capability is absent",async()=>{
  render(<StravaConnectionPanel client={client({stravaStatus:vi.fn().mockResolvedValue({...state(false),requires_reconnect:true})})} athleteId="athlete-a" athleteName="Atleta A" canDisconnect canSync/>);
  expect(await screen.findByText("Requiere reconexión")).toBeInTheDocument();
  expect(screen.queryByRole("button",{name:/Reconectar Strava/})).not.toBeInTheDocument();
 });
});