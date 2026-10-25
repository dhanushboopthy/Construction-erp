import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router";

import { createQueryClient } from "@/api/queryClient";

import { useAdminAuth } from "./AdminAuthContext";
import { AdminAuthProvider } from "./AdminAuthProvider";
import { AdminShell } from "./AdminShell";
import { ActivityPage } from "./pages/ActivityPage";
import { AdminLoginPage } from "./pages/AdminLoginPage";
import { CompaniesPage } from "./pages/CompaniesPage";
import { CompanyPage } from "./pages/CompanyPage";
import { NewCompanyPage } from "./pages/NewCompanyPage";
import { OverviewPage } from "./pages/OverviewPage";
import { UsersPage } from "./pages/UsersPage";

const queryClient = createQueryClient();

function RequireAdmin({ children }: { children: ReactNode }) {
  const { admin, ready } = useAdminAuth();
  const location = useLocation();
  if (!ready) return <p role="status">Loading…</p>;
  if (!admin) return <Navigate to="/admin/login" replace state={{ from: location.pathname }} />;
  return children;
}

/** The Duolink admin console (Milestone 16, ADR 0012), served at admin.<domain>/admin. */
export function AdminApp({ client = queryClient }: { client?: QueryClient }) {
  return (
    <QueryClientProvider client={client}>
      <AdminAuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/admin/login" element={<AdminLoginPage />} />
            <Route
              path="/admin"
              element={
                <RequireAdmin>
                  <AdminShell />
                </RequireAdmin>
              }
            >
              <Route index element={<OverviewPage />} />
              <Route path="companies" element={<CompaniesPage />} />
              <Route path="companies/new" element={<NewCompanyPage />} />
              <Route path="companies/:id" element={<CompanyPage />} />
              <Route path="users" element={<UsersPage />} />
              <Route path="activity" element={<ActivityPage />} />
            </Route>
            <Route path="*" element={<Navigate to="/admin" replace />} />
          </Routes>
        </BrowserRouter>
      </AdminAuthProvider>
    </QueryClientProvider>
  );
}
