import type {BodyRegion} from "../../types/manualStrength";
export const BODY_REGIONS:readonly BodyRegion[]=["full_body","chest","back","shoulders","arms","core","quadriceps","hamstrings","glutes","calves"];
export const BODY_REGION_LABELS:Record<BodyRegion,string>={full_body:"Cuerpo completo",chest:"Pecho",back:"Espalda",shoulders:"Hombros",arms:"Brazos",core:"Zona media",quadriceps:"Cuádriceps",hamstrings:"Isquiotibiales",glutes:"Glúteos",calves:"Gemelos"};
export function toggleRegion(current:BodyRegion[],region:BodyRegion){if(current.includes(region))return current.filter(x=>x!==region);if(region==="full_body")return [region];return BODY_REGIONS.filter(x=>x!=="full_body"&&[...current.filter(y=>y!=="full_body"),region].includes(x));}
