import {describe,expect,it} from "vitest";import {cssToSeconds,paceToSeconds,secondsToCss,secondsToPace,formatPace,formatSwimPace,formatPaceRange,formatSwimPaceRange} from "./profileFormat";
describe("conversiones del perfil",()=>{it("convierte ritmo",()=>{expect(paceToSeconds("4","35")).toBe(275);expect(secondsToPace(275)).toEqual({minutes:"4",seconds:"35"})});it("convierte CSS",()=>{expect(cssToSeconds("1","42")).toBe(102);expect(secondsToCss(102)).toEqual({minutes:"1",seconds:"42"})});it("preserva vacíos",()=>{expect(paceToSeconds("","")).toBeNull();expect(secondsToPace(null)).toEqual({minutes:"",seconds:""})})});
it("formatPace",()=>{expect(formatPace(260)).toBe("4:20 min/km");expect(formatPace(270)).toBe("4:30 min/km");expect(formatPace(59)).toBe("0:59 min/km");expect(formatPace(0)).toBe("0:00 min/km")});
it("formatSwimPace",()=>{expect(formatSwimPace(110)).toBe("1:50 min/100 m");expect(formatSwimPace(120)).toBe("2:00 min/100 m")});


it("format pace ranges",()=>{expect(formatPaceRange(260,279)).toBe("4:20–4:39 min/km");expect(formatPaceRange(300,null)).toBe("Más lento que 5:00 min/km");expect(formatPaceRange(null,240)).toBe("Más rápido que 4:00 min/km");expect(formatSwimPaceRange(110,120)).toBe("1:50–2:00 min/100 m");expect(formatSwimPaceRange(95,105)).toBe("1:35–1:45 min/100 m")});

