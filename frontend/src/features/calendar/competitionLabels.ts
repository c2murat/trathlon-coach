import type {CompetitionCategory,CompetitionSegmentSport} from "../../types/planning";
export const categoryLabels:Record<CompetitionCategory,string>={triathlon:"Triatlón",duathlon:"Duatlón",aquathlon:"Acuatlón",running:"Carrera",cycling:"Ciclismo",swimming:"Natación"};
export const segmentLabels:Record<CompetitionSegmentSport,string>={swim:"Natación",bike:"Ciclismo",run:"Carrera"};
export function localDate(value:string){const [year,month,day]=value.split("-").map(Number);return new Date(year,month-1,day)}
export function dateLabel(value:string){return new Intl.DateTimeFormat("es-ES",{day:"numeric",month:"long",year:"numeric"}).format(localDate(value))}
