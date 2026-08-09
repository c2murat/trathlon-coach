export interface AuthenticatedUser {
  id:string;
  email:string;
  display_name:string;
  authentication_mode:"development"|"session";
}

export interface LoginCredentials {email:string;password:string}
