import type { ActivitySummary } from "../../types/api";import { ActivityCard } from "./ActivityCard";
export function ActivityList({items,returnQuery}:{items:ActivitySummary[];returnQuery:string}){return <div className="browse-activity-list">{items.map(x=><ActivityCard key={x.id} activity={x} returnQuery={returnQuery}/>)}</div>}
