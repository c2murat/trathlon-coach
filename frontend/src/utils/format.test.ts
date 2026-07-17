import { describe,expect,it } from "vitest";
import { formatActivityDateLine,formatCadence,formatCommute,formatCompactDuration,formatDistance,formatDuration,formatManual,formatPower,formatSportSpeed,formatTrainer,formatVisibility } from "./format";
describe("basic metric formatting",()=>{it("formats durations and distances",()=>{expect(formatDuration(2538)).toBe("42:18");expect(formatDuration(7865)).toBe("2:11:05");expect(formatDuration(null)).toBe("No disponible");expect(formatDistance(8200)).toBe("8,2 km");expect(formatDistance(450)).toBe("0,5 km");expect(formatDistance(null)).toBe("No disponible")})});
describe("sport-aware speed",()=>{
 it("converts cycling m/s to Spanish km/h",()=>{const x=formatSportSpeed("cycling",10,15);expect(x).toEqual({averageLabel:"Velocidad media",maximumLabel:"Velocidad máxima",averageValue:"36,0 km/h",maximumValue:"54,0 km/h"})});
 it("converts running speed to min/km pace",()=>{const x=formatSportSpeed("running",1000/300,1000/240);expect(x.averageValue).toBe("5:00 min/km");expect(x.maximumValue).toBe("4:00 min/km")});
 it("converts swimming speed to pace per 100 metres",()=>{const x=formatSportSpeed("swimming",100/90,100/75);expect(x.averageValue).toBe("1:30 /100 m");expect(x.maximumValue).toBe("1:15 /100 m")});
 it("rejects zero, missing and invalid speed",()=>{expect(formatSportSpeed("running",0,null).averageValue).toBe("No disponible");expect(formatSportSpeed("cycling",Number.NaN,-1).maximumValue).toBe("No disponible");expect(formatSportSpeed("other",null,null).averageValue).toBe("No disponible")});
});
describe("activity metadata formatting",()=>{
 it("keeps literal rounded power units",()=>{expect(formatPower(221.6)).toBe("222 W");expect(formatPower(250)).toBe("250 W");expect(formatPower(174)).toBe("174 W");expect(formatPower(184)).toBe("184 W");expect(formatPower(174)).not.toContain("Oeste");expect(formatPower(null)).toBe("No disponible")});
 it("formats cadence without inferring swimming semantics",()=>{expect(formatCadence("cycling",88).value).toBe("88 rpm");expect(formatCadence("running",172).value).toBe("172 ppm");expect(formatCadence("swimming",30)).toEqual({label:"Cadencia de brazada",value:"No disponible"})});
 it("localizes visibility variants safely",()=>{expect(formatVisibility("everyone")).toBe("Todos");expect(formatVisibility("followers_only")).toBe("Seguidores");expect(formatVisibility("follower_only")).toBe("Seguidores");expect(formatVisibility("only_me")).toBe("Solo yo");expect(formatVisibility("solo_yo")).toBe("Solo yo");expect(formatVisibility("private")).toBe("Privada");expect(formatVisibility("public")).toBe("Pública");expect(formatVisibility("unexpected_value")).toBe("No disponible")});
 it("uses readable trainer, manual and commute phrases",()=>{expect(formatTrainer(true)).toBe("Sí, rodillo");expect(formatTrainer(false)).toBe("No, exterior");expect(formatManual(true)).toBe("Registrada manualmente");expect(formatManual(false)).toBe("Registrada automáticamente");expect(formatCommute(true)).toBe("Desplazamiento");expect(formatCommute(false)).toBe("Actividad deportiva")});
});

describe("activity hero formatting",()=>{it("formats compact duration and localized date",()=>{expect(formatCompactDuration(3840)).toBe("1 h 04 min");expect(formatActivityDateLine("2026-07-15T05:21:00Z","Europe/Madrid")).toBe("Miércoles · 15 jul 2026 · 07:21")})});
