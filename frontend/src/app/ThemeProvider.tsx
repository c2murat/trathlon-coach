import { createContext, useContext, useEffect, useMemo, useState } from "react";
type Theme="light"|"dark";
const ThemeContext=createContext<{theme:Theme;toggle():void}>({theme:"light",toggle:()=>undefined});
function initialTheme():Theme {const saved=localStorage.getItem("tricoach-theme");if(saved==="light"||saved==="dark")return saved;return window.matchMedia?.("(prefers-color-scheme: dark)").matches?"dark":"light";}
export function ThemeProvider({children}:{children:React.ReactNode}){const [theme,setTheme]=useState<Theme>(initialTheme);useEffect(()=>{document.documentElement.dataset.theme=theme;localStorage.setItem("tricoach-theme",theme)},[theme]);const value=useMemo(()=>({theme,toggle:()=>setTheme(current=>current==="light"?"dark":"light")}),[theme]);return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>}
export function useTheme(){return useContext(ThemeContext)}
