import { Navigate, Route, Routes, useParams } from "react-router-dom";
import { useAuth } from "@/features/auth/AuthContext";
import { LoginPage } from "@/features/auth/LoginPage";
import { AutomationFormPage } from "@/features/automations/AutomationFormPage";
import { AutomationsPage } from "@/features/automations/AutomationsPage";
import { AutomationDetailPage } from "@/features/automations/AutomationDetailPage";
import { BusinessHoursPage } from "@/features/settings/BusinessHoursPage";
import { CustomerDetailPage } from "@/features/customers/CustomerDetailPage";
import { CustomersPage } from "@/features/customers/CustomersPage";
import { WebChatPage } from "@/features/conversations/WebChatPage";
import { InboxPage } from "@/features/inbox/InboxPage";
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

function InboxConversationRedirect() {
  const { conversationId } = useParams();
  return <Navigate to={conversationId ? `/?c=${conversationId}` : "/"} replace />;
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
                <Route path="/app/inbox" element={<InboxPage />} />
                <Route path="/app/inbox/:conversationId" element={<InboxConversationRedirect />} />
                <Route path="/customers" element={<CustomersPage />} />
                <Route path="/customers/:customerId" element={<CustomerDetailPage />} />
                <Route path="/app/customers/:customerId" element={<CustomerDetailPage />} />
                <Route path="/automations" element={<AutomationsPage />} />
                <Route path="/automations/new" element={<AutomationFormPage />} />
                <Route path="/automations/:automationId/edit" element={<AutomationFormPage />} />
                <Route path="/automations/:automationId" element={<AutomationDetailPage />} />
                <Route path="/app/automations" element={<AutomationsPage />} />
                <Route path="/channels" element={<Navigate to="/settings/channels" replace />} />
                <Route path="/app/channels" element={<Navigate to="/settings/channels" replace />} />
                <Route path="/knowledge" element={<KnowledgePage />} />
                <Route path="/knowledge/:sourceId" element={<KnowledgeSourcePage />} />
                <Route path="/app/knowledge" element={<Navigate to="/knowledge" replace />} />
                <Route path="/app/knowledge/:sourceId" element={<KnowledgeAppRedirect />} />
                <Route path="/tickets" element={<TicketsPage />} />
                <Route path="/teams" element={<TeamsPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="/settings/business-hours" element={<BusinessHoursPage />} />
                <Route path="/settings/channels" element={<ChannelSettingsPage />} />
                <Route path="/app/settings/channels" element={<ChannelSettingsPage />} />
              </Routes>
            </AppShell>
          </Protected>
        }
      />
    </Routes>
  );
}
