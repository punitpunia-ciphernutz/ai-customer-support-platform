import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "@/features/auth/AuthContext";
import { LoginPage } from "@/features/auth/LoginPage";
import { InboxPage } from "@/features/inbox/InboxPage";
import { CustomersPage } from "@/features/customers/CustomersPage";
import { WebChatPage } from "@/features/conversations/WebChatPage";
import { KnowledgePage, KnowledgeSourcePage } from "@/features/knowledge/KnowledgePage";
import { AppShell } from "@/components/shared/AppShell";

function Protected({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="center">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export function App() {
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
                <Route path="/knowledge" element={<KnowledgePage />} />
                <Route path="/knowledge/:sourceId" element={<KnowledgeSourcePage />} />
              </Routes>
            </AppShell>
          </Protected>
        }
      />
    </Routes>
  );
}
