import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router";

import { createQueryClient } from "@/api/queryClient";
import { AuthProvider } from "@/auth/AuthProvider";
import { AppShell } from "@/components/AppShell";
import { RequireAuth } from "@/components/RequireAuth";
import { RequireRole } from "@/components/RequireRole";
import { MODULES } from "@/modules";
import { ComingSoonPage } from "@/pages/ComingSoonPage";
import { ItemsPage } from "@/pages/items/ItemsPage";
import { LoginPage } from "@/pages/LoginPage";
import { PartiesPage } from "@/pages/parties/PartiesPage";
import { OrdersPage } from "@/pages/purchases/OrdersPage";
import { PurchaseEntryPage } from "@/pages/purchases/PurchaseEntryPage";
import { PurchasesPage } from "@/pages/purchases/PurchasesPage";
import { CustomerRatesPage } from "@/pages/rates/CustomerRatesPage";
import { RateBoardPage } from "@/pages/rates/RateBoardPage";
import { RatesLayout } from "@/pages/rates/RatesLayout";
import { BillEntryPage } from "@/pages/sales/BillEntryPage";
import { SalesPage } from "@/pages/sales/SalesPage";
import { PaymentsPage } from "@/pages/payments/PaymentsPage";
import { AuditLogPage } from "@/pages/settings/AuditLogPage";
import { PeriodLockPage } from "@/pages/settings/PeriodLockPage";
import { SystemPage } from "@/pages/settings/SystemPage";
import { PinPage } from "@/pages/settings/PinPage";
import { OpeningPage } from "@/pages/opening/OpeningPage";
import { ChargeTypesPage } from "@/pages/settings/ChargeTypesPage";
import { LocationsPage } from "@/pages/settings/LocationsPage";
import { SettingsLayout } from "@/pages/settings/SettingsLayout";
import { ShopSettingsPage } from "@/pages/settings/ShopSettingsPage";
import { UsersPage } from "@/pages/settings/UsersPage";
import { LostSalesPage } from "@/pages/stock/LostSalesPage";
import { ShrinkagePage } from "@/pages/stock/ShrinkagePage";
import { StockAnalysisPage } from "@/pages/stock/StockAnalysisPage";
import { StockValuePage } from "@/pages/stock/StockValuePage";
import { AdjustmentsPage } from "@/pages/stock/AdjustmentsPage";
import { CountsPage } from "@/pages/stock/CountsPage";
import { ClosingPage } from "@/pages/reports/ClosingPage";
import { BankPage } from "@/pages/reports/BankPage";
import { DuesPage } from "@/pages/reports/DuesPage";
import { OrderMatchPage } from "@/pages/reports/OrderMatchPage";
import { ExceptionsPage } from "@/pages/reports/ExceptionsPage";
import { GstPage } from "@/pages/reports/GstPage";
import { ItcRiskPage } from "@/pages/reports/ItcRiskPage";
import { ProfitCutsPage } from "@/pages/reports/ProfitCutsPage";
import { ItcReversalPage } from "@/pages/reports/ItcReversalPage";
import { MetricsPage } from "@/pages/MetricsPage";
import { ReceivablesPage } from "@/pages/reports/ReceivablesPage";
import { WorkingCapitalPage } from "@/pages/reports/WorkingCapitalPage";
import { OverridesPage } from "@/pages/reports/OverridesPage";
import { PnlPage } from "@/pages/reports/PnlPage";
import { ProfitPage } from "@/pages/reports/ProfitPage";
import { ReportsLayout } from "@/pages/reports/ReportsLayout";
import { CashBookPage } from "@/pages/cash/CashBookPage";
import { TallyPage } from "@/pages/reports/TallyPage";
import { SegmentsPage } from "@/pages/reports/SegmentsPage";
import { SchemesPage } from "@/pages/purchases/SchemesPage";
import { DirectSalesPage } from "@/pages/transport/DirectSalesPage";
import { TransportLayout } from "@/pages/transport/TransportLayout";
import { TripsPage } from "@/pages/transport/TripsPage";
import { VehiclesPage } from "@/pages/transport/VehiclesPage";
import { StockLayout } from "@/pages/stock/StockLayout";
import { StockPage } from "@/pages/stock/StockPage";
import { TransfersPage } from "@/pages/stock/TransfersPage";
import { TodayPage } from "@/pages/TodayPage";

