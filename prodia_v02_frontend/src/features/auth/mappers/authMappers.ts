/**
 * Mapper snake_case (API) -> camelCase (modelo de vista). Copiado literal
 * de Robustez V02. Contrato "Interceptor 1 (Pydantic) <-> Interceptor 2
 * (mappers)": el backend define el esquema, el mapper es la única frontera
 * donde cambia el naming — ninguna vista de ProdIA V02 consume snake_case.
 */
import type {
  AuthGroup,
  AuthPermissions,
  AuthSession,
  AuthUser,
  LoginResult,
} from '../types/authTypes';

interface ApiGroup {
  id: number;
  name: string;
  description?: string | null;
  is_admin: boolean;
}

interface ApiUser {
  id: number;
  username: string;
  email: string;
  full_name?: string | null;
  is_admin: boolean;
  is_active: boolean;
  group?: ApiGroup | null;
  last_login_at?: string | null;
  created_at: string;
  updated_at: string;
}

interface ApiPermissions {
  campos?: string[];
  sections?: string[];
}

export interface ApiMeResponse {
  user: ApiUser;
  permissions: ApiPermissions;
}

interface ApiLoginResponse {
  access_token: string;
  token_type: string;
}

export function toAuthGroup(api: ApiGroup): AuthGroup {
  return {
    id: api.id,
    name: api.name,
    description: api.description ?? null,
    isAdmin: api.is_admin,
  };
}

export function toAuthUser(api: ApiUser): AuthUser {
  return {
    id: api.id,
    username: api.username,
    email: api.email,
    fullName: api.full_name ?? null,
    isAdmin: api.is_admin,
    isActive: api.is_active,
    group: api.group ? toAuthGroup(api.group) : null,
    lastLoginAt: api.last_login_at ?? null,
    createdAt: api.created_at,
    updatedAt: api.updated_at,
  };
}

export function toAuthPermissions(api: ApiPermissions): AuthPermissions {
  return {
    campos: api.campos ?? [],
    sections: api.sections ?? [],
  };
}

export function toAuthSession(api: ApiMeResponse): AuthSession {
  return {
    user: toAuthUser(api.user),
    permissions: toAuthPermissions(api.permissions),
  };
}

export function toLoginResult(api: ApiLoginResponse): LoginResult {
  return {
    accessToken: api.access_token,
    tokenType: api.token_type,
  };
}
