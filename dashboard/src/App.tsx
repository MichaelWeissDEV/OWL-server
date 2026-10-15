import type { ReactElement } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth/AuthProvider";
import { Layout } from "./components/Layout";
import { ErrorBlock, Spinner } from "./components/Feedback";
import { ActivityPage } from "./pages/ActivityPage";
import { AuditPage } from "./pages/AuditPage";
import { CollectionsPage } from "./pages/CollectionsPage";
import { LoginPage, SsoCallback } from "./pages/LoginPage";
import { OverviewPage } from "./pages/OverviewPage";
import { ProfilePage } from "./pages/ProfilePage";
import { RegistriesPage, RegistryDetailPage } from "./pages/RegistriesPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SkillDetailPage } from "./pages/SkillDetailPage";
import { SkillsPage } from "./pages/SkillsPage";
import { TokensPage } from "./pages/TokensPage";
import { UsersPage } from "./pages/UsersPage";

/** Hides admin pages from non-admins. The server enforces this too - this is only convenience. */
function AdminOnly({ children }: { children: ReactElement }) {
  const { isAdmin, signedIn, config } = useAuth();
  const location = useLocation();
  if (isAdmin) return children;
  if (!signedIn && !config?.open) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;
  return <ErrorBlock error={new Error("Only server administrators can open this page.")} title="Not allowed" />;
}

export function App() {
  const { loading, error } = useAuth();
  if (loading) return <Spinner label="Loading OWL Server" />;
  if (error) return <ErrorBlock error={new Error(error)} title="The server cannot be reached" />;
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/auth/callback" element={<SsoCallback />} />
      <Route element={<Layout />}>
        <Route index element={<OverviewPage />} />
        <Route path="registries" element={<RegistriesPage />} />
        <Route path="registries/:slug" element={<RegistryDetailPage />} />
        <Route path="r/:registry" element={<Navigate to="skills" replace />} />
        <Route path="r/:registry/skills" element={<SkillsPage />} />
        <Route path="r/:registry/skills/:author/:name" element={<SkillDetailPage />} />
        <Route path="r/:registry/collections" element={<CollectionsPage />} />
        <Route path="r/:registry/activity" element={<ActivityPage />} />
        <Route path="profile" element={<ProfilePage />} />
        <Route path="admin/users" element={<AdminOnly><UsersPage /></AdminOnly>} />
        <Route path="admin/tokens" element={<AdminOnly><TokensPage /></AdminOnly>} />
        <Route path="admin/audit" element={<AdminOnly><AuditPage /></AdminOnly>} />
        <Route path="settings" element={<AdminOnly><SettingsPage /></AdminOnly>} />
        <Route path="*" element={<ErrorBlock error={new Error("This page does not exist.")} title="Not found" />} />
      </Route>
    </Routes>
  );
}
