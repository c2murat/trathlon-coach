import type {UnitSystem} from "./athleteProfileTypes";
const LB_PER_KG=2.2046226218,INCHES_PER_METER=39.37007874;
export const metersToCentimeters=(value:number)=>Math.round(value*1000)/10;
export const centimetersToMeters=(value:number)=>Math.round(value*10)/1000;
export const kilogramsToPounds=(value:number)=>Math.round(value*LB_PER_KG*10)/10;
export const poundsToKilograms=(value:number)=>Math.round(value/LB_PER_KG*1000)/1000;
export function metersToFeetAndInches(value:number){const total=Math.round(value*INCHES_PER_METER);return {feet:Math.floor(total/12),inches:total%12}}
export const feetAndInchesToMeters=(feet:number,inches:number)=>Math.round(((feet*12)+inches)/INCHES_PER_METER*1000)/1000;
export const displayWeight=(kg:number|null,unit:UnitSystem)=>kg===null?"":String(unit==="metric"?Math.round(kg*1000)/1000:kilogramsToPounds(kg));
export function displayHeight(meters:number|null,unit:UnitSystem){if(meters===null)return {primary:"",secondary:""};if(unit==="metric")return {primary:String(metersToCentimeters(meters)),secondary:""};const value=metersToFeetAndInches(meters);return {primary:String(value.feet),secondary:String(value.inches)}}
