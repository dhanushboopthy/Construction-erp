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
export type Item = Schemas["ItemOut"];
export type ItemOwner = Schemas["ItemOwnerOut"];
export type ItemCreate = Schemas["ItemCreate"];
export type ItemUpdate = Schemas["ItemUpdate"];
export type ItemUnit = Schemas["ItemUnitOut"];
export type ItemCategory = Schemas["ItemCategory"];
export type ImportResult = Schemas["ImportResult"];
export type Conversion = Schemas["ConversionOut"];
export type Party = Schemas["PartyOut"];
export type PartyCreate = Schemas["PartyCreate"];
export type PartyUpdate = Schemas["PartyUpdate"];
export type PartyType = Schemas["PartyType"];
export type Site = Schemas["SiteOut"];
export type SiteCreate = Schemas["SiteCreate"];
export type SiteUpdate = Schemas["SiteUpdate"];
export type CustomerSegment = Schemas["CustomerSegment"];
export type Page<T> = { items: T[]; total: number; limit: number; offset: number };
export type OpeningRow = Schemas["OpeningOut"];
export type OpeningCreate = Schemas["OpeningCreate"];
export type OpeningKind = Schemas["OpeningKind"];
export type PostResult = Schemas["PostResult"];
export type StockItem = Schemas["StockItemOut"];
export type StockItemOwner = Schemas["StockItemOwnerOut"];
export type Statement = Schemas["StatementOut"];
export type AccountView = Schemas["AccountOut"];
export type Dues = Schemas["DuesOut"];
export type LedgerAccount = Schemas["LedgerAccount"];
export type CostComponent = Schemas["CostComponentOut"];
export type CostComponentCreate = Schemas["CostComponentIn"];
export type ChargeBasis = Schemas["ChargeBasis"];
export type PurchaseCreate = Schemas["PurchaseCreate"];
export type PurchaseLineIn = Schemas["PurchaseLineIn"];
export type ChargeIn = Schemas["ChargeIn"];
export type Purchase = Schemas["PurchaseOut"];
export type PurchaseOwner = Schemas["PurchaseOwnerOut"];
export type PurchasePreview = Schemas["PurchasePreview"];
export type PaymentCreate = Schemas["PaymentCreate"];
export type PaymentOut = Schemas["PaymentOut"];
export type PaymentMode = Schemas["PaymentMode"];
export type Transfer = Schemas["TransferOut"];
export type TransferCreate = Schemas["TransferCreate"];
export type StockCount = Schemas["CountOut"];
export type StockCountOwner = Schemas["CountOwnerOut"];
export type AuditLogEntry = Schemas["AuditLogOut"];

/** Error body returned by the API for every failure (core/errors.py adds the extras). */
export type ApiErrorBody = Schemas["ErrorResponse"] & {
  requires_owner_approval?: boolean;
  errors?: { field: string; message: string }[];
};
