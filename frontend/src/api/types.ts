// API types are generated from the backend's OpenAPI spec into schema.d.ts. Regenerate with
// `make gen-api` (Docker) or `npm run gen:api` (backend running on :8000); never edit by hand.
// This file only gives the generated shapes short names.

import type { components } from "./schema";

type Schemas = components["schemas"];

export type Role = Schemas["Role"];
export type LocationKind = Schemas["LocationKind"];
export type Location = Schemas["LocationOut"];
export type LocationCreate = Schemas["LocationCreate"];
export type LocationUpdate = Schemas["LocationUpdate"];
export type User = Schemas["UserOut"];
export type UserCreate = Schemas["UserCreate"];
export type UserUpdate = Schemas["UserUpdate"];
export type PasswordReset = Schemas["PasswordReset"];
export type ShopSettings = Schemas["ShopSettingsOut"];
export type ShopSettingsUpdate = Schemas["ShopSettingsUpdate"];
export type TokenResponse = Schemas["TokenResponse"];
export type AuditLogEntry = Schemas["AuditLogOut"];

/** Error body returned by the API for every failure (core/errors.py adds the extras). */
export type ApiErrorBody = Schemas["ErrorResponse"] & {
  requires_owner_approval?: boolean;
  errors?: { field: string; message: string }[];
};
