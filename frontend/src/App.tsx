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
import { PurchaseEntryPage } from "@/pages/purchases/PurchaseEntryPage";
import { PurchasesPage } from "@/pages/purchases/PurchasesPage";
import { CustomerRatesPage } from "@/pages/rates/CustomerRatesPage";
import { RateBoardPage } from "@/pages/rates/RateBoardPage";
import { RatesLayout } from "@/pages/rates/RatesLayout";
import { OpeningPage } from "@/pages/opening/OpeningPage";
import { ChargeTypesPage } from "@/pages/settings/ChargeTypesPage";
import { LocationsPage } from "@/pages/settings/LocationsPage";
import { SettingsLayout } from "@/pages/settings/SettingsLayout";
import { ShopSettingsPage } from "@/pages/settings/ShopSettingsPage";
import { UsersPage } from "@/pages/settings/UsersPage";
import { CountsPage } from "@/pages/stock/CountsPage";
import { StockLayout } from "@/pages/stock/StockLayout";
import { StockPage } from "@/pages/stock/StockPage";
import { TransfersPage } from "@/pages/stock/TransfersPage";
import { TodayPage } from "@/pages/TodayPage";

const queryClient = createQueryClient();

/** Modules that have real screens; the rest show a placeholder until their milestone. */
const BUILT = new Set(["/settings", "/items", "/parties", "/stock", "/purchases", "/rates"]);

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
                <Route path="opening" element={<OpeningPage />} />
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
                path="/purchases"
                element={
                  <RequireRole roles={["owner", "counter", "accountant"]}>
                    <PurchasesPage />
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
              </Route>
              <Route
                path="/parties"
                element={
                  <RequireRole roles={["owner", "counter", "accountant"]}>
                    <PartiesPage />
                  </RequireRole>
                }
              />
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