const queryClient = createQueryClient();

/** Modules that have real screens; the rest show a placeholder until their milestone. */
const BUILT = new Set([
  "/settings",
  "/items",
  "/parties",
  "/stock",
  "/purchases",
  "/rates",
  "/sales",
  "/transport",
  "/reports",
]);

export function App({ client = queryClient }: { client?: QueryClient }) {
  return (
    <QueryClientProvider client={client}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              element={
                <RequireAuth>
                  <AppShell />
                </RequireAuth>
              }
            >
              <Route index element={<TodayPage />} />
              <Route
                path="/metrics"
                element={
                  <RequireRole roles={["owner"]}>
                    <MetricsPage />
                  </RequireRole>
                }
              />
              <Route
                path="/settings"
                element={
                  <RequireRole roles={["owner"]}>
                    <SettingsLayout />
                  </RequireRole>
                }
              >
                <Route index element={<ShopSettingsPage />} />
                <Route path="users" element={<UsersPage />} />
                <Route path="locations" element={<LocationsPage />} />
                <Route path="charges" element={<ChargeTypesPage />} />
                <Route path="pin" element={<PinPage />} />
                <Route path="opening" element={<OpeningPage />} />
                <Route path="lock" element={<PeriodLockPage />} />
                <Route path="audit" element={<AuditLogPage />} />
                <Route path="system" element={<SystemPage />} />
              </Route>
              <Route
                path="/items"
                element={
                  <RequireRole roles={["owner", "counter", "accountant"]}>
                    <ItemsPage />
                  </RequireRole>
                }
              />
              <Route
                path="/sales"
                element={
                  <RequireRole roles={["owner", "counter", "accountant"]}>
                    <SalesPage />
                  </RequireRole>
                }
              />
              <Route
                path="/sales/new"
                element={
                  <RequireRole roles={["owner", "counter"]}>
                    <BillEntryPage />
                  </RequireRole>
                }
              />
              <Route
                path="/purchases"
                element={
                  <RequireRole roles={["owner", "counter", "accountant"]}>
                    <PurchasesPage />
                  </RequireRole>
                }
              />
              <Route
                path="/purchases/orders"
                element={
                  <RequireRole roles={["owner", "counter", "accountant"]}>
                    <OrdersPage />
                  </RequireRole>
                }
              />
              <Route
                path="/purchases/schemes"
                element={
                  <RequireRole roles={["owner", "accountant"]}>
                    <SchemesPage />
                  </RequireRole>
                }
              />
              <Route
                path="/purchases/new"
                element={
                  <RequireRole roles={["owner", "counter"]}>
                    <PurchaseEntryPage />
                  </RequireRole>
                }
              />
              <Route
                path="/payments"
                element={
                  <RequireRole roles={["owner", "counter", "accountant"]}>
                    <PaymentsPage />
                  </RequireRole>
                }
              />
              <Route
                path="/cash"
                element={
                  <RequireRole roles={["owner", "counter", "accountant"]}>
                    <CashBookPage />
                  </RequireRole>
                }
              />
              <Route
                path="/rates"
                element={
                  <RequireRole roles={["owner"]}>
                    <RatesLayout />
                  </RequireRole>
                }
              >
                <Route index element={<RateBoardPage />} />
                <Route path="customers" element={<CustomerRatesPage />} />
              </Route>
              <Route
                path="/stock"
                element={
                  <RequireRole roles={["owner", "counter", "accountant"]}>
                    <StockLayout />
                  </RequireRole>
                }
              >
                <Route index element={<StockPage />} />
                <Route path="transfers" element={<TransfersPage />} />
                <Route path="counts" element={<CountsPage />} />
                <Route path="adjustments" element={<AdjustmentsPage />} />
                <Route
                  path="lost-sales"
                  element={
                    <RequireRole roles={["owner", "counter"]}>
                      <LostSalesPage />
                    </RequireRole>
                  }
                />
                <Route
                  path="analysis"
                  element={
                    <RequireRole roles={["owner"]}>
                      <StockAnalysisPage />
                    </RequireRole>
                  }
                />
                <Route
                  path="value"
                  element={
                    <RequireRole roles={["owner", "accountant"]}>
                      <StockValuePage />
                    </RequireRole>
                  }
                />
                <Route
                  path="shortages"
                  element={
                    <RequireRole roles={["owner", "accountant"]}>
                      <ShrinkagePage />
                    </RequireRole>
                  }
                />
              </Route>
              <Route
                path="/parties"
                element={
                  <RequireRole roles={["owner", "counter", "accountant"]}>
                    <PartiesPage />
                  </RequireRole>
                }
              />
              <Route
                path="/reports"
                element={
                  <RequireRole roles={["owner", "counter", "accountant"]}>
                    <ReportsLayout />
                  </RequireRole>
                }
              >
                <Route index element={<ClosingPage />} />
                <Route
                  path="profit"
                  element={
                    <RequireRole roles={["owner"]}>
                      <ProfitPage />
                    </RequireRole>
                  }
                />
                <Route
                  path="pnl"
                  element={
                    <RequireRole roles={["owner"]}>
                      <PnlPage />
                    </RequireRole>
                  }
                />
                <Route
                  path="profit-cuts"
                  element={
                    <RequireRole roles={["owner"]}>
                      <ProfitCutsPage />
                    </RequireRole>
                  }
                />
                <Route
                  path="itc-risk"
                  element={
                    <RequireRole roles={["owner", "accountant"]}>
                      <ItcRiskPage />
                    </RequireRole>
                  }
                />
                <Route
                  path="receivables"
                  element={
                    <RequireRole roles={["owner", "accountant"]}>
                      <ReceivablesPage />
                    </RequireRole>
                  }
                />
                <Route
                  path="working-capital"
                  element={
                    <RequireRole roles={["owner"]}>
                      <WorkingCapitalPage />
                    </RequireRole>
                  }
                />
                <Route
                  path="tally"
                  element={
                    <RequireRole roles={["owner", "accountant"]}>
                      <TallyPage />
                    </RequireRole>
                  }
                />
                <Route
                  path="overrides"
                  element={
                    <RequireRole roles={["owner"]}>
                      <OverridesPage />
                    </RequireRole>
                  }
                />
                <Route
                  path="itc-reversal"
                  element={
                    <RequireRole roles={["owner", "accountant"]}>
                      <ItcReversalPage />
                    </RequireRole>
                  }
                />
                <Route
                  path="bank"
                  element={
                    <RequireRole roles={["owner", "accountant"]}>
                      <BankPage />
                    </RequireRole>
                  }
                />
                <Route
                  path="order-match"
                  element={
                    <RequireRole roles={["owner"]}>
                      <OrderMatchPage />
                    </RequireRole>
                  }
                />
                <Route
                  path="exceptions"
                  element={
                    <RequireRole roles={["owner"]}>
                      <ExceptionsPage />
                    </RequireRole>
                  }
                />
                <Route
                  path="dues"
                  element={
                    <RequireRole roles={["owner", "accountant"]}>
                      <DuesPage />
                    </RequireRole>
                  }
                />
                <Route
                  path="gst"
                  element={
                    <RequireRole roles={["owner", "accountant"]}>
                      <GstPage />
                    </RequireRole>
                  }
                />
                <Route
                  path="segments"
                  element={
                    <RequireRole roles={["owner", "accountant"]}>
                      <SegmentsPage />
                    </RequireRole>
                  }
                />
              </Route>
              <Route
                path="/transport"
                element={
                  <RequireRole roles={["owner", "accountant"]}>
                    <TransportLayout />
                  </RequireRole>
                }
              >
                <Route index element={<TripsPage />} />
                <Route path="vehicles" element={<VehiclesPage />} />
                <Route path="direct" element={<DirectSalesPage />} />
              </Route>
              {MODULES.filter((m) => m.milestone && !BUILT.has(m.path)).map((m) => (
                <Route
                  key={m.path}
                  path={m.path}
                  element={
                    <RequireRole roles={m.roles}>
                      <ComingSoonPage module={m} />
                    </RequireRole>
                  }
                />
              ))}
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
