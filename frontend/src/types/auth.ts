export type AccountPlan="owner"|"athlete"|"coach";
export interface AuthenticatedUser{id:string;email:string;display_name:string;authentication_mode:string;account_plan?:AccountPlan}
export interface LoginCredentials{email:string;password:string}
export interface RegistrationInput{display_name:string;email:string;password:string;account_plan:"athlete"|"coach";timezone:string}