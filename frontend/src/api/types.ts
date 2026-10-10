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
export type RateRow = Schemas["RateRowOut"];
export type RateRowOwner = Schemas["RateRowOwnerOut"];
export type MarketRatesResult = Schemas["MarketRatesResult"];
export type CustomerRate = Schemas["CustomerRateOut"];
export type CustomerRateCreate = Schemas["CustomerRateCreate"];
export type MarginOut = Schemas["MarginOut"];
export type InvoiceCreate = Schemas["InvoiceCreate"];
export type InvoiceLineIn = Schemas["InvoiceLineIn"];
export type InvoicePreview = Schemas["InvoicePreview"];
export type InvoiceSummary = Schemas["InvoiceSummary"];
export type Invoice = Schemas["InvoiceOut"];
export type InvoiceOwner = Schemas["InvoiceOwnerOut"];
export type FulfilmentSource = Schemas["FulfilmentSource"];
export type ApprovalAction = Schemas["ApprovalAction"];
export type ApprovalOut = Schemas["ApprovalOut"];
export type OpenBills = Schemas["OpenBillsOut"];
export type AuditLogEntry = Schemas["AuditLogOut"];

/** Error body returned by the API for every failure (core/errors.py adds the extras). */
export type ApiErrorBody = Schemas["ErrorResponse"] & {
  requires_owner_approval?: boolean;
  errors?: { field: string; message: string }[];
};
export type CreditNote = Schemas["CreditNoteOut"];
export type CreditNoteSummary = Schemas["CreditNoteSummary"];
export type CreditNoteCreate = Schemas["CreditNoteCreate"];
export type DebitNote = Schemas["DebitNoteOut"];
export type DebitNoteSummary = Schemas["DebitNoteSummary"];
export type DebitNoteCreate = Schemas["DebitNoteCreate"];
export type ReturnLineIn = Schemas["ReturnLineIn"];
export type Vehicle = Schemas["VehicleOut"];
export type VehicleCreate = Schemas["VehicleCreate"];
export type Trip = Schemas["TripOut"];
export type TripCreate = Schemas["TripCreate"];
export type OpenDirectLine = Schemas["OpenDirectLineOut"];
export type DropShipReport = Schemas["DropShipReport"];
export type DropShipLinkCreate = Schemas["LinkCreate"];
export type EwayStatus = Schemas["EwayStatusOut"];
export type EwayBill = Schemas["EwayOut"];
export type EwayCreate = Schemas["EwayCreate"];
export type EwayManual = Schemas["EwayManual"];
export type EwayVehicleUpdate = Schemas["EwayVehicleUpdate"];
export type PendingEway = Schemas["PendingEwayOut"];
export type EInvoiceStatus = Schemas["EInvoiceStatusOut"];
export type EInvoiceCreate = Schemas["EInvoiceCreate"];
export type Attachment = Schemas["AttachmentOut"];
export type AttachmentRef = Schemas["AttachmentRef"];
export type AttachmentKind = Schemas["AttachmentKind"];
export type Scheme = Schemas["SchemeOut"];
export type SchemeCreate = Schemas["SchemeCreate"];
export type Today = Schemas["TodayOut"];
export type ClosingPreview = Schemas["ClosingPreview"];
export type ClosingCreate = Schemas["ClosingCreate"];
export type Closing = Schemas["ClosingOut"];
export type ProfitReport = Schemas["ProfitReport"];
export type ProfitGroup = Schemas["ProfitGroup"];
export type SegmentReport = Schemas["SegmentReport"];
export type Gstr1 = Schemas["Gstr1"];
export type Gstr3b = Schemas["Gstr3b"];
export type Gstr2bResult = Schemas["Gstr2bResult"];
export type SystemStatus = Schemas["StatusOut"];
export type SystemCheck = Schemas["Check"];
export type VerifyResult = Schemas["VerifyOut"];

// FM1: cash book, expense heads, profit and loss, KPI catalogue.
export type CashEntryKind = Schemas["CashEntryKind"];
export type ExpenseNature = Schemas["ExpenseNature"];
export type ExpenseCategory = Schemas["ExpenseCategoryOut"];
export type ExpenseCategoryIn = Schemas["ExpenseCategoryIn"];
export type ExpenseCategoryUpdate = Schemas["ExpenseCategoryUpdate"];
export type CashEntry = Schemas["CashEntryOut"];
export type CashEntryCreate = Schemas["CashEntryCreate"];
export type CashBook = Schemas["CashBookOut"];
export type Pnl = Schemas["PnlOut"];
export type KpiDefinition = Schemas["KpiDefinitionOut"];

