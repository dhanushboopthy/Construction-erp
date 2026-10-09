// Hand-written for Milestone 1. Once the API grows, run `npm run gen:api` (backend running)
// to generate src/api/schema.d.ts from the OpenAPI spec and import types from there.

export type Role = "owner" | "counter" | "accountant";

export interface Location {
  id: number;
  code: string;
  name: string;
  kind: "shop" | "godown";
  address: string;
  state_code: string;
  phone: string | null;
  is_active: boolean;
}

export interface User {
  id: number;
  username: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  last_login_at: string | null;
  locations: Location[];
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: User;
}

/** Error body returned by the API for every failure. */
export interface ApiErrorBody {
  code: string;
  message: string;
  field: string | null;
  request_id: string | null;
  requires_owner_approval?: boolean;
}
