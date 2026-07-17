import {render,screen} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {describe,expect,it} from "vitest";
import type {ActivitySummary} from "../../types/api";
import {RecentActivityList} from "./RecentActivityList";
const activity:ActivitySummary={id:"internal-uuid",external_activity_id:"strava-1",name:"Morning Run",sport_type:"running",start_time:"2026-07-14T06:00:00Z",athlete_timezone:"Europe/Madrid",distance_metres:8200,moving_time_seconds:2538,elapsed_time_seconds:2600,elevation_metres:74,average_heart_rate:null,average_watts:null,trainer:false,manual:false,visibility:"everyone"};
describe("RecentActivityList",()=>{it("links each activity to the internal detail route and navigates by keyboard",async()=>{render(<RecentActivityList activities={[activity]}/>);const link=screen.getByRole("link",{name:"Ver actividad Morning Run"});expect(link).toHaveAttribute("href","/activities/internal-uuid?return=%2Fdashboard");link.focus();expect(link).toHaveFocus();await userEvent.click(link);expect(window.location.pathname).toBe("/activities/internal-uuid");expect(window.location.search).toBe("?return=%2Fdashboard")})});