// FM6: inventory analytics, stock value (NRV), cement age, weight shortages.
export type InventoryAnalytics = Schemas["InventoryAnalyticsOut"];
export type InventoryRow = Schemas["InventoryRowOut"];
export type NrvReport = Schemas["NrvReportOut"];
export type NrvRow = Schemas["NrvRowOut"];
export type Writedown = Schemas["WritedownOut"];
export type WritedownCreate = Schemas["WritedownCreate"];
export type FifoAge = Schemas["FifoAgeOut"];
export type Shrinkage = Schemas["ShrinkageOut"];

// FM5: working capital, receivables by due date, bad-debt write-offs.
export type WorkingCapital = Schemas["WorkingCapitalOut"];
export type WorkingCapitalPoint = Schemas["WorkingCapitalPoint"];
export type Receivables = Schemas["ReceivablesOut"];
export type ReceivablesOwner = Schemas["ReceivablesOwnerOut"];
export type ReceivableRow = Schemas["ReceivableRowOut"];
export type OverdueBuckets = Schemas["BucketsOut"];
export type Writeoff = Schemas["WriteoffOut"];
export type WriteoffCreate = Schemas["WriteoffCreate"];

// FM4: Tally export.
export type TallyLedgers = Schemas["TallyLedgersOut"];
export type TallyLedger = Schemas["TallyLedgerOut"];
export type TallyPreview = Schemas["TallyPreviewOut"];
export type TallyCheck = Schemas["TallyCheckOut"];

// FM3: labelled rate overrides.
export type RateOverrides = Schemas["RateOverridesOut"];
export type RateOverrideLine = Schemas["OverrideLineOut"];
export type RateOverrideUser = Schemas["OverrideUserOut"];

// FM2: stock adjustments with reasons, ITC to reverse.
export type AdjustmentReason = Schemas["AdjustmentReason"];
export type StockDirection = Schemas["Direction"];
export type AdjustmentCreate = Schemas["AdjustmentCreate"];
export type Adjustment = Schemas["AdjustmentOut"];
export type AdjustmentOwner = Schemas["AdjustmentOwnerOut"];
export type AdjustmentBook = Schemas["AdjustmentBookOut"];
export type AdjustmentBookOwner = Schemas["AdjustmentBookOwnerOut"];
export type ItcReversal = Schemas["ItcReversalOut"];

// FM7: controls
export type PeriodLock = Schemas["PeriodLockOut"];
export type PeriodLockSet = Schemas["PeriodLockSet"];
export type PeriodChecklist = Schemas["PeriodChecklist"];
export type BankAccount = Schemas["BankAccountOut"];
export type BankStatement = Schemas["BankStatementOut"];
export type Reconciliation = Schemas["ReconciliationOut"];
export type ExceptionReport = Schemas["ExceptionReport"];
export type AuditLogRow = Schemas["AuditLogOut"];
export type AuditAction = Schemas["AuditAction"];

// FM8: profitability cuts and ITC at risk
export type Cut = Schemas["Cut"];
export type Profitability = Schemas["ProfitabilityOut"];
export type CutRow = Schemas["CutRow"];
export type ItcAtRisk = Schemas["ItcAtRiskOut"];
export type ItcRiskRow = Schemas["ItcRiskRow"];

// FM10: orders, lots and demand
export type PurchaseOrderRow = Schemas["OrderOut"] | Schemas["OrderOwnerOut"];
export type PurchaseOrderOwner = Schemas["OrderOwnerOut"];
export type OrderCreate = Schemas["OrderCreate"];
export type ReceiptCreate = Schemas["ReceiptCreate"];
export type MatchReport = Schemas["MatchReport"];
export type OrderMatchRow = Schemas["OrderMatchRow"];
export type LostSale = Schemas["LostSaleOut"] | Schemas["LostSaleOwnerOut"];
export type LostSaleCreate = Schemas["LostSaleCreate"];
export type FillRateReport = Schemas["FillRateReport"];
