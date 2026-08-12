import {createContext,useCallback,useContext,useEffect,useMemo,useRef,useState,type ReactNode} from "react";
import {apiClient,FetchApiClient,type ApiClient} from "../services/apiClient";
import {athleteStorageKey,type AthleteCapability,type AthleteMembershipView,type CurrentUser} from "../types/sessionContext";
interface AthleteContextValue{
 user:CurrentUser|null;athletes:AthleteMembershipView[];activeAthlete:AthleteMembershipView|null;activeAthleteId:string|null;role:string|null;capabilities:readonly AthleteCapability[];loading:boolean;selectionRequired:boolean;error:string|null;announcement:string;
 selectAthlete(id:string):void;refreshContext(options?:{preferredAthleteId?:string}):Promise<boolean>;hasAthleteCapability(capability:AthleteCapability):boolean;
}
const AthleteContext=createContext<AthleteContextValue|null>(null);
function isAbortError(error:unknown){return error instanceof DOMException?error.name==="AbortError":error instanceof Error&&error.name==="AbortError"}
export function AthleteContextProvider({children,client=apiClient}:{children:ReactNode;client?:ApiClient}){
 const [user,setUser]=useState<CurrentUser|null>(null),[athletes,setAthletes]=useState<AthleteMembershipView[]>([]),[activeId,setActiveId]=useState<string|null>(null),[loading,setLoading]=useState(true),[required,setRequired]=useState(false),[error,setError]=useState<string|null>(null),[announcement,setAnnouncement]=useState("");
 const requestGeneration=useRef(0),mounted=useRef(false);
 const transport=client instanceof FetchApiClient?client:apiClient;
 const refreshContext=useCallback(async(options?:{preferredAthleteId?:string})=>{const generation=++requestGeneration.current;setLoading(true);setError(null);try{
  if(!client.sessionContext)throw new Error("session_context_unavailable");
  const context=await client.sessionContext();if(!mounted.current||generation!==requestGeneration.current)return false;
  setUser(context.user);setAthletes(context.athletes);
  const key=athleteStorageKey(context.user.id),preferred=options?.preferredAthleteId,preferredAthlete=context.athletes.find(x=>x.athlete_id===preferred),persisted=localStorage.getItem(key),valid=context.athletes.find(x=>x.athlete_id===persisted);
  if(persisted&&!valid)localStorage.removeItem(key);
  const next=preferredAthlete?.athlete_id??valid?.athlete_id??context.selected_athlete_id;
  if(preferredAthlete)localStorage.setItem(key,preferredAthlete.athlete_id);
  setActiveId(next);transport.setActiveAthlete(next);setRequired(!next&&context.selection_required);
  return preferred?Boolean(preferredAthlete):true;
 }catch(cause){if(!mounted.current||generation!==requestGeneration.current||isAbortError(cause))return false;setError("No se ha podido cargar el contexto de usuario.");transport.setActiveAthlete(null);return false}finally{if(mounted.current&&generation===requestGeneration.current)setLoading(false)}},[client,transport]);
 useEffect(()=>{mounted.current=true;void refreshContext();return()=>{mounted.current=false;requestGeneration.current++;transport.setActiveAthlete(null)}},[refreshContext,transport]);
 useEffect(()=>{transport.setAuthorizationErrorHandler(code=>{if(code==="athlete_not_authorized"&&user)localStorage.removeItem(athleteStorageKey(user.id));void refreshContext()});return()=>transport.setAuthorizationErrorHandler(null)},[transport,refreshContext,user]);
 const selectAthlete=useCallback((id:string)=>{const next=athletes.find(x=>x.athlete_id===id);if(!next||!user)return;setLoading(true);transport.setActiveAthlete(id);localStorage.setItem(athleteStorageKey(user.id),id);setActiveId(id);setRequired(false);setError(null);setAnnouncement(`Atleta cambiado a ${next.label}`);queueMicrotask(()=>setLoading(false))},[athletes,user,transport]);
 const active=athletes.find(x=>x.athlete_id===activeId)??null;
 const value=useMemo<AthleteContextValue>(()=>({user,athletes,activeAthlete:active,activeAthleteId:activeId,role:active?.role??null,capabilities:active?.capabilities??[],loading,selectionRequired:required,error,announcement,selectAthlete,refreshContext,hasAthleteCapability:c=>Boolean(active?.capabilities.includes(c))}),[user,athletes,active,activeId,loading,required,error,announcement,selectAthlete,refreshContext]);
 return <AthleteContext.Provider value={value}>{children}</AthleteContext.Provider>
}
export function useAthleteContext(){const value=useContext(AthleteContext);if(!value)throw new Error("AthleteContextProvider is required");return value}