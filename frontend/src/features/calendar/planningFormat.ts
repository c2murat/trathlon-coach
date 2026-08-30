const sports:Record<string,string>={running:"Carrera",run:"Carrera",cycling:"Ciclismo",bike:"Ciclismo",swimming:"Natación",swim:"Natación",strength:"Fuerza",competition:"Competición"};
const sessions:Record<string,string>={RUN_EASY:"Carrera suave",RUN_LONG:"Tirada larga",RUN_TEMPO:"Carrera tempo",RUN_THRESHOLD:"Carrera a umbral",RUN_INTERVAL:"Intervalos de carrera",RUN_RECOVERY:"Carrera de recuperación",BIKE_EASY:"Bici suave",BIKE_ENDURANCE:"Bici de resistencia",BIKE_LONG:"Salida larga en bici",BIKE_TEMPO:"Bici tempo",BIKE_THRESHOLD:"Bici a umbral",BIKE_INTERVAL:"Intervalos en bici",BIKE_RECOVERY:"Bici de recuperación",SWIM_TECHNIQUE:"Técnica de natación",SWIM_EASY:"Natación suave",SWIM_AEROBIC:"Natación aeróbica",SWIM_THRESHOLD:"Natación a umbral",SWIM_INTERVAL:"Series de natación",SWIM_ENDURANCE:"Natación de resistencia",GENERAL_STRENGTH:"Fuerza general",COMPETITION:"Competición",EASY:"Suave",RECOVERY:"Recuperación",ENDURANCE:"Resistencia",TEMPO:"Tempo",THRESHOLD:"Umbral",VO2:"VO₂ máx.",LONG:"Sesión larga",BRICK:"Transición",STRENGTH:"Fuerza",REST:"Descanso"};
const purposes:Record<string,string>={AEROBIC_BASE:"Base aeróbica",ENDURANCE:"Resistencia",LONG_ENDURANCE:"Resistencia larga",TECHNIQUE:"Técnica",TEMPO_DEVELOPMENT:"Desarrollo de tempo",THRESHOLD_DEVELOPMENT:"Desarrollo del umbral",HIGH_INTENSITY:"Alta intensidad",RECOVERY:"Recuperación",GENERAL_STRENGTH:"Fuerza general",COMPETITION:"Competición"};
const intensities:Record<string,string>={EASY:"Suave",MODERATE:"Moderada",HARD:"Alta",EVENT:"Competición"};
export const sportLabel=(value:string)=>sports[value]??value;
export const sessionLabel=(value:string)=>sessions[value]??value.replaceAll("_"," ").toLocaleLowerCase("es-ES");
export const purposeLabel=(value:string)=>purposes[value]??value.replaceAll("_"," ").toLocaleLowerCase("es-ES");
export const intensityLabel=(value:string)=>intensities[value]??value;
const warningLabels:Record<string,(context:Record<string,unknown>)=>string>={
 DISCIPLINE_UNDERREPRESENTED:context=>`La disciplina de ${sportLabel(String(context.discipline??"")).toLocaleLowerCase("es-ES")} está subrepresentada esta semana.`,
 KEY_SESSION_SPACING_CONSTRAINT:()=>"No se pudo mantener la separación preferida entre sesiones clave.",
 SESSION_PLACEMENT_CONSTRAINT:()=>"No se pudo ubicar una sesión compatible con la disponibilidad.",
 WEEKLY_LOAD_BUDGET_UNDERSHOT:()=>"La carga planificada queda por debajo del objetivo semanal.",
 WEEKLY_LOAD_BUDGET_OVERSHOT:()=>"La carga planificada supera el objetivo semanal.",
 WEEKLY_SESSION_LIMIT_REACHED:()=>"Se ha alcanzado el límite semanal de sesiones.",
 PREFERRED_REST_DAY_UNAVAILABLE:()=>"No se pudo mantener libre el día de descanso preferido.",
 PREFERRED_LONG_DAY_UNAVAILABLE:context=>`No se pudo ubicar la sesión larga de ${sportLabel(String(context.discipline??"")).toLocaleLowerCase("es-ES")} en el día preferido.`,
 LONG_SESSION_HISTORY_INSUFFICIENT:context=>`La progresión de la sesión larga de ${sportLabel(String(context.discipline??"")).toLocaleLowerCase("es-ES")} usa una referencia conservadora por falta de historial.`,
 SESSION_LOAD_TARGET_UNAVAILABLE:()=>"No hay datos suficientes para estimar la carga de las sesiones.",
};
export const warningLabel=(code:string,context:Record<string,unknown>={})=>warningLabels[code]?.(context)??"Hay una condición de planificación que requiere revisión.";
export const goalRoleLabel=(role:string|null|undefined)=>({primary:"Principal",supporting:"Secundario",training:"Entrenamiento"}[role??""]??"Sin clasificar");
export const durationLabel=(seconds:number)=>seconds>=3600?`${Math.floor(seconds/3600)} h ${Math.round(seconds%3600/60)} min`:`${Math.round(seconds/60)} min`;
export const minutesLabel=(minutes:number)=>durationLabel(minutes*60);
export const paceLabel=(seconds:number,unit="/km")=>`${Math.floor(seconds/60)}:${String(Math.round(seconds%60)).padStart(2,"0")} ${unit}`;
const percentage=(value:number)=>`${Math.round(value*100)}`;
const decimal=(value:number)=>value.toLocaleString("es-ES",{maximumFractionDigits:3});
const paceRange=(lower:number,upper:number)=>`${formatPace(lower).replace(" min/km","")}–${formatPace(upper)}`;
const swimRange=(lower:number,upper:number)=>`${formatSwimPace(lower).replace(" min/100 m","")}–${formatSwimPace(upper).replace("min/100 m","/100 m")}`;
const referenceNames:Record<string,string>={FTP:"FTP",threshold_hr:"umbral de frecuencia cardiaca",threshold_pace:"ritmo umbral",CSS:"CSS"};
export function workoutTargetLabel(target?:WorkoutTarget):string{
 if(!target||target.metric==="none")return "Libre";
 const hasResolved=[target.reference_value,target.resolved_minimum,target.resolved_maximum].every(value=>typeof value==="number"&&Number.isFinite(value));
 const minimum=Number(target.minimum??0),maximum=Number(target.maximum??0),reference=referenceNames[target.reference??""]??"referencia";
 if(target.mode==="percent_reference"&&hasResolved){
  const resolvedMinimum=Number(target.resolved_minimum),resolvedMaximum=Number(target.resolved_maximum),referenceValue=Number(target.reference_value);
  if(target.metric==="power"&&target.resolved_unit==="watts")return `Potencia ${Math.round(resolvedMinimum)}–${Math.round(resolvedMaximum)} W · ${percentage(minimum)}–${percentage(maximum)} % FTP · FTP: ${Math.round(referenceValue)} W`;
  if(target.metric==="pace"&&target.resolved_unit==="seconds_per_km")return `Ritmo ${paceRange(resolvedMinimum,resolvedMaximum)} · ${percentage(minimum)}–${percentage(maximum)} % del ritmo umbral · Ritmo umbral: ${formatPace(referenceValue)}`;
  if(target.metric==="swim_pace"&&target.resolved_unit==="seconds_per_100m")return `Ritmo ${swimRange(resolvedMinimum,resolvedMaximum)} · ${percentage(minimum)}–${percentage(maximum)} % del CSS · CSS: ${formatSwimPace(referenceValue).replace("min/100 m","/100 m")}`;
 }
 if(target.mode==="percent_reference")return `${decimal(minimum)}–${decimal(maximum)} × ${reference}`;
 const range=target.minimum!==undefined&&target.maximum!==undefined?`${target.minimum}–${target.maximum}`:"";
 if(target.metric==="rpe")return `RPE ${range}`;
 if(target.metric==="pace")return formatPace(Number(target.minimum??0));
 if(target.metric==="swim_pace")return formatSwimPace(Number(target.minimum??0));
 return `${target.metric==="power"?"Potencia":target.metric==="heart_rate"?"Frecuencia cardiaca":target.metric} ${range}`.trim();
}
export function targetLabel(value:unknown,key=""){
 if(typeof value!=="number")return String(value??"");
 const lower=key.toLowerCase();if(lower.includes("pace")&&lower.includes("100"))return paceLabel(value,"/100 m");if(lower.includes("pace"))return paceLabel(value);if(lower.includes("watt"))return `${Math.round(value)} W`;if(lower.includes("heart")||lower.includes("bpm"))return `${Math.round(value)} ppm`;if(lower.includes("rpe"))return `RPE ${value}`;if(lower.includes("duration")||lower.includes("seconds"))return durationLabel(value);return String(value);
}
export function errorMessage(error:unknown){const text=error instanceof Error?error.message:"";if(text.includes("training_plan_active_conflict"))return "Ya existe otro plan activo para este atleta.";if(text.includes("training_plan_invalid_transition"))return "El estado actual del plan no permite realizar esta acción.";if(text.includes("training_plan_overlap"))return "Ya existe un plan de entrenamiento para parte de este periodo.";if(text.includes("fingerprint"))return "La vista previa ya no coincide con la versión esperada.";if(text.includes("athlete_permission_denied")||text.includes("403"))return "No tienes permisos para realizar esta acción.";if(text.includes("planning_preferences_not_found"))return "Completa o guarda tu disponibilidad antes de generar el plan.";if(text.includes("goal")&&text.includes("invalid"))return "Uno de los objetivos ya no es válido para este atleta.";if(text.includes("blocking")||text.includes("NO_TRAINING_AVAILABILITY"))return "La disponibilidad actual impide construir un plan. Revisa los días y minutos disponibles.";if(text.includes("404"))return "El recurso ya no está disponible.";if(text.includes("422"))return "Revisa objetivos, fechas y disponibilidad; no se pudo construir el plan.";return "No se ha podido completar la operación. Inténtalo de nuevo."}
import type {WorkoutTarget} from "../../types/planning";
import {formatPace,formatSwimPace} from "../profile/profileFormat";
