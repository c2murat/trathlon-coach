import {createContext,useCallback,useContext,useEffect,useMemo,useState,type ReactNode} from "react";
import {apiClient,type ApiClient} from "../services/apiClient";
import type {AuthenticatedUser,LoginCredentials} from "../types/auth";
import {navigate} from "./usePathname";

type AuthStatus="loading"|"authenticated"|"unauthenticated";
interface AuthContextValue{status:AuthStatus;user:AuthenticatedUser|null;login(credentials:LoginCredentials):Promise<void>;logout():Promise<void>;refreshUser():Promise<void>}
const AuthContext=createContext<AuthContextValue|null>(null);
export function AuthProvider({children,client=apiClient}:{children:ReactNode;client?:ApiClient}){
 const [status,setStatus]=useState<AuthStatus>("loading"),[user,setUser]=useState<AuthenticatedUser|null>(null);
 useEffect(()=>{let active=true;void client.authMe().then(value=>{if(active){setUser(value);setStatus("authenticated")}}).catch(()=>{if(active){setUser(null);setStatus("unauthenticated")}});return()=>{active=false}},[client]);
 const login=useCallback(async(credentials:LoginCredentials)=>{const value=await client.login(credentials);setUser(value);setStatus("authenticated");navigate("/")},[client]);
 const logout=useCallback(async()=>{await client.logout();setUser(null);setStatus("unauthenticated");navigate("/login")},[client]);
 const refreshUser=useCallback(async()=>{try{const value=await client.authMe();setUser(value);setStatus("authenticated")}catch(error){setUser(null);setStatus("unauthenticated");navigate("/login");throw error}},[client]);
 const value=useMemo(()=>({status,user,login,logout,refreshUser}),[status,user,login,logout,refreshUser]);
 return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
export function useAuth(){const value=useContext(AuthContext);if(!value)throw new Error("AuthProvider is required");return value}
