import { Navigate, Route, Routes, useParams } from "react-router-dom";
import { useAuth } from "@/features/auth/AuthContext";
import { LoginPage } from "@/features/auth/LoginPage";
import { InboxPage } from "@/features/inbox/InboxPage";
import { CustomerDetailPage } from "@/features/customers/CustomerDetailPage";
import { CustomersPage } from "@/features/customers/CustomersPage";
import { WebChatPage } from "@/features/conversations/WebChatPage";
import { KnowledgePage, KnowledgeSourcePage } from "@/features/knowledge/KnowledgePage";
import { AppShell } from "@/components/shared/AppShell";
import { TicketsPage } from "@/features/tickets/TicketsPage";
import { TeamsPage } from "@/features/teams/TeamsPage";
import { ChannelSettingsPage } from "@/features/settings/ChannelSettingsPage";
import { SettingsPage } from "@/features/settings/SettingsPage";

function Protected({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="center">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function KnowledgeAppRedirect() {
  const { sourceId } = useParams();
  return <Navigate to={sourceId ? `/knowledge/${sourceId}` : "/knowledge"} replace />;
}

export function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/chat" element={<WebChatPage />} />
      <Route
        path="/*"
        element={
          <Protected>
            <AppShell>
              <Routes>
                <Route path="/" element={<InboxPage />} />
                <Route path="/customers" element={<CustomersPage />} />
                <Route path="/customers/:customerId" element={<CustomerDetailPage />} />
                <Route path="/knowledge" element={<KnowledgePage />} />
                <Route path="/knowledge/:sourceId" element={<KnowledgeSourcePage />} />
                <Route path="/app/knowledge" element={<Navigate to="/knowledge" replace />} />
                <Route path="/app/knowledge/:sourceId" element={<KnowledgeAppRedirect />} />
                <Route path="/tickets" element={<TicketsPage />} />
                <Route path="/teams" element={<TeamsPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="/settings/channels" element={<ChannelSettingsPage />} />
              </Routes>
            </AppShell>
          </Protected>
        }
      />
    </Routes>
  );
}
