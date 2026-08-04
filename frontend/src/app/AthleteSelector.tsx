import {roleLabel} from "../types/sessionContext";
import {useAthleteContext} from "./AthleteContext";
export function AthleteSelector({required=false}:{required?:boolean}){
 const {athletes,activeAthlete,selectAthlete}=useAthleteContext();
 if(athletes.length===1)return <div className="athlete-identity"><strong>{athletes[0].label}</strong><small>{roleLabel(athletes[0].role)}</small></div>;
 return <div className={required?"athlete-selector athlete-selector--required":"athlete-selector"}>
  <label htmlFor={required?"required-athlete":"active-athlete"}>{required?"Selecciona un atleta":"Atleta activo"}</label>
  <select id={required?"required-athlete":"active-athlete"} aria-label="Seleccionar atleta" value={activeAthlete?.athlete_id??""} onChange={event=>selectAthlete(event.target.value)}>
   <option value="" disabled>Selecciona…</option>{athletes.map(item=><option key={item.athlete_id} value={item.athlete_id}>{item.label} · {roleLabel(item.role)}</option>)}
  </select>{activeAthlete&&<small>{roleLabel(activeAthlete.role)}</small>}
 </div>
}
