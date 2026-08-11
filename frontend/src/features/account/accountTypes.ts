export interface Account {
  id: string;
  email: string;
  display_name: string | null;
  created_at: string;
  last_login_at: string | null;
}

export interface AccountUpdateRequest {
  display_name: string | null;
}

export interface PasswordChangeRequest {
  current_password: string;
  new_password: string;
}
