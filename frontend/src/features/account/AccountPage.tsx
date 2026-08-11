import {useCallback,useEffect,useState,type FormEvent} from "react";
import {useAuth} from "../../app/AuthContext";
import {apiClient,type ApiClient} from "../../services/apiClient";
import type {Account} from "./accountTypes";

function formatDate(value:string|null){
 if(!value)return "Sin accesos registrados";
 return new Intl.DateTimeFormat("es-ES",{dateStyle:"medium",timeStyle:"short"}).format(new Date(value));
}
function isAuthenticationError(error:unknown){return error instanceof Error&&error.message.includes("(401)")}
function passwordError(error:unknown){
 const message=error instanceof Error?error.message:"";
 if(message.includes("current_password_invalid"))return "La contraseña actual no es correcta.";
 if(message.includes("new_password_unchanged"))return "La nueva contraseña debe ser diferente de la actual.";
 if(message.includes("(422)"))return "La nueva contraseña debe tener entre 12 y 1024 caracteres.";
 if(message.includes("(403)"))return "No se ha podido completar la operación. Actualiza la página e inténtalo de nuevo.";
 return "No se ha podido actualizar la contraseña. Inténtalo de nuevo.";
}

export function AccountPage({client=apiClient}:{client?:ApiClient}){
 const {refreshUser}=useAuth();
 const [account,setAccount]=useState<Account|null>(null),[loading,setLoading]=useState(true),[loadError,setLoadError]=useState(false);
 const [displayName,setDisplayName]=useState(""),[savingName,setSavingName]=useState(false),[nameMessage,setNameMessage]=useState(""),[nameError,setNameError]=useState("");
 const [currentPassword,setCurrentPassword]=useState(""),[newPassword,setNewPassword]=useState(""),[confirmPassword,setConfirmPassword]=useState("");
 const [savingPassword,setSavingPassword]=useState(false),[passwordMessage,setPasswordMessage]=useState(""),[passwordFormError,setPasswordFormError]=useState("");
 const load=useCallback(async()=>{setLoading(true);setLoadError(false);try{if(!client.getAccount)throw new Error("account_api_unavailable");const value=await client.getAccount();setAccount(value);setDisplayName(value.display_name??"")}catch(error){if(isAuthenticationError(error))void refreshUser().catch(()=>undefined);else setLoadError(true)}finally{setLoading(false)}},[client,refreshUser]);
 useEffect(()=>{void load()},[load]);
 async function saveName(event:FormEvent){event.preventDefault();if(savingName||!account||!client.updateAccount)return;setSavingName(true);setNameError("");setNameMessage("");try{const value=await client.updateAccount({display_name:displayName.trim()?displayName:null});setAccount(value);setDisplayName(value.display_name??"");await refreshUser();setNameMessage("Nombre actualizado correctamente.")}catch(error){if(isAuthenticationError(error))void refreshUser().catch(()=>undefined);else setNameError("No se ha podido guardar el nombre. Inténtalo de nuevo.")}finally{setSavingName(false)}}
 async function savePassword(event:FormEvent){event.preventDefault();if(savingPassword||!client.changePassword)return;setPasswordFormError("");setPasswordMessage("");if(!currentPassword)return setPasswordFormError("Introduce tu contraseña actual.");if(!newPassword)return setPasswordFormError("Introduce una contraseña nueva.");if(!confirmPassword)return setPasswordFormError("Confirma la contraseña nueva.");if(newPassword.length<12||newPassword.length>1024)return setPasswordFormError("La nueva contraseña debe tener entre 12 y 1024 caracteres.");if(newPassword!==confirmPassword)return setPasswordFormError("Las contraseñas nuevas no coinciden.");setSavingPassword(true);try{await client.changePassword({current_password:currentPassword,new_password:newPassword});setCurrentPassword("");setNewPassword("");setConfirmPassword("");setPasswordMessage("Contraseña actualizada correctamente.")}catch(error){if(isAuthenticationError(error))void refreshUser().catch(()=>undefined);else setPasswordFormError(passwordError(error))}finally{setSavingPassword(false)}}
 if(loading)return <section className="account-state" role="status">Cargando cuenta…</section>;
 if(loadError)return <section className="account-state account-state--error" role="alert"><h1>No se ha podido cargar la cuenta</h1><p>Comprueba tu conexión e inténtalo de nuevo.</p><button className="button button--primary" type="button" onClick={()=>void load()}>Reintentar</button></section>;
 if(!account)return null;
 return <div className="account-page">
  <header className="account-header"><p>CONFIGURACIÓN</p><h1>Cuenta</h1><span>Gestiona la identidad y seguridad de tu cuenta.</span></header>
  <section className="account-card" aria-labelledby="account-information"><header><h2 id="account-information">Información de la cuenta</h2><p>Datos asociados a tu sesión de TriCoach AI.</p></header><dl className="account-details"><div><dt>Nombre visible</dt><dd>{account.display_name??"No definido"}</dd></div><div><dt>Correo electrónico</dt><dd>{account.email}</dd><small>Solo lectura</small></div><div><dt>Cuenta creada</dt><dd>{formatDate(account.created_at)}</dd></div><div><dt>Último acceso</dt><dd>{formatDate(account.last_login_at)}</dd></div></dl></section>
  <section className="account-card" aria-labelledby="display-name-title"><header><h2 id="display-name-title">Cambiar nombre visible</h2><p>Este nombre aparece en el encabezado y avatar de la aplicación.</p></header><form onSubmit={saveName} className="account-form"><label htmlFor="display-name">Nombre visible</label><input id="display-name" value={displayName} maxLength={200} onChange={event=>setDisplayName(event.target.value)} aria-describedby="display-name-help name-feedback"/><small id="display-name-help">Puedes dejarlo vacío para eliminarlo. Máximo 200 caracteres.</small><div id="name-feedback" className={nameError?"account-feedback account-feedback--error":"account-feedback"} role={nameError?"alert":"status"} aria-live="polite">{nameError||nameMessage}</div><button className="button button--primary" disabled={savingName} type="submit">{savingName?"Guardando…":"Guardar nombre"}</button></form></section>
  <section className="account-card" aria-labelledby="password-title"><header><h2 id="password-title">Cambiar contraseña</h2><p>La nueva contraseña debe tener entre 12 y 1024 caracteres.</p></header><form onSubmit={savePassword} className="account-form"><label htmlFor="current-password">Contraseña actual</label><input id="current-password" type="password" autoComplete="current-password" value={currentPassword} maxLength={1024} onChange={event=>setCurrentPassword(event.target.value)}/><label htmlFor="new-password">Nueva contraseña</label><input id="new-password" type="password" autoComplete="new-password" value={newPassword} maxLength={1024} onChange={event=>setNewPassword(event.target.value)}/><label htmlFor="confirm-password">Confirmar nueva contraseña</label><input id="confirm-password" type="password" autoComplete="new-password" value={confirmPassword} maxLength={1024} onChange={event=>setConfirmPassword(event.target.value)} aria-describedby="password-feedback"/><div id="password-feedback" className={passwordFormError?"account-feedback account-feedback--error":"account-feedback"} role={passwordFormError?"alert":"status"} aria-live="polite">{passwordFormError||passwordMessage}</div><button className="button button--primary" disabled={savingPassword} type="submit">{savingPassword?"Actualizando…":"Cambiar contraseña"}</button></form></section>
 </div>
}
