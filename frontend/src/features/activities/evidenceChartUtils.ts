import type {ActivityEvidence,EvidenceStream} from "../../types/api";

export type AxisKind="time"|"distance"|"sample";
export type ChartSeries={key:string;label:string;unit:string;values:(number|null)[]};
export type ChartDatum={index:number;x:number;y:number;rawY:number};

export const seriesMeta:Record<string,{label:string;unit:string;convert:(value:number)=>number}>={
 velocity_smooth:{label:"Velocidad",unit:"km/h",convert:value=>value*3.6},
 heartrate:{label:"Frecuencia cardiaca",unit:"ppm",convert:value=>value},
 watts:{label:"Potencia",unit:"W",convert:value=>value},
 cadence:{label:"Cadencia",unit:"rpm",convert:value=>value},
 altitude:{label:"Altitud",unit:"m",convert:value=>value},
};

export function formatTime(value:number){const seconds=Math.max(0,Math.round(value)),h=Math.floor(seconds/3600),m=Math.floor(seconds%3600/60),s=seconds%60;return h?`${h}:${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")}`:`${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")}`}
export function formatAxisDistance(value:number){if(Math.abs(value)<1000)return `${Math.round(value)} m`;return `${new Intl.NumberFormat("es-ES",{maximumFractionDigits:Math.abs(value)<10000?1:0}).format(value/1000)} km`}
export function formatSeriesValue(key:string,value:number){if(key==="altitude")return new Intl.NumberFormat("es-ES",{maximumFractionDigits:Number.isInteger(value)?0:1}).format(value);return new Intl.NumberFormat("es-ES",{maximumFractionDigits:0}).format(value)}

export function stableTicks(min:number,max:number,count=5){if(!Number.isFinite(min)||!Number.isFinite(max))return [] as number[];if(min===max)return [min];const divisions=Math.max(1,count-1);return Array.from({length:count},(_,index)=>min+(max-min)*index/divisions)}
export function extent(values:number[]){if(!values.length)return null;return {min:Math.min(...values),max:Math.max(...values)}}
export function scale(value:number,min:number,max:number,start:number,end:number){return min===max?(start+end)/2:start+(value-min)*(end-start)/(max-min)}

function aligned(stream:EvidenceStream|undefined,length:number){return stream?.values.length===length&&stream.values.every(value=>value!==null&&Number.isFinite(Number(value)))}
export function selectXAxis(evidence:ActivityEvidence,length:number){const time=evidence.streams.time,distance=evidence.streams.distance;if(aligned(time,length))return {kind:"time" as const,label:"Tiempo transcurrido",values:time.values.map(Number),warning:null};if(aligned(distance,length))return {kind:"distance" as const,label:"Distancia acumulada",values:distance.values.map(Number),warning:time?"El stream de tiempo no está alineado; se usa distancia acumulada.":null};return {kind:"sample" as const,label:"Índice de muestra",values:Array.from({length},(_,index)=>index+1),warning:time||distance?"Los streams de referencia no están alineados; se usa el índice de muestra sin interpolar.":null}}
export function prepareSeries(key:string,stream:EvidenceStream):ChartSeries{const meta=seriesMeta[key];return {key,label:meta.label,unit:meta.unit,values:stream.values.map(value=>value===null||!Number.isFinite(Number(value))?null:meta.convert(Number(value)))}}
export function formatX(kind:AxisKind,value:number){return kind==="time"?formatTime(value):kind==="distance"?formatAxisDistance(value):String(Math.round(value))}
