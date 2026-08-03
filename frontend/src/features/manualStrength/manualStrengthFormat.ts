import type {BodyRegion,ManualStrengthTrainingLoad} from "../../types/manualStrength";
import {BODY_REGION_LABELS} from "./bodyRegions";
export const formatBodyRegion=(region:BodyRegion)=>BODY_REGION_LABELS[region];
export function formatBodyRegions(regions:BodyRegion[]){const labels=regions.map(x=>BODY_REGION_LABELS[x]);if(labels.length<2)return labels[0]??"";return `${labels.slice(0,-1).join(", ")} y ${labels.at(-1)!.toLocaleLowerCase("es-ES")}`;}
export const formatStrengthDuration=(minutes:number)=>`${minutes} min`;
export const formatRpe=(value:number|null)=>value===null?"No indicado":`${value}/10`;
export const formatStrengthLoad=(value:number)=>new Intl.NumberFormat("es-ES",{minimumFractionDigits:2,maximumFractionDigits:2}).format(value);
export const formatStrengthDate=(value:string)=>new Intl.DateTimeFormat("es-ES",{dateStyle:"long",timeStyle:"short"}).format(new Date(value));
export const formatStrengthQuality=(value:ManualStrengthTrainingLoad["quality"])=>value==="medium"?"Fiabilidad media":"Fiabilidad baja";
export const formatStrengthWarning=(warning:string)=>warning==="missing_perceived_exertion"?"Carga estimada solo mediante la duración.":warning;
