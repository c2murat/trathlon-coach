import { AppShell } from "./app/AppShell";
import { ThemeProvider } from "./app/ThemeProvider";
import {AthleteContextProvider} from "./app/AthleteContext";
export default function App(){return <ThemeProvider><AthleteContextProvider><AppShell/></AthleteContextProvider></ThemeProvider>}
