import type {CompetitionGoal,TrainingPlanSession} from "../../types/planning";
import {durationLabel,sessionLabel,sportLabel} from "./planningFormat";

export type CalendarItemKind="training"|"competition";
export type CalendarItemVariant="running"|"cycling"|"swimming"|"strength"|"competition"|"recovery"|"other";
export interface CalendarItem {id:string;date:string;kind:CalendarItemKind;sport:string;title:string;subtitle:string;status:string;durationSeconds:number|null;sourceId:string;priority?:"A"|"B"|"C";variant:CalendarItemVariant}

const variants:Record<string,CalendarItemVariant>={running:"running",run:"running",cycling:"cycling",bike:"cycling",swimming:"swimming",swim:"swimming",strength:"strength",competition:"competition",recovery:"recovery",mobility:"recovery"};
export const calendarVariant=(sport:string,kind:CalendarItemKind):CalendarItemVariant=>kind==="competition"?"competition":variants[sport]??"other";

export function calendarItems(goals:CompetitionGoal[],sessions:TrainingPlanSession[]):CalendarItem[]{
 const competitions=goals.map((goal):CalendarItem=>({id:`goal-${goal.id}`,date:goal.event_date,kind:"competition",sport:"competition",title:goal.name,subtitle:`Competición ${goal.priority}`,status:goal.status,durationSeconds:null,sourceId:goal.id,priority:goal.priority,variant:"competition"}));
 const training=sessions.map((session):CalendarItem=>({id:`training-${session.id}`,date:session.scheduled_date,kind:"training",sport:session.sport,title:sessionLabel(session.title),subtitle:`${sportLabel(session.sport)}${session.planned_duration_seconds!==null?` · ${durationLabel(session.planned_duration_seconds)}`:""}`,status:"planned",durationSeconds:session.planned_duration_seconds,sourceId:session.id,variant:calendarVariant(session.sport,"training")}));
 return [...competitions,...training].sort((a,b)=>a.date.localeCompare(b.date)||a.kind.localeCompare(b.kind)||a.title.localeCompare(b.title));
}
