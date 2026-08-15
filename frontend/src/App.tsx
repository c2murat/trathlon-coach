import {useEffect} from "react";
import {AppShell} from "./app/AppShell";
import {AthleteContextProvider} from "./app/AthleteContext";
import {AuthProvider,useAuth} from "./app/AuthContext";
import {ThemeProvider} from "./app/ThemeProvider";
import {navigate,usePathname} from "./app/usePathname";
import {LoginPage} from "./features/auth/LoginPage";
import {RegisterPage} from "./features/registration/RegisterPage";

function AuthenticatedArea(){
 const {status,user,logout}=useAuth();const [path]=usePathname();
 useEffect(()=>{if(status==="unauthenticated"&&!(["/login","/register"].includes(path)))navigate("/login");if(status==="authenticated"&&["/login","/register"].includes(path))navigate("/")},[status,path]);
 if(status==="loading")return <main className="auth-loading" role="status">Comprobando sesión…</main>;
 if(status==="unauthenticated")return path==="/register"?<RegisterPage/>:<LoginPage/>;
 return <AthleteContextProvider><AppShell showLogout={user?.authentication_mode==="session"} onLogout={logout}/></AthleteContextProvider>;
}
export default function App(){return <ThemeProvider><AuthProvider><AuthenticatedArea/></AuthProvider></ThemeProvider>}