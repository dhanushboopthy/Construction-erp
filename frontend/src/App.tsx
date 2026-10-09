import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router";

import { createQueryClient } from "@/api/queryClient";
import { AuthProvider } from "@/auth/AuthProvider";
import { AppShell } from "@/components/AppShell";
import { RequireAuth } from "@/components/RequireAuth";
import { RequireRole } from "@/components/RequireRole";
import { MODULES } from "@/modules";
import { ComingSoonPage } from "@/pages/ComingSoonPage";
import { LoginPage } from "@/pages/LoginPage";
import { LocationsPage } from "@/pages/settings/LocationsPage";
import { SettingsLayout } from "@/pages/settings/SettingsLayout";
import { ShopSettingsPage } from "@/pages/settings/ShopSettingsPage";
import { UsersPage } from "@/pages/settings/UsersPage";
import { TodayPage } from "@/pages/TodayPage";

const queryClient = createQueryClient();

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
              </Route>
              {MODULES.filter((m) => m.milestone && m.path !== "/settings").map((m) => (
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
