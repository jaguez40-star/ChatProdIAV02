export interface AuthUser {
  id: number;
  username: string;
  email: string;
  fullName: string | null;
  isAdmin: boolean;
  isActive: boolean;
  group: AuthGroup | null;
  lastLoginAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface AuthGroup {
  id: number;
  name: string;
  description: string | null;
  isAdmin: boolean;
}

export interface AuthPermissions {
  campos: string[];
  sections: string[];
}

export interface AuthSession {
  user: AuthUser;
  permissions: AuthPermissions;
}

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface LoginResult {
  accessToken: string;
  tokenType: string;
}
